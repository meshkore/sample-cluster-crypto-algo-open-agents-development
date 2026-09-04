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
from .modules.drawdown import DrawdownSizer
from .modules.edgemonitor import EdgeMonitor
from .modules.conviction import Conviction
from .modules.crowd import Crowd
from .modules.fractal import Fractal
from .modules.horserace import HorseRace
from .modules.martingale import Martingale
from .modules.meta import Meta
from .modules.microstructure import Microstructure
from .modules.momentum import Momentum
from .modules.onchain import OnChain
from .modules.money import Money
from .modules.oracle_nn import OracleNN
from .modules.regime import Regime
from .modules.risk import Stops
from .modules.seasoning import Seasoning
from .modules.sentiment import Sentiment
from .modules.sizing import Sizing
from .modules.sweep import Sweep
from .modules.tree import Tree
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
        scale_in: int = 0,          # max ADD tranches per position (0 = off)
        scale_step: float = 0.03,   # each add needs this much profit over the last fill
        scale_decay: float = 0.5,   # each add is this fraction of the previous tranche
        scale_enter: float | None = None,  # conviction an ADD needs (None = the entry bar)

        max_drawdown: float = 0.25,
        enter: float = 0.5,
        exit_: float = 0.5,
        min_hold: int = 1,
        consensus_k: int = 1,
        bar_seconds: int = 900,
        min_notional: float = 0.0,       # skip buys below this many dollars (0 = off)
        max_participation: float = 0.0,  # cap a buy at this fraction of the bar's traded value (0 = off)
    ):
        self._channels = channels
        self.modules = list(modules)
        self.position_fraction = float(position_fraction)
        self.max_positions = int(max_positions)
        self.scale_in = max(0, int(scale_in))
        self.scale_step = float(scale_step)
        self.scale_decay = float(scale_decay)
        # Measured 2026-08-30: requiring ENTRY-grade conviction to add made the lever
        # inert - at bars where a position was in profit with tranches available, the
        # median conviction was 0.49 against an entry bar of 0.75, because the model's
        # conviction decays as a trade matures. Demanding it twice counts the same
        # evidence twice: the position has already proven itself IN PRICE. So the add
        # threshold is its own lever, defaulting to the entry bar (unchanged behaviour).
        self.scale_enter = float(scale_enter) if scale_enter is not None else None
        self._tranches: dict[str, int] = {}
        self._last_fill: dict[str, float] = {}
        # Why adds get refused. An INERT lever cost two experiments before this
        # existed; a counter is cheaper than a reproduction.
        self.scale_stats: dict[str, int] = {}
        self.max_drawdown = float(max_drawdown)
        self.enter = float(enter)
        self.exit_ = float(exit_)
        self.min_hold = int(min_hold)
        self.consensus_k = int(consensus_k)
        self.bar_seconds = int(bar_seconds)
        # Execution realism (operator, 2026-09-02, after the 2021 audit). The engine
        # charges the same 15 bps whether an order is $100 or $45M, which is only true
        # at sizes the market never notices. min_notional drops dust orders no venue
        # would fill for a fee that matters; max_participation caps a BUY at a fraction
        # of the bar's actual traded value, because the audit found $45M orders in
        # single 15-minute NEAR candles once the 2021 account had compounded to $122M.
        # Both off by default: every configuration that does not name them is
        # byte-identical to before, the same guarantee allow_adds made.
        self.min_notional = max(0.0, float(min_notional))
        self.max_participation = max(0.0, float(max_participation))
        # Why buys were shrunk or refused - the scale_stats lesson: an invisible
        # refusal reads as INERT, and a counter is cheaper than a reproduction.
        self.cap_stats: dict[str, int] = {}
        # The entry funnel: for every symbol that cleared the model's bar, WHY it did
        # not become a trade. Two years can post the same trade count for completely
        # different reasons, and until this existed the only way to tell them apart was
        # to guess. Diagnosis only - nothing reads it to make a decision.
        self.funnel: dict[str, float] = {}
        self._equity_peak = 0.0
        self._peak: dict[str, float] = {}  # per-holding high-water price (trailing stops)

    def reset(self) -> None:
        self._equity_peak = 0.0
        self._peak = {}
        self._tranches = {}
        self._last_fill = {}
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
                if vote.veto:
                    # Keep WHICH module vetoed, not just that one did. The aggregate
                    # boolean was enough to trade on and useless to diagnose with: two
                    # years can veto the same number of entries for opposite reasons.
                    row.setdefault("vetoed_by", []).append(module.name)
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
                self._tranches.pop(symbol, None)
                self._last_fill.pop(symbol, None)
                continue
            held_bars = 0
            entry = holding.get("entry_time")
            if entry:
                held_bars = (now - datetime.fromisoformat(str(entry).replace("Z", "+00:00"))
                             ).total_seconds() / self.bar_seconds
            if score(symbol) <= self.exit_ and held_bars >= self.min_hold:
                decision.sell(symbol, "EXIT", "conviction gone; to cash")
                self._peak.pop(symbol, None)
                self._tranches.pop(symbol, None)
                self._last_fill.pop(symbol, None)
            else:
                staying += 1

        # Entries: the highest-conviction names that clear the band, the consensus
        # count and the veto, equal weight, capped at the small book.
        room = self.max_positions - staying
        base = deploy if deploy is not None else self.position_fraction
        deployed = min(1.0, max(0.05, base * deploy_mult))  # money mgmt scales, mandate guards
        per = equity * deployed / max(self.max_positions, 1)
        # The entry funnel, counted symbol-by-symbol on the way through. Exactly the
        # same filter as the comprehension it replaces - written as a loop so each
        # rejection can be attributed instead of vanishing into a boolean. Counting
        # only; nothing here changes a single decision.
        candidates = []
        f = self.funnel
        f["bars"] = f.get("bars", 0) + 1
        f["deploy_sum"] = f.get("deploy_sum", 0.0) + deployed
        for s in candles:
            if s in positions:
                continue
            if score(s) < self.enter:
                continue
            f["above_bar"] = f.get("above_bar", 0) + 1
            row = agg.get(s, {})
            if row.get("veto", False):
                for name in row.get("vetoed_by", ["?"]):
                    f[f"veto:{name}"] = f.get(f"veto:{name}", 0) + 1
                f["vetoed"] = f.get("vetoed", 0) + 1
                continue
            if row.get("backers", 0) < self.consensus_k:
                f["no_consensus"] = f.get("no_consensus", 0) + 1
                continue
            f["eligible"] = f.get("eligible", 0) + 1
            candidates.append(s)
        if candidates and room <= 0:
            # The book was already full. These are the entries the strategy WANTED and
            # could not take - the one rejection that is about capacity, not opinion.
            f["book_full"] = f.get("book_full", 0) + len(candidates)
        def cap_buy(symbol: str, notional: float) -> float:
            """Execution-realism funnel: every BUY notional passes through here.

            Returns the notional the market could plausibly absorb, or 0.0 to skip.
            Participation first, then the minimum - a $45M wish capped to $80k must
            still clear the floor, not be excused from it by its original size.
            """
            if self.max_participation > 0:
                bar = candles.get(symbol) or {}
                traded = float(bar.get("close") or 0.0) * float(bar.get("volume") or 0.0)
                if traded > 0 and notional > traded * self.max_participation:
                    notional = traded * self.max_participation
                    self.cap_stats["participation_capped"] = (
                        self.cap_stats.get("participation_capped", 0) + 1)
            if self.min_notional > 0 and notional < self.min_notional:
                self.cap_stats["below_min_notional"] = (
                    self.cap_stats.get("below_min_notional", 0) + 1)
                return 0.0
            return notional

        candidates.sort(key=score, reverse=True)  # scarce slots to top conviction
        for symbol in candidates[:max(room, 0)]:
            size_mult = agg.get(symbol, {}).get("size_mult", 1.0)
            sized = cap_buy(symbol, per * size_mult)
            if sized <= 0:
                continue
            decision.buy(symbol, sized, "ENTER", "top-conviction up-swing, up regime")
            self._peak[symbol] = price(symbol)
            self._tranches[symbol] = 0
            self._last_fill[symbol] = price(symbol)

        # --- progressive entries: pyramid into strength, never into weakness ------
        # Operator request (2026-08-29): do not commit the whole position at once;
        # add as the trade proves itself and the signal keeps confirming.
        #
        # The classic discipline, and the reason this is safe to add: an add is only
        # allowed on a position that is ALREADY IN PROFIT since its last fill. That
        # single rule is what separates pyramiding from averaging down - the ruinous
        # mirror image, which doubles into losers. Each tranche is geometrically
        # smaller (`scale_decay`), so a name's total stake is bounded even if the
        # trend runs for months, and the add must clear the SAME quality bar as a
        # fresh entry (conviction, veto, consensus) - a weakening signal cannot be
        # topped up. Off by default (`scale_in = 0`).
        if self.scale_in > 0:
            cash = float(account.get("cash", 0.0))
            for symbol in positions:
                if symbol in {o["symbol"] for o in decision.orders}:
                    self.scale_stats["acted"] = self.scale_stats.get("acted", 0) + 1
                    continue                      # already acted on this bar
                done = self._tranches.get(symbol, 0)
                if done >= self.scale_in:
                    self.scale_stats["tranches_used"] = self.scale_stats.get("tranches_used", 0) + 1
                    continue
                px, last = price(symbol), self._last_fill.get(symbol, 0.0)
                if px <= 0 or last <= 0 or px < last * (1.0 + self.scale_step):
                    self.scale_stats["not_in_profit"] = self.scale_stats.get("not_in_profit", 0) + 1
                    continue                      # not in profit since the last fill
                row = agg.get(symbol, {})
                add_bar = self.scale_enter if self.scale_enter is not None else self.enter
                if (row.get("score", 0.0) < add_bar or row.get("veto", False)
                        or (self.scale_enter is None
                            and row.get("backers", 0) < self.consensus_k)):
                    self.scale_stats["signal"] = self.scale_stats.get("signal", 0) + 1
                    continue                      # the signal must still be entry-grade
                tranche = per * row.get("size_mult", 1.0) * (self.scale_decay ** (done + 1))
                tranche = min(cap_buy(symbol, tranche), cash)
                if tranche <= 0:
                    self.scale_stats["no_cash"] = self.scale_stats.get("no_cash", 0) + 1
                    continue
                self.scale_stats["fired"] = self.scale_stats.get("fired", 0) + 1
                decision.buy(symbol, tranche, "ADD",
                             f"pyramid tranche {done + 1}/{self.scale_in}: "
                             f"+{(px / last - 1):.1%} since last fill, signal still strong")
                cash -= tranche
                self._tranches[symbol] = done + 1
                self._last_fill[symbol] = px

        if not decision.orders:
            decision.note = note or f"holding {staying}"
        return decision


