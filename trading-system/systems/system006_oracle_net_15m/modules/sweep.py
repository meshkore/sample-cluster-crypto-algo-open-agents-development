"""Market-maker liquidation hunt: lean into the bar after a two-sided stop sweep.

Idea `liquidation-hunt` (operator, 2026-08-25). A market maker that clears both sides
of the book prints a recognisable bar — long upper AND lower wicks around a small body,
heavy volume, an unusually wide range. Stops above and below have just been run, the
weak hands are out, and price frequently reverses out of that cleanup. The operator
recognises these visually; `infer._causal_sweep` turns the same geometry into a causal
per-bar score.

This module reads that score and, on a name the rest of the stack already wants to
enter, UPSIZES the position when the sweep just fired — buying the post-cleanup bounce
rather than the move into it. Long-only, so it only ever leans into the recovery side.

Safe by construction, exactly like `horserace`: it returns a bounded size multiplier
for names the ensemble already chose, never forces an entry and never vetoes. Off
(`sweep <= 0`) -> abstains entirely, so an off-by-default config backtests identically
to the pre-sweep path.

The anticipatory half of the operator's idea — refusing entries when a sweep looks DUE
(long quiet period plus volume build-up) — is deliberately not wired here: it would gate
entries on a prediction rather than an observation. It stays on the agenda (A31) as the
follow-up once this observational half has an honest verdict.
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput

MAX_PRESS = 0.30  # largest upsize (x1.3) on a full-strength sweep at full lever strength


class Sweep:
    def __init__(self, sweep: float = 0.0, gate: float = 0.25):
        self.name = "sweep"
        self.weight = 0.0  # sizes only; never votes direction, never vetoes
        self.strength = float(sweep)
        self.gate = float(gate)

    def reset(self) -> None:
        pass

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.strength <= 0:
            return out
        ch, ns = view.channels, view.ns
        pressed = 0
        for symbol in view.candles:
            score = ch.sweep(symbol, ns)
            if score is None or score < self.gate:
                continue
            # Scale the press by how far past the gate the sweep fired, so a marginal
            # bar barely moves size and a violent two-sided cleanup moves it most.
            span = max(1e-9, 1.0 - self.gate)
            frac = min(1.0, (float(score) - self.gate) / span)
            out.vote(symbol, size_mult=1.0 + self.strength * MAX_PRESS * frac)
            pressed += 1
        if pressed:
            out.note = f"sweep: {pressed} name(s) upsized after a two-sided liquidity sweep"
        return out
