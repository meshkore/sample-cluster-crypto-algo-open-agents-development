"""Learned money management: size entries by the walk-forward trade-quality channel.

Operator idea A45. Every sizing overlay before this one was a hand-written rule
(vol targeting, fear/greed, horse race) and none moved the needle, because they
scaled a roughly uniform edge. The trade-opportunity map showed the edge is NOT
uniform — expectancy concentrates several-fold in observable entry states — and a
walk-forward model of those states lifted out-of-sample expectancy ~45% relative
without hurting any year. This module applies that model's per-bar multiplier
(precomputed by `moneymodel.py`, quintile-mapped 0.5–2.0) to ENTRY sizing only.

`money_model` is the lever: 0 disables the module entirely; 1.0 applies the
channel's multiplier as-is; values between scale its intensity toward neutral.
Bars without a verdict — the walk-forward's first years, or a missing channel —
are abstained on, so the book behaves exactly as before there. Held names are
never re-sized: this decides how much to buy, never when to sell.
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput

MULT_FLOOR = 0.25
MULT_CAP = 2.5


class Sizing:
    def __init__(self, money_model: float = 0.0):
        self.name = "sizing"
        self.weight = 0.0                    # never votes direction, only scales size
        self.money_model = float(money_model)

    def reset(self) -> None:
        pass

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.money_model <= 0:
            return out
        ch, ns = view.channels, view.ns
        sized = 0
        for symbol in view.candles:
            if symbol in view.held:
                continue                      # entries only
            base = ch.size(symbol, ns)
            if base is None:
                continue                      # no walk-forward verdict -> abstain
            mult = 1.0 + self.money_model * (float(base) - 1.0)
            mult = min(max(mult, MULT_FLOOR), MULT_CAP)
            if mult != 1.0:
                out.vote(symbol, size_mult=mult)
                sized += 1
        if sized:
            out.note = f"sizing: scaled {sized} entry candidate(s)"
        return out
