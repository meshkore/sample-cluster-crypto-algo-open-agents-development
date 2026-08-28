"""Fractal regime: veto entries when the tape is anti-persistent (choppy).

Idea `hurst-ghe` (Mandelbrot; Di Matteo generalized Hurst). The generalized Hurst
exponent H of log-price separates two regimes a trend-follower must tell apart:

  - H > 0.5  persistent / trending  -> the oracle's swing signal is reliable; enter.
  - H < 0.5  anti-persistent / choppy -> trend-following whipsaws (the bear-chop of
             2018/2022 that breaks the consistency law); keep the name out of the book.

`infer._causal_hurst` writes the causal per-bar H channel; this module reads it and,
when `hurst_gate > 0`, VETOES entering any symbol whose H is known and below the gate.
A veto only keeps a name out — it never force-exits a held position (that belongs to
the stops / regime risk-off, which own capital preservation). The warm-up bars carry
the neutral 0.5, which a sensible gate (< 0.5) never vetoes, so early bars are never
blocked on a fabricated regime call.

Off (`hurst_gate <= 0`) -> the module abstains entirely, so an off-by-default config
has an identical backtest to the pre-fractal path.
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput


class Fractal:
    def __init__(self, hurst_gate: float = 0.0):
        self.name = "fractal"
        self.weight = 0.0  # gates entries only; never votes direction
        self.hurst_gate = float(hurst_gate)

    def reset(self) -> None:
        pass

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.hurst_gate <= 0:
            return out
        ch, ns = view.channels, view.ns
        vetoed = 0
        for symbol in view.candles:
            h = ch.hurst(symbol, ns)
            if h is not None and h < self.hurst_gate:
                out.vote(symbol, veto=True)
                vetoed += 1
        if vetoed:
            out.note = f"fractal: {vetoed} name(s) vetoed (H<{self.hurst_gate:.2f}, choppy)"
        return out
