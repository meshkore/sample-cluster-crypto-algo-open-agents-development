"""The brain: read the net's precomputed hold bit per symbol, run a portfolio.

It holds no model and no feature code — `infer.py` did the thinking and wrote one
bit per bar per symbol. Each tick, the brain:

  - sells any held symbol the net now reads as flat,
  - buys, equal-weight, the symbols the net reads as an up-swing and it is not yet
    holding, up to `max_positions`,
  - stops the run when equity is 25% below the deposit — the mandate, enforced by
    the brain as `CONTRACT.md` requires.

Long-only and now a basket rather than one asset: the oracle is still one in/out
bit per symbol, so there is nothing to size beyond in-or-out and how many at once.
Equal weight is the honest default for a signal that is one bit — it expresses no
confidence the model did not give it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np

from quantlab_trading.brains import register
from quantlab_trading.runner import Decision

from .infer import load_table


def _ns(iso: str) -> int:
    """Tick timestamp (ISO string) -> epoch ns, matching `infer._epoch_ns`."""
    moment = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    naive_utc = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return int(np.datetime64(naive_utc, "ns").astype("int64"))


@register(
    "system06-oracle-net",
    "A basket that holds each liquid crypto while a TCN trained to imitate the "
    "perfect-hindsight oracle predicts an up-swing on it; flat otherwise; 25% "
    "drawdown mandate.",
)
class OracleNetBrain:
    def __init__(
        self,
        signals: str = "research/system06/signals.npz",
        trade_from: str | None = None,
        position_fraction: float = 0.90,
        max_positions: int = 5,
        max_drawdown: float = 0.25,
        enter: float = 0.5,
        exit_: float = 0.5,
        min_hold: int = 1,
        stop_loss: float = 0.0,   # hard stop: exit if down this fraction from entry (0 = off)
        trail_stop: float = 0.0,  # trailing stop: exit if down this fraction from peak (0 = off)
        vol_scale: float = 0.0,   # volatility targeting: 0 = off; >0 = cap on the size multiplier
        vol_floor: float = 0.4,   # smallest exposure multiplier when vol is high (de-risk floor)
        mom_gate: float = 0.0,    # cross-sectional momentum gate: 0 = off; else only enter names
        #                           whose relative momentum is >= this quantile of the basket
        breadth_gate: float = 0.0,  # market-breadth risk-off: 0 = off; else flatten the WHOLE book
        #                             when fewer than this fraction of the universe is in an uptrend
        regime_deploy: float = 0.0,  # regime-scaled deployment: 0 = off (static fraction); else the
        #                             MAX total fraction of equity to deploy in a strong broad uptrend.
        #                             position_fraction becomes the defensive floor (bear/neutral).
        regime_persist: float = 0.0,  # regime smoothing (EMA span in bars): 0 = off (instantaneous
        #                             breadth). >0 turns on PERSISTENCE + BIDIRECTIONAL deployment:
        #                             breadth is EMA-smoothed over this span so brief pullbacks don't
        #                             slash exposure and brief bear-rallies don't spike it, and the
        #                             deployed fraction scales the FULL way from near-cash (sustained
        #                             bear) up to regime_deploy (sustained bull). Only active with
        #                             regime_deploy>0.
        bar_seconds: int = 900,  # 15m
        model_tag: str = "system06",
        **_ignored: Any,
    ):
        self.signals_path = signals
        self.trade_from = trade_from
        self.position_fraction = float(position_fraction)
        self.max_positions = int(max_positions)
        self.max_drawdown = float(max_drawdown)
        self.enter = float(enter)
        self.exit_ = float(exit_)
        self.min_hold = int(min_hold)
        self.stop_loss = float(stop_loss)
        self.trail_stop = float(trail_stop)
        self.vol_scale = float(vol_scale)
        self.vol_floor = float(vol_floor)
        self.mom_gate = float(mom_gate)
        self.breadth_gate = float(breadth_gate)
        self.regime_deploy = float(regime_deploy)
        self.regime_persist = float(regime_persist)
        self.bar_seconds = int(bar_seconds)
        self.model_tag = model_tag
        self.table = load_table(signals)  # {symbol: {"prob": {ns: p}, "trend": {ns: bit}}}
        self._peak: dict[str, float] = {}  # per-holding high-water price, for the trailing stop
        self._equity_peak = 0.0  # book high-water, for the peak-to-trough mandate
        self._breadth_ema: float | None = None  # smoothed breadth for regime persistence

    def parameters(self) -> dict[str, Any]:
        return {
            "trade_from": self.trade_from,
            "position_fraction": self.position_fraction,
            "max_positions": self.max_positions,
            "max_drawdown": self.max_drawdown,
            "enter": self.enter,
            "exit": self.exit_,
            "min_hold": self.min_hold,
            "stop_loss": self.stop_loss,
            "trail_stop": self.trail_stop,
            "vol_scale": self.vol_scale,
            "vol_floor": self.vol_floor,
            "mom_gate": self.mom_gate,
            "breadth_gate": self.breadth_gate,
            "regime_deploy": self.regime_deploy,
            "regime_persist": self.regime_persist,
            "model_tag": self.model_tag,
        }

    def reset(self) -> None:
        """Hold state is read from the account; peaks (equity + per-name) are ours."""
        self._peak = {}
        self._equity_peak = 0.0
        self._breadth_ema = None  # persistence EMA (regime_persist), warms per independent year

    def decide(self, tick: dict[str, Any]) -> Decision:
        decision = Decision()
        account = tick["account"]
        equity = account["equity"]
        initial = account["initial_capital"]

        # The mandate is peak-to-trough (mandate_basis "peak"): stop when equity is
        # max_drawdown below its own high-water mark, NOT below the deposit. The
        # lenient deposit basis would let a book run up then give 25% back and keep
        # trading — the published incumbent used "peak", so we must too.
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

        def prob(symbol: str) -> float:
            return self.table.get(symbol, {}).get("prob", {}).get(nsval, 0.0)

        def uptrend(symbol: str) -> bool:
            # Missing trend map (pre-gate signals) reads as risk-on, so old files
            # behave exactly as before the gate existed.
            trend = self.table.get(symbol, {}).get("trend")
            if not trend:
                return True
            return bool(trend.get(nsval, 0))

        def size_factor(symbol: str) -> float:
            # Volatility targeting: shrink the position when recent vol is above the
            # symbol's typical vol, grow it (capped) when below. Off (factor 1.0) when
            # vol_scale<=0 or the vol channel is absent — fully backward compatible.
            if self.vol_scale <= 0:
                return 1.0
            vol = self.table.get(symbol, {}).get("vol")
            ratio = vol.get(nsval) if vol else None
            if not ratio or ratio <= 0:
                return 1.0
            factor = 1.0 / float(ratio)
            return float(min(self.vol_scale, max(self.vol_floor, factor)))

        def price(symbol: str) -> float:
            bar = candles.get(symbol) or {}
            return float(bar.get("close") or 0.0)

        # Market-breadth risk-off gate (idea market-breadth-gate): an ABSOLUTE regime
        # switch. breadth = fraction of the traded universe in a causal uptrend. In a
        # broad bear (2022) breadth collapses and the whole book goes to cash — distinct
        # from the per-symbol trend filter (which still admits lone bounces) and from the
        # REJECTED relative-momentum gate (which only reranks names, never de-risks). Off
        # (breadth_gate<=0) or no trend maps present -> risk_off stays False, so old
        # signals behave exactly as before the gate existed.
        # Market breadth = fraction of the traded universe currently in a causal
        # uptrend. Computed once and shared by the risk-off gate (an absolute switch)
        # and the regime-scaled deployment below. None when no trend maps are present
        # (pre-gate signals), which leaves both features off — fully backward compatible.
        breadth = None
        trended = [s for s in candles if self.table.get(s, {}).get("trend")]
        if trended:
            breadth = sum(1 for s in trended if uptrend(s)) / len(trended)
        risk_off = bool(self.breadth_gate > 0 and breadth is not None and breadth < self.breadth_gate)

        positions = account["positions"]
        # Exit priority: a STOP always fires (capital preservation is the mandate's
        # whole job in a crash), then — when breadth has collapsed — an absolute risk-off
        # exit (overrides min_hold, like a stop), then a conviction exit once past
        # min_hold. The slow-trend bit is an ENTRY filter only — force-exiting on it churns
        # the book on every wobble, which is what sinks a 15m long book.
        staying = 0
        for symbol, holding in positions.items():
            px = price(symbol)
            peak = max(self._peak.get(symbol, 0.0), px) if px else self._peak.get(symbol, 0.0)
            self._peak[symbol] = peak
            unreal = holding.get("unrealised_pct")
            if unreal is None and px and holding.get("entry_price"):
                unreal = px / float(holding["entry_price"]) - 1.0
            unreal = float(unreal or 0.0)

            held_bars = 0
            entry = holding.get("entry_time")
            if entry:
                held_bars = (now - datetime.fromisoformat(str(entry).replace("Z", "+00:00"))).total_seconds() / self.bar_seconds

            stop_hit = self.stop_loss > 0 and unreal <= -self.stop_loss
            trail_hit = self.trail_stop > 0 and peak > 0 and px > 0 and px <= peak * (1 - self.trail_stop)
            if stop_hit or trail_hit:
                decision.sell(symbol, "STOP", f"stop hit ({unreal:+.1%}); to cash")
                self._peak.pop(symbol, None)
            elif risk_off:
                decision.sell(symbol, "RISKOFF", "market breadth collapsed; to cash")
                self._peak.pop(symbol, None)
            elif prob(symbol) <= self.exit_ and held_bars >= self.min_hold:
                decision.sell(symbol, "EXIT", "conviction gone; to cash")
                self._peak.pop(symbol, None)
            else:
                staying += 1

        # Enter the HIGHEST-conviction names that clear the band AND the up regime,
        # equal weight, capped at a small book — concentration + stops is what lets
        # a long-only crypto basket survive a 25% mandate in a crash year.
        room = self.max_positions - staying
        # Regime-scaled deployment (money management). position_fraction is the
        # DEFENSIVE floor — what we deploy when the market is not in a broad uptrend.
        # When regime_deploy>0 and breadth is known, the deployed fraction ramps from
        # that floor up to regime_deploy as breadth crosses a BEAR->BULL band, so a
        # broad, confirmed uptrend (2019/2020/2021) puts much more capital to work
        # while a bear (2018/2022) stays near the cash-heavy floor. Off (regime_deploy
        # <=0) or no breadth -> the static floor, so old configs are byte-for-byte
        # unchanged. The -25% peak-to-trough mandate above is the guardrail on the
        # extra exposure this buys.
        deployed = self.position_fraction
        if self.regime_deploy > 0 and breadth is not None:
            lo, hi = 0.35, 0.70  # breadth band mapped onto the deployment range
            if self.regime_persist > 0:
                # PERSISTENCE + BIDIRECTIONAL: smooth breadth with an EMA so brief
                # pullbacks/bear-rallies don't whipsaw exposure, and let deployment
                # scale the FULL way — near-cash in a SUSTAINED bear (protects 2018/
                # 2022), up to regime_deploy in a SUSTAINED bull. This is the refined
                # answer to the finding that instantaneous breadth is too noisy (a
                # breadth gate flattened good years on false-bear pullbacks).
                alpha = 2.0 / (self.regime_persist + 1.0)
                self._breadth_ema = (breadth if self._breadth_ema is None
                                     else alpha * breadth + (1.0 - alpha) * self._breadth_ema)
                score = min(1.0, max(0.0, (self._breadth_ema - lo) / (hi - lo)))
                deployed = max(0.05, self.regime_deploy * score)
            else:
                # Instantaneous, floor-anchored (original, off-by-default-compatible).
                score = min(1.0, max(0.0, (breadth - lo) / (hi - lo)))
                deployed = self.position_fraction + (self.regime_deploy - self.position_fraction) * score
        per = equity * deployed / max(self.max_positions, 1)
        candidates = [] if risk_off else [
            s for s in candles
            if s not in positions and prob(s) >= self.enter and uptrend(s)
        ]
        # Cross-sectional momentum gate (idea xsec-momentum): keep only the names whose
        # relative strength clears a quantile of the WHOLE basket, so scarce slots go to
        # relative winners. Off (mom_gate<=0) or no mom channel -> no filtering.
        if self.mom_gate > 0 and candidates:
            def momentum(symbol: str) -> float:
                mom = self.table.get(symbol, {}).get("mom")
                return float(mom.get(nsval, 0.0)) if mom else 0.0
            basket = [momentum(s) for s in candles if (self.table.get(s, {}).get("mom"))]
            if basket:
                threshold = float(np.quantile(basket, min(max(self.mom_gate, 0.0), 1.0)))
                candidates = [s for s in candidates if momentum(s) >= threshold]
        candidates.sort(key=prob, reverse=True)  # spend scarce slots on top conviction
        for symbol in candidates[:max(room, 0)]:
            notional = per * size_factor(symbol)  # volatility-targeted sizing
            decision.buy(symbol, notional, "ENTER", "top-conviction up-swing, up regime")
            self._peak[symbol] = price(symbol)

        if not decision.orders:
            decision.note = f"holding {staying}"
        return decision
