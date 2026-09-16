"""Size from the distance to the drawdown limit, instead of trading full size into a cliff.

Idea A55, and the principled answer to the operator's instruction of 2026-08-28: minimise
drawdown, do not bound it. The book currently carries a constant fraction until equity
falls far enough to trip a hard abort, at which point it stops for the rest of the year.
That cliff is expensive in a measurable way - P09 found that raising the deployment ceiling
collapses above 0.50 not because the market punishes size but because the abort forfeits
2021, a year worth 227 points more than the alternative.

Grossman and Zhou's result for growth under a maximum-drawdown constraint is to invest in
proportion to the EXCESS above a moving floor. Written in terms this book already tracks,
with `m` the mandate and `dd` the current peak-to-trough fall:

    floor    = peak * (1 - m)
    headroom = (equity - floor) / (peak - floor) = 1 - dd / m

so headroom is 1 at a new high and 0 at the limit. The multiplier follows it, which means
size is withdrawn SMOOTHLY as trouble approaches rather than all at once on arrival - and
restored as the account recovers, which an abort never does.

TWO HONEST LIMITS, both from tracing the arithmetic rather than assuming it:

  * The orchestrator computes `deployed = min(1.0, max(0.05, base * deploy_mult))`, so a
    5% floor is applied AFTER this module. It can taper the book but cannot flatten it -
    the abort remains the only thing that fully stops trading, and this is a complement to
    it, not a replacement.
  * `power` above 1 makes the taper convex, cutting size early and gently; below 1 makes it
    concave, holding size until late. Which is right is an empirical question, not a
    theoretical one, so it is a swept lever rather than a fixed choice.
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput


class DrawdownSizer:
    def __init__(self, dd_sizer: float = 0.0, max_drawdown: float = 0.25,
                 floor_mult: float = 0.10):
        self.name = "drawdown-sizer"
        self.weight = 0.0            # never votes direction; scales the book only
        self.dd_sizer = float(dd_sizer)      # 0 = off; >0 = the taper's power
        self.max_drawdown = float(max_drawdown)
        self.floor_mult = float(floor_mult)  # never shrink below this multiple
        self._peak = 0.0

    def reset(self) -> None:
        # Per-year accounts are independent, so the high-water mark must reset with them.
        self._peak = 0.0

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.dd_sizer <= 0 or self.max_drawdown <= 0:
            return out
        equity = float(view.equity)
        if equity <= 0:
            return out
        self._peak = max(self._peak, equity)
        if self._peak <= 0:
            return out
        dd = 1.0 - equity / self._peak
        headroom = 1.0 - dd / self.max_drawdown
        headroom = min(1.0, max(0.0, headroom))
        mult = headroom ** self.dd_sizer
        mult = max(self.floor_mult, min(1.0, mult))
        out.deploy_mult = mult
        if mult < 0.999:
            out.note = f"drawdown {dd * 100:.1f}% of a {self.max_drawdown * 100:.0f}% limit -> deploy x{mult:.2f}"
        return out
