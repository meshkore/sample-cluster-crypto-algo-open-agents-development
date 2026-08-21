"""Stops: the capital-preservation exits, as a module.

A hard stop (down `stop_loss` from entry) and a trailing stop (down `trail_stop`
from the position's high-water price) each demand an immediate exit — they outrank
`min_hold` and the conviction band, because in a crash getting to cash is the
mandate's whole job. The peak this reads is the one the orchestrator seeded at
entry and raised each bar, so the trail is measured from the same high-water mark
the monolith used.

Off (both thresholds ≤ 0) → the module abstains and the book behaves as if stops
never existed.
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput


class Stops:
    def __init__(self, stop_loss: float = 0.0, trail_stop: float = 0.0):
        self.name = "stops"
        self.weight = 0.0  # a risk module: it exits and vetoes, it never votes direction
        self.stop_loss = float(stop_loss)
        self.trail_stop = float(trail_stop)

    def reset(self) -> None:
        pass  # peaks are the orchestrator's bookkeeping, reset there

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.stop_loss <= 0 and self.trail_stop <= 0:
            return out
        positions = view.account["positions"]
        for symbol in view.held:
            holding = positions.get(symbol, {})
            px = view.price(symbol)
            peak = view.peaks.get(symbol, 0.0)
            unreal = holding.get("unrealised_pct")
            if unreal is None and px and holding.get("entry_price"):
                unreal = px / float(holding["entry_price"]) - 1.0
            unreal = float(unreal or 0.0)
            stop_hit = self.stop_loss > 0 and unreal <= -self.stop_loss
            trail_hit = (self.trail_stop > 0 and peak > 0 and px > 0
                         and px <= peak * (1 - self.trail_stop))
            if stop_hit or trail_hit:
                out.demand_exit(symbol, "STOP", f"stop hit ({unreal:+.1%}); to cash")
        return out
