"""Regime: market breadth → risk-off exits and dynamic capital deployment.

Breadth is the fraction of the traded universe in a causal uptrend. This one
module owns both things the monolith derived from it:

  - **risk-off** (`breadth_gate`): when breadth collapses below the gate — a broad
    bear, 2018/2022 — veto every entry and demand the whole book to cash. An
    absolute regime switch, distinct from the per-symbol trend veto.
  - **deployment** (`regime_deploy` / `regime_persist`): the fraction of equity to
    put to work. `position_fraction` is the defensive floor; a broad, confirmed
    uptrend ramps deployment up to `regime_deploy`. With `regime_persist` the
    breadth is EMA-smoothed so brief pullbacks don't whipsaw exposure and it scales
    the full way from near-cash (sustained bear) to the cap (sustained bull).

Off (`breadth_gate ≤ 0` and `regime_deploy ≤ 0`) → the module abstains entirely.
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput

# The breadth band mapped onto the deployment range, matching the monolith.
DEPLOY_LO, DEPLOY_HI = 0.35, 0.70


class Regime:
    def __init__(self, breadth_gate: float = 0.0, regime_deploy: float = 0.0,
                 regime_persist: float = 0.0, position_fraction: float = 0.90):
        self.name = "regime"
        self.weight = 0.0  # sets deploy + risk-off veto/exit, never votes direction
        self.breadth_gate = float(breadth_gate)
        self.regime_deploy = float(regime_deploy)
        self.regime_persist = float(regime_persist)
        self.position_fraction = float(position_fraction)
        self._breadth_ema: float | None = None

    def reset(self) -> None:
        self._breadth_ema = None

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        ch, ns, candles = view.channels, view.ns, view.candles

        # Breadth: fraction of the universe with a live trend map that is up. None
        # when no trend maps are present (pre-gate signals) — leaves both features off.
        trended = [s for s in candles if ch.has("trend", s)]
        breadth = (sum(1 for s in trended if ch.uptrend(s, ns)) / len(trended)
                   if trended else None)

        # Risk-off: veto every entry and empty the book.
        if self.breadth_gate > 0 and breadth is not None and breadth < self.breadth_gate:
            for symbol in candles:
                out.vote(symbol, veto=True)
            for symbol in view.held:
                out.demand_exit(symbol, "RISKOFF", "market breadth collapsed; to cash")

        # Deployment fraction. position_fraction is the floor; ramp up to regime_deploy
        # as breadth crosses the bear→bull band. Only active with regime_deploy>0 and a
        # known breadth — otherwise no suggestion, and the orchestrator keeps the floor.
        if self.regime_deploy > 0 and breadth is not None:
            lo, hi = DEPLOY_LO, DEPLOY_HI
            if self.regime_persist > 0:
                alpha = 2.0 / (self.regime_persist + 1.0)
                self._breadth_ema = (breadth if self._breadth_ema is None
                                     else alpha * breadth + (1.0 - alpha) * self._breadth_ema)
                score = min(1.0, max(0.0, (self._breadth_ema - lo) / (hi - lo)))
                out.deploy = max(0.05, self.regime_deploy * score)
            else:
                score = min(1.0, max(0.0, (breadth - lo) / (hi - lo)))
                out.deploy = self.position_fraction + (self.regime_deploy - self.position_fraction) * score
        return out
