"""Behavioural fear/greed: contrarian sizing at crowd-emotion extremes.

Idea `fear-greed-behavioral` (Kahneman-Tversky prospect theory; De Bondt-Thaler
overreaction). Crowds over-react at emotional extremes, so a long-only book should
lean AGAINST them:

  - GREED extreme (fg high — price extended above trend, calm): TRIM the size. This
    protects the operator's rolling one-year-hold cohorts, which otherwise buy near a
    euphoric top and sit underwater a year later.
  - FEAR extreme (fg low — price below trend, turbulent): gently PRESS the size. Because
    the trend/breadth gates run first, a name only reaches here on a pullback INSIDE an
    uptrend — a dip to buy, never a falling knife in a confirmed bear.

`infer._causal_feargreed` writes the causal per-bar fg channel in [0,1] (0.5 neutral).
This module maps it to a size multiplier composed (by product) with the other sizing
modules. `feargreed` is the lever strength (0 = off -> the module abstains, so an
off-by-default config backtests identically to the pre-sentiment path).
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput

GREED_HI = 0.75   # above this fg = greedy -> trim
FEAR_LO = 0.25    # below this fg = fearful -> press
MAX_TRIM = 0.50   # deepest trim (size x0.5) at full greed, full strength
MAX_PRESS = 0.30  # largest press (size x1.3) at full fear, full strength


class Sentiment:
    def __init__(self, feargreed: float = 0.0):
        self.name = "sentiment"
        self.weight = 0.0  # sizes only; never votes direction, never vetoes
        self.strength = float(feargreed)

    def reset(self) -> None:
        pass

    def _mult(self, fg: float) -> float:
        if fg > GREED_HI:
            frac = (fg - GREED_HI) / (1.0 - GREED_HI)
            return 1.0 - self.strength * MAX_TRIM * frac
        if fg < FEAR_LO:
            frac = (FEAR_LO - fg) / FEAR_LO
            return 1.0 + self.strength * MAX_PRESS * frac
        return 1.0

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.strength <= 0:
            return out
        ch, ns = view.channels, view.ns
        for symbol in view.candles:
            fg = ch.feargreed(symbol, ns)
            if fg is None:
                continue
            mult = self._mult(float(fg))
            if mult != 1.0:
                out.vote(symbol, size_mult=max(0.5, min(1.3, mult)))
        return out
