"""The orchestrator: assemble the bar once, poll the modules, combine, decide.

This is the thin conductor that replaces the monolithic `OracleNetBrain.decide`.
It owns exactly what a strategy must own and no module may: the 25 % peak-to-trough
mandate, per-name peak bookkeeping, the exit priority, the consensus rule, and the
final sizing. Everything opinionated — is this name worth holding, how turbulent is
it, has the regime turned, does a stop fire — lives in a module.

Combination, per bar:
  - direction: for each symbol, a weight-weighted mean of the conviction of the
    modules that express a directional opinion (conviction > 0); a symbol may ENTER
    only if that score clears `enter`, no module vetoes it, and at least
    `consensus_k` modules independently back it. Non-directional modules (stops,
    regime, vol, momentum) never dilute the mean — they veto, exit, size or deploy.
  - exits: a module may DEMAND an exit (stop, risk-off); the highest-priority demand
    fires immediately, ignoring `min_hold`. Otherwise a conviction exit fires once a
    held name's score falls to `exit_` and it has cleared `min_hold`.
  - deploy: the fraction of equity to put to work, reconciled from the modules'
    book-wide suggestions (the regime/money layer); defaults to the static floor.
  - size: `equity * deploy / max_positions`, times the product of the per-symbol
    size multipliers, bounded by the book.

Fed the default module set with every lever off, it reproduces the monolith's
behaviour bar for bar; that equivalence is pinned by `tests/test_ensemble.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np

from quantlab_trading.runner import Decision

from .channels import Channels
from .modules.base import MarketView, Module
from .modules.meta import Meta
from .modules.microstructure import Microstructure
from .modules.momentum import Momentum
from .modules.money import Money
from .modules.oracle_nn import OracleNN
from .modules.regime import Regime
from .modules.risk import Stops
from .modules.volatility import Volatility

# Lower number = higher priority. A stop outranks a regime risk-off: if both fire
# on a name the reason recorded is the stop, exactly as the monolith's if/elif did.
EXIT_PRIORITY = {"STOP": 0, "RISKOFF": 1}


def _ns(iso: str) -> int:
    """Tick timestamp (ISO string) -> epoch ns, matching `infer._epoch_ns`."""
    moment = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    naive_utc = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return int(np.datetime64(naive_utc, "ns").astype("int64"))


class EnsembleBrain:
    """Conduct a set of decision modules into one long-only portfolio decision."""

    def __init__(
        self,
        channels: Channels,
        modules: list[Module],
        *,
        position_fraction: float = 0.90,
        max_positions: int = 5,
        max_drawdown: float = 0.25,
        enter: float = 0.5,
        exit_: float = 0.5,
        min_hold: int = 1,
        consensus_k: int = 1,
        bar_seconds: int = 900,
    ):
        self._channels = channels
        self.modules = list(modules)
        self.position_fraction = float(position_fraction)
        self.max_positions = int(max_positions)
        self.max_drawdown = float(max_drawdown)
        self.enter = float(enter)
        self.exit_ = float(exit_)
        self.min_hold = int(min_hold)
        self.consensus_k = int(consensus_k)
        self.bar_seconds = int(bar_seconds)
        self._equity_peak = 0.0
        self._peak: dict[str, float] = {}  # per-holding high-water price (trailing stops)

    def reset(self) -> None:
        self._equity_peak = 0.0
        self._peak = {}
        for module in self.modules:
            module.reset()

    # -- combination -----------------------------------------------------------

    def _combine(self, view: MarketView) -> tuple[dict[str, dict[str, Any]], float | None, float, str]:
        """Poll every module and fold their votes into one row per symbol.

        `agg[symbol]` = {score, veto, size_mult, backers, exit}: the weighted-mean
        conviction (over directional votes only), whether any module forbids entry,
        the product of size multipliers, the consensus count, and the winning exit
        demand (reason, rationale) if any. Also returns the reconciled deploy
        fraction and a joined note.
        """
        agg: dict[str, dict[str, Any]] = {}
        deploys: list[float] = []
        deploy_mult = 1.0
        notes: list[str] = []
        for module in self.modules:
            output = module.evaluate(view)
            if output.deploy is not None:
                deploys.append(float(output.deploy))
            if output.deploy_mult is not None:
                deploy_mult *= float(output.deploy_mult)
            if output.note:
                notes.append(f"{module.name}: {output.note}")
            weight = float(getattr(module, "weight", 1.0))
            for symbol, vote in output.votes.items():
                row = agg.setdefault(
                    symbol, {"wsum": 0.0, "wconv": 0.0, "veto": False,
                             "size_mult": 1.0, "backers": 0, "exit": None, "exit_pri": 99}
                )
                # Only a positive conviction is a directional opinion; a veto/size/
                # exit vote carries conviction 0 and must not drag the mean down.
                if weight > 0 and vote.conviction > 0:
                    row["wsum"] += weight
                    row["wconv"] += weight * vote.conviction
                    if vote.conviction >= self.enter and not vote.veto:
                        row["backers"] += 1
                row["veto"] = row["veto"] or vote.veto
                row["size_mult"] *= float(vote.size_mult)
                if vote.exit_now:
                    pri = EXIT_PRIORITY.get(vote.exit_reason, 50)
                    if pri < row["exit_pri"]:
                        row["exit_pri"] = pri
                        row["exit"] = (vote.exit_reason, vote.exit_rationale)
        for row in agg.values():
            row["score"] = row["wconv"] / row["wsum"] if row["wsum"] > 0 else 0.0
        deploy = min(deploys) if deploys else None
        return agg, deploy, deploy_mult, " | ".join(notes)

    # -- the decision ----------------------------------------------------------

    def decide(self, tick: dict[str, Any]) -> Decision:
        decision = Decision()
        account = tick["account"]
        equity = account["equity"]

        # The mandate, peak-to-trough, checked before anything else.
        self._equity_peak = max(self._equity_peak, equity)
        if self._equity_peak and equity <= self._equity_peak * (1 - self.max_drawdown):
            decision.stop = (
                f"drawdown mandate breached: equity {equity:.0f} vs peak {self._equity_peak:.0f}"
            )
            return decision

        stamp = tick.get("timestamp")
        candles = tick.get("candles", {})
        if stamp is None:
            return decision
        nsval = _ns(stamp)
        now = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        positions = account["positions"]

        def price(symbol: str) -> float:
            bar = candles.get(symbol) or {}
            return float(bar.get("close") or 0.0)

        # Per-name high-water bookkeeping, raised each bar for every held name — the
        # trailing-stop module reads these, so the peak is measured from entry exactly
        # as the monolith measured it.
        for symbol in positions:
            px = price(symbol)
            self._peak[symbol] = max(self._peak.get(symbol, 0.0), px) if px else self._peak.get(symbol, 0.0)

        view = MarketView(
            timestamp=now, ns=nsval, candles=candles, account=account,
            channels=self._channels, held=set(positions), peaks=self._peak,
        )
        agg, deploy, deploy_mult, note = self._combine(view)

        def score(symbol: str) -> float:
            return agg.get(symbol, {}).get("score", 0.0)

        # Exits. A module's exit demand (stop, then risk-off) fires first and ignores
        # min_hold; otherwise a conviction exit once the score has fallen to exit_ and
        # the name has cleared min_hold.
        staying = 0
        for symbol, holding in positions.items():
            demand = agg.get(symbol, {}).get("exit")
            if demand is not None:
                decision.sell(symbol, demand[0], demand[1])
                self._peak.pop(symbol, None)
                continue
            held_bars = 0
            entry = holding.get("entry_time")
            if entry:
                held_bars = (now - datetime.fromisoformat(str(entry).replace("Z", "+00:00"))
                             ).total_seconds() / self.bar_seconds
            if score(symbol) <= self.exit_ and held_bars >= self.min_hold:
                decision.sell(symbol, "EXIT", "conviction gone; to cash")
                self._peak.pop(symbol, None)
            else:
                staying += 1

        # Entries: the highest-conviction names that clear the band, the consensus
        # count and the veto, equal weight, capped at the small book.
        room = self.max_positions - staying
        base = deploy if deploy is not None else self.position_fraction
        deployed = min(1.0, max(0.05, base * deploy_mult))  # money mgmt scales, mandate guards
        per = equity * deployed / max(self.max_positions, 1)
        candidates = [
            s for s in candles
            if s not in positions
            and score(s) >= self.enter
            and not agg.get(s, {}).get("veto", False)
            and agg.get(s, {}).get("backers", 0) >= self.consensus_k
        ]
        candidates.sort(key=score, reverse=True)  # scarce slots to top conviction
        for symbol in candidates[:max(room, 0)]:
            size_mult = agg.get(symbol, {}).get("size_mult", 1.0)
            decision.buy(symbol, per * size_mult, "ENTER", "top-conviction up-swing, up regime")
            self._peak[symbol] = price(symbol)

        if not decision.orders:
            decision.note = note or f"holding {staying}"
        return decision


def build_ensemble(
    channels: Channels,
    *,
    position_fraction: float = 0.90,
    max_positions: int = 5,
    max_drawdown: float = 0.25,
    enter: float = 0.5,
    exit_: float = 0.5,
    min_hold: int = 1,
    stop_loss: float = 0.0,
    trail_stop: float = 0.0,
    vol_scale: float = 0.0,
    vol_floor: float = 0.4,
    mom_gate: float = 0.0,
    breadth_gate: float = 0.0,
    regime_deploy: float = 0.0,
    regime_persist: float = 0.0,
    meta_margin: float | None = None,
    money_kelly: float = 0.0,
    money_pyramid: float = 0.0,
    micro_gate: float | None = None,
    consensus_k: int = 1,
    bar_seconds: int = 900,
) -> EnsembleBrain:
    """Assemble the default system-06 module set from the flat risk-layer parameters.

    Every module self-disables when its lever is off, so the list is stable and the
    ensemble with all levers at their defaults equals the monolith's vanilla path.
    """
    modules: list[Module] = [
        OracleNN(),
        Meta(margin=meta_margin),
        Stops(stop_loss=stop_loss, trail_stop=trail_stop),
        Regime(breadth_gate=breadth_gate, regime_deploy=regime_deploy,
               regime_persist=regime_persist, position_fraction=position_fraction),
        Volatility(vol_scale=vol_scale, vol_floor=vol_floor),
        Momentum(mom_gate=mom_gate),
        Money(kelly=money_kelly, pyramid=money_pyramid),
        Microstructure(gate=micro_gate),
    ]
    return EnsembleBrain(
        channels, modules,
        position_fraction=position_fraction, max_positions=max_positions,
        max_drawdown=max_drawdown, enter=enter, exit_=exit_, min_hold=min_hold,
        consensus_k=consensus_k, bar_seconds=bar_seconds,
    )
