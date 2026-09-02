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
        meta_margin: float | None = None,  # meta-label filter: veto entries with expected net <= this
        #                                    (None = off). Requires a meta.npz verdict channel.
        meta_signals: str = "research/system06/meta.npz",
        money_kelly: float = 0.0,   # fractional-Kelly per-name sizing from the meta edge (0 = off)
        money_pyramid: float = 0.0,  # anti-martingale deploy scaling from the equity trend (0 = off)
        martingale: float = 0.0,     # bounded, occasional press INTO a shallow dip (0 = off)
        micro_gate: float | None = None,  # microstructure contrarian veto threshold (None = off)
        micro_signals: str = "research/system06/micro.npz",
        hurst_gate: float = 0.0,  # fractal-regime gate: veto entries with Hurst below this (0 = off)
        fng_min: float = 0.0,
        scale_in: int = 0,  # progressive entries: max ADD tranches per position (0 = off)
        min_age_days: float = 0.0,  # seasoning: a symbol must have this much of its OWN history
        scale_enter: float | None = None,  # conviction an ADD needs (None = the entry bar)
        activity_min: float | None = None,  # A70: veto entries when chain activity is this many sd below normal
        conviction_sizing: float = 0.0,  # A71: fund each entry in proportion to how far it clears the bar  # A65: veto new entries when the REAL Fear & Greed index is below this (0 = off)
        feargreed: float = 0.0,   # behavioural fear/greed contrarian sizing strength (0 = off)
        horserace: float = 0.0,   # cross-asset lead-lag: upsize laggards when the pack runs (0 = off)
        sweep: float = 0.0,       # MM liquidation-hunt: upsize after a two-sided stop sweep (0 = off)
        tree_weight: float = 0.0,  # decision-tree DIRECTIONAL voter weight (0 = off; needs tree.npz)
        tree_signals: str = "research/system06/tree.npz",
        trend_soft: float = 0.0,   # enter DOWN-trend names at this size instead of vetoing (0 = veto)
        dd_sizer: float = 0.0,     # taper the book as the drawdown limit nears (0 = off)
        money_model: float = 0.0,  # learned money-management sizing intensity (0 = off)
        size_signals: str = "research/system06/moneymodel.npz",
        edge_monitor: float = 0.0,  # circuit breaker: cut deploy when our own realized edge decays (0 = off)
        consensus_k: int = 1,     # require this many directional modules to agree to enter
        bar_seconds: int = 900,   # 15m
        min_notional: float = 0.0,       # execution realism: skip buys below this $ (0 = off)
        max_participation: float = 0.0,  # cap a buy at this share of the bar's traded value (0 = off)
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
        self.meta_margin = None if meta_margin is None else float(meta_margin)
        self.money_kelly = float(money_kelly)
        self.money_pyramid = float(money_pyramid)
        self.martingale = float(martingale)
        self.micro_gate = None if micro_gate is None else float(micro_gate)
        self.hurst_gate = float(hurst_gate)
        self.fng_min = float(fng_min)
        self.scale_in = int(scale_in)
        self.min_age_days = float(min_age_days)
        self.scale_enter = None if scale_enter is None else float(scale_enter)
        self.activity_min = None if activity_min is None else float(activity_min)
        self.conviction_sizing = float(conviction_sizing)
        self.feargreed = float(feargreed)
        self.horserace = float(horserace)
        self.sweep = float(sweep)
        self.tree_weight = float(tree_weight)
        self.trend_soft = float(trend_soft)
        self.dd_sizer = float(dd_sizer)
        self.money_model = float(money_model)
        self.edge_monitor = float(edge_monitor)
        self.consensus_k = int(consensus_k)
        self.bar_seconds = int(bar_seconds)
        self.min_notional = float(min_notional)
        self.max_participation = float(max_participation)
        self.model_tag = model_tag

        # Load each overlay channel only when its lever is active, so off-by-default
        # configs keep an identical backtest fingerprint and pay no load cost.
        meta_path = meta_signals if self.meta_margin is not None else None
        micro_path = micro_signals if self.micro_gate is not None else None
        tree_path = tree_signals if self.tree_weight > 0 else None
        size_path = size_signals if self.money_model > 0 else None
        self._brain = build_ensemble(
            Channels.from_file(signals, meta_path=meta_path, micro_path=micro_path,
                              tree_path=tree_path, size_path=size_path),
            position_fraction=self.position_fraction, max_positions=self.max_positions,
            max_drawdown=self.max_drawdown, enter=self.enter, exit_=self.exit_,
            min_hold=self.min_hold, stop_loss=self.stop_loss, trail_stop=self.trail_stop,
            vol_scale=self.vol_scale, vol_floor=self.vol_floor, mom_gate=self.mom_gate,
            breadth_gate=self.breadth_gate, regime_deploy=self.regime_deploy,
            regime_persist=self.regime_persist, meta_margin=self.meta_margin,
            money_kelly=self.money_kelly, money_pyramid=self.money_pyramid,
            martingale=self.martingale, micro_gate=self.micro_gate,
            hurst_gate=self.hurst_gate, fng_min=self.fng_min, scale_in=self.scale_in, scale_enter=self.scale_enter,
            min_age_days=self.min_age_days, activity_min=self.activity_min, conviction_sizing=self.conviction_sizing,
            feargreed=self.feargreed,
            horserace=self.horserace, sweep=self.sweep,
            tree_weight=self.tree_weight, money_model=self.money_model,
            trend_soft=self.trend_soft, dd_sizer=self.dd_sizer,
            edge_monitor=self.edge_monitor,
            consensus_k=self.consensus_k, bar_seconds=self.bar_seconds,
            min_notional=self.min_notional, max_participation=self.max_participation,
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
            # Only surfaced when active, so off-by-default fingerprints/cards are unchanged.
            **({"meta_margin": self.meta_margin} if self.meta_margin is not None else {}),
            **({"money_kelly": self.money_kelly} if self.money_kelly else {}),
            **({"money_pyramid": self.money_pyramid} if self.money_pyramid else {}),
            **({"martingale": self.martingale} if self.martingale else {}),
            **({"micro_gate": self.micro_gate} if self.micro_gate is not None else {}),
            **({"hurst_gate": self.hurst_gate} if self.hurst_gate else {}),
            **({"fng_min": self.fng_min} if self.fng_min else {}),
            **({"scale_in": self.scale_in} if self.scale_in else {}),
            **({"scale_enter": self.scale_enter} if self.scale_enter is not None else {}),
            **({"min_age_days": self.min_age_days} if self.min_age_days else {}),
            **({"activity_min": self.activity_min} if self.activity_min is not None else {}),
            **({"conviction_sizing": self.conviction_sizing} if self.conviction_sizing else {}),
            **({"min_notional": self.min_notional} if self.min_notional else {}),
            **({"max_participation": self.max_participation} if self.max_participation else {}),
            **({"feargreed": self.feargreed} if self.feargreed else {}),
            **({"horserace": self.horserace} if self.horserace else {}),
            **({"sweep": self.sweep} if self.sweep else {}),
            **({"tree_weight": self.tree_weight} if self.tree_weight else {}),
            **({"trend_soft": self.trend_soft} if self.trend_soft else {}),
            **({"dd_sizer": self.dd_sizer} if self.dd_sizer else {}),
            **({"money_model": self.money_model} if self.money_model else {}),
            **({"edge_monitor": self.edge_monitor} if self.edge_monitor else {}),
            **({"consensus_k": self.consensus_k} if self.consensus_k != 1 else {}),
        }

    def reset(self) -> None:
        self._brain.reset()

    def decide(self, tick: dict[str, Any]) -> Decision:
        return self._brain.decide(tick)
