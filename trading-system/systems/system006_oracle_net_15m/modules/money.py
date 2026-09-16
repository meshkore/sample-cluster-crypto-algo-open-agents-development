"""Money management: size by conviction of profit, and press winners — never losers.

Two bounded, research-grounded levers, both off by default:

  - **Fractional Kelly** (`kelly`): the meta model already estimates each entry's
    expected net return. Kelly says stake in proportion to edge; here the per-name
    size multiplier tilts up for the highest-edge entries and down for the barely-
    passing ones, blended by `kelly` (a fraction of full Kelly — full Kelly is famously
    too aggressive, so we take a slice of it) and clamped to [`kelly_lo`, `kelly_hi`].
    Needs the meta channel; abstains on names without a verdict.

  - **Anti-martingale deploy** (`pyramid`): scale the book's deployment UP when the
    account is above its own trend (a winning streak — press with the market's money)
    and DOWN when below it (a losing streak — retreat). This is the OPPOSITE of a
    martingale, which doubles into losses and guarantees ruin; the multiplier can only
    fall below 1 when equity is under its trend, never rise there. Bounded to
    [`pyramid_lo`, `pyramid_hi`], and the 25 % mandate is the hard floor underneath.

Off (`kelly = 0` and `pyramid = 0`, the defaults) → abstains entirely.
"""

from __future__ import annotations

import math

from .base import MarketView, ModuleOutput


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class Money:
    def __init__(self, kelly: float = 0.0, kelly_ref: float = 0.02,
                 kelly_lo: float = 0.5, kelly_hi: float = 1.6,
                 pyramid: float = 0.0, pyramid_span: float = 192.0,
                 pyramid_lo: float = 0.7, pyramid_hi: float = 1.15):
        self.name = "money"
        self.weight = 0.0  # sizing/deployment only, no direction
        self.kelly = float(kelly)
        self.kelly_ref = float(kelly_ref)
        self.kelly_lo = float(kelly_lo)
        self.kelly_hi = float(kelly_hi)
        self.pyramid = float(pyramid)
        self.pyramid_span = float(pyramid_span)
        self.pyramid_lo = float(pyramid_lo)
        self.pyramid_hi = float(pyramid_hi)
        self._eq_level: float | None = None  # slow EMA of equity, the "trend" to press/retreat from

    def reset(self) -> None:
        self._eq_level = None

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()

        # Fractional-Kelly per-name tilt from the meta expected-net edge.
        if self.kelly > 0:
            ch, ns = view.channels, view.ns
            for symbol in view.candles:
                edge = ch.meta(symbol, ns)
                if edge is None:
                    continue
                tilt = _clamp(edge / self.kelly_ref, self.kelly_lo, self.kelly_hi)
                out.vote(symbol, size_mult=1.0 + self.kelly * (tilt - 1.0))

        # Anti-martingale book deployment from the account's own trend.
        if self.pyramid > 0:
            eq = view.equity
            if eq > 0:
                if self._eq_level is None:
                    self._eq_level = eq
                else:
                    alpha = 2.0 / (self.pyramid_span + 1.0)
                    ratio = eq / self._eq_level - 1.0
                    self._eq_level = alpha * eq + (1.0 - alpha) * self._eq_level
                    mult = 1.0 + self.pyramid * math.tanh(10.0 * ratio)
                    out.deploy_mult = _clamp(mult, self.pyramid_lo, self.pyramid_hi)
        return out
