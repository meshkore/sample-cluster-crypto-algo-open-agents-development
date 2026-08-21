"""Volatility targeting: shrink turbulent names, grow calm ones, to hold roughly
constant risk (the managed-vol idea).

`vol` in the channel table is a causal ratio of recent to typical realized vol.
The size multiplier is `1/ratio` — below 1 when the name is turbulent, above 1
when calm — clamped between `vol_floor` (never de-risk past this) and `vol_scale`
(the cap on growing into calm). It scales notional only; it never changes
direction, so its conviction is always zero and it never dilutes the vote.

Off (`vol_scale ≤ 0`) or no vol channel → multiplier 1.0 (abstain).
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput


class Volatility:
    def __init__(self, vol_scale: float = 0.0, vol_floor: float = 0.4):
        self.name = "volatility"
        self.weight = 0.0  # sizing only, no direction
        self.vol_scale = float(vol_scale)
        self.vol_floor = float(vol_floor)

    def reset(self) -> None:
        pass

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.vol_scale <= 0:
            return out
        ch, ns = view.channels, view.ns
        for symbol in view.candles:
            ratio = ch.volratio(symbol, ns)
            if ratio is None:
                continue  # size flat — abstain
            factor = 1.0 / float(ratio)
            out.vote(symbol, size_mult=float(min(self.vol_scale, max(self.vol_floor, factor))))
        return out