def build_ensemble(
    channels: Channels,
    *,
    position_fraction: float = 0.90,
    max_positions: int = 5,
    scale_in: int = 0,
    scale_step: float = 0.03,
    scale_decay: float = 0.5,
    scale_enter: float | None = None,
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
    martingale: float = 0.0,
    micro_gate: float | None = None,
    hurst_gate: float = 0.0,
    feargreed: float = 0.0,
    horserace: float = 0.0,
    sweep: float = 0.0,
    tree_weight: float = 0.0,
    money_model: float = 0.0,
    trend_soft: float = 0.0,
    dd_sizer: float = 0.0,
    edge_monitor: float = 0.0,
    fng_min: float = 0.0,
    min_age_days: float = 0.0,
    activity_min: float | None = None,
    conviction_sizing: float = 0.0,
    consensus_k: int = 1,
    bar_seconds: int = 900,
    min_notional: float = 0.0,
    max_participation: float = 0.0,
) -> EnsembleBrain:
    """Assemble the default system-06 module set from the flat risk-layer parameters.

    Every module self-disables when its lever is off, so the list is stable and the
    ensemble with all levers at their defaults equals the monolith's vanilla path.
    """
    modules: list[Module] = [
        OracleNN(trend_soft=trend_soft),
        Meta(margin=meta_margin),
        Stops(stop_loss=stop_loss, trail_stop=trail_stop),
        Regime(breadth_gate=breadth_gate, regime_deploy=regime_deploy,
               regime_persist=regime_persist, position_fraction=position_fraction),
        Volatility(vol_scale=vol_scale, vol_floor=vol_floor),
        Momentum(mom_gate=mom_gate),
        Money(kelly=money_kelly, pyramid=money_pyramid),
        Martingale(step=martingale),
        Microstructure(gate=micro_gate),
        Fractal(hurst_gate=hurst_gate),
        Sentiment(feargreed=feargreed),
        HorseRace(horserace=horserace),
        Sweep(sweep=sweep),
        Tree(tree_weight=tree_weight),
        Sizing(money_model=money_model),
        DrawdownSizer(dd_sizer=dd_sizer, max_drawdown=max_drawdown),
        EdgeMonitor(edge_monitor=edge_monitor),
        Crowd(fng_min=fng_min),
        Seasoning(min_age_days=min_age_days),
        OnChain(activity_min=activity_min),
        Conviction(conviction_sizing=conviction_sizing, enter=enter),
    ]
    return EnsembleBrain(
        channels, modules,
        position_fraction=position_fraction, max_positions=max_positions,
        scale_in=scale_in, scale_step=scale_step, scale_decay=scale_decay,
        scale_enter=scale_enter,
        max_drawdown=max_drawdown, enter=enter, exit_=exit_, min_hold=min_hold,
        consensus_k=consensus_k, bar_seconds=bar_seconds,
        min_notional=min_notional, max_participation=max_participation,
    )
