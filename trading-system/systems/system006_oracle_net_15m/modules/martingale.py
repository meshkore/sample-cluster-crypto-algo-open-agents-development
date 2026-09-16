"""Martingale: a bounded, optional, occasional press INTO a shallow dip.

The operator asked to see a variant that uses "alguna especie de martingala,
ocasional y opcional". A classic martingale doubles into losses and guarantees
ruin, so this is the disciplined, research-only cousin of it — and it is OFF by
default (`step = 0`).

It is the mirror image of the money module's anti-martingale, with a hard safety
rail. Reading only the account's own equity versus a slow EMA (its "trend"):

  - **shallow dip** (equity a little below its trend): press deployment UP by up to
    `step`, betting the pullback reverts. This is the martingale — add after a loss.
  - **deep dip** (drawdown beyond `floor_dd`): STAND DOWN — the multiplier snaps
    back to 1.0. A real drawdown is exactly where a naive martingale doubles down
    and dies; here we refuse to. The orchestrator's 25 % peak-to-trough mandate is
    the hard backstop underneath, untouched.
  - **at/above trend**: neutral (1.0). The press only ever acts in a controlled dip,
    is capped at `cap`, and can never scale the book DOWN — that is the regime and
    money modules' job, not this one's.

Off (`step = 0`, the default) → abstains entirely. Long-only, research software:
this changes position SIZE within the deploy clamp, never leverage or shorts.
"""

from __future__ import annotations

import math

from .base import MarketView, ModuleOutput


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class Martingale:
    def __init__(self, step: float = 0.0, span: float = 192.0,
                 cap: float = 1.35, floor_dd: float = 0.12, gain: float = 12.0):
        self.name = "martingale"
        self.weight = 0.0  # deployment sizing only, no direction
        self.step = float(step)
        self.span = float(span)
        self.cap = float(cap)
        self.floor_dd = float(floor_dd)
        self.gain = float(gain)
        self._eq_level: float | None = None  # slow EMA of equity = the trend we dip below

    def reset(self) -> None:
        self._eq_level = None

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.step <= 0:
            return out
        eq = view.equity
        if eq <= 0:
            return out
        if self._eq_level is None:
            self._eq_level = eq
            return out
        alpha = 2.0 / (self.span + 1.0)
        ratio = eq / self._eq_level - 1.0
        self._eq_level = alpha * eq + (1.0 - alpha) * self._eq_level
        dip = max(0.0, -ratio)                       # how far below trend we are
        if dip > self.floor_dd:                      # too deep — refuse to martingale
            mult = 1.0
        else:
            mult = 1.0 + self.step * math.tanh(self.gain * dip)
        out.deploy_mult = _clamp(mult, 1.0, self.cap)
        if out.deploy_mult > 1.0:
            out.note = f"pressing a {dip*100:.1f}% dip ×{out.deploy_mult:.2f}"
        return out
