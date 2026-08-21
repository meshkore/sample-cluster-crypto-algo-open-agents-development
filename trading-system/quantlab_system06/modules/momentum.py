"""Cross-sectional momentum gate: spend scarce slots on relative winners.

At each bar it ranks the whole basket by trailing return and vetoes the names
below the `mom_gate` quantile, so only coins strong relative to their peers can be
entered. It is a filter on entries — a veto, never an exit and never a direction —
so a held name that slips down the ranking is kept, matching the monolith.

Off (`mom_gate ≤ 0`) or no momentum channel → abstain.
"""

from __future__ import annotations

import numpy as np

from .base import MarketView, ModuleOutput


class Momentum:
    def __init__(self, mom_gate: float = 0.0):
        self.name = "momentum"
        self.weight = 0.0  # a rank gate: vetoes, never votes direction
        self.mom_gate = float(mom_gate)

    def reset(self) -> None:
        pass

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.mom_gate <= 0:
            return out
        ch, ns, candles = view.channels, view.ns, view.candles
        basket = [ch.momentum(s, ns) for s in candles if ch.has("mom", s)]
        if not basket:
            return out
        threshold = float(np.quantile(basket, min(max(self.mom_gate, 0.0), 1.0)))
        for symbol in candles:
            value = ch.momentum(symbol, ns)
            if (value if value is not None else 0.0) < threshold:
                out.vote(symbol, veto=True)
        return out
