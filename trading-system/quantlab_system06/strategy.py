"""The system 06 brain — now a thin adapter over the modular ensemble.

The 200-line monolith that used to live here (every risk idea as an inline flag)
has been decomposed into independent modules under `modules/`, combined by
`orchestrator.EnsembleBrain`. This class is the compatibility surface the rest of
the system already knows: it keeps the `system06-oracle-net` family name, the
constructor signature, and `parameters()` byte-for-byte, so `launch.py`, the
autoloop, the backtest fingerprint, and the monitor card are all unchanged. It
builds the channel table and the module set once, then delegates every decision.

The equivalence between this ensemble and the retired monolith is pinned by
`tests/test_ensemble.py` (the full risk-layer parameter space) and was verified on
real-data backtests before the monolith was removed. See `REFACTOR_PLAN.md`.
"""

from __future__ import annotations

from typing import Any

from quantlab_trading.brains import register
from quantlab_trading.runner import Decision

from .channels import Channels
from .orchestrator import build_ensemble


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
        mom_gate: float = 0.0,    # cross-sectional momentum gate: 0 = off; else quantile threshold
        breadth_gate: float = 0.0,   # market-breadth risk-off: flatten the book below this breadth
        regime_deploy: float = 0.0,  # regime-scaled deployment cap (0 = static position_fraction)
        regime_persist: float = 0.0,  # EMA span (bars) smoothing breadth for bidirectional deploy
        bar_seconds: int = 900,   # 15m
        model_tag: str = "system06",
        **_ignored: Any,
    ):
        # Kept verbatim for parameters(): the backtest fingerprint and the monitor
        # card read these, so their names and values must not drift.
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

        self._brain = build_ensemble(
            Channels.from_file(signals),
            position_fraction=self.position_fraction, max_positions=self.max_positions,
            max_drawdown=self.max_drawdown, enter=self.enter, exit_=self.exit_,
            min_hold=self.min_hold, stop_loss=self.stop_loss, trail_stop=self.trail_stop,
            vol_scale=self.vol_scale, vol_floor=self.vol_floor, mom_gate=self.mom_gate,
            breadth_gate=self.breadth_gate, regime_deploy=self.regime_deploy,
            regime_persist=self.regime_persist, bar_seconds=self.bar_seconds,
        )

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
        self._brain.reset()

    def decide(self, tick: dict[str, Any]) -> Decision:
        return self._brain.decide(tick)
