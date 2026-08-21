"""Microstructure sentiment: read the derivatives crowd, trade spot against it.

We are spot and long-only — we never touch a perpetual — but the perpetual market
broadcasts where leverage is piled up and when it gets flushed, and that is tradeable
information for a spot book. The `micro` channel carries a causal contrarian score in
[-1, 1] per bar (built offline by `quantlab_system06.microstructure`):

  - **negative** = crowded, over-levered longs (extreme positive funding + a spike in
    open interest): a fragile top — refuse to add into it.
  - **positive** = that leverage has just been flushed (a cascade of LONG liquidations):
    capitulation — the spot entry the primary wants is exactly where to take it.

This module vetoes entries whose contrarian score is at or below `-gate` (crowded/
fragile). Off (`gate is None`, the default, or no micro channel) → abstains.
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput


class Microstructure:
    def __init__(self, gate: float | None = None):
        self.name = "microstructure"
        self.weight = 0.0  # a contrarian filter: vetoes, never votes direction
        self.gate = gate

    def reset(self) -> None:
        pass

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.gate is None:
            return out
        ch, ns = view.channels, view.ns
        for symbol in view.candles:
            score = ch.micro(symbol, ns)
            if score is not None and score <= -abs(self.gate):
                out.vote(symbol, veto=True)
        return out
