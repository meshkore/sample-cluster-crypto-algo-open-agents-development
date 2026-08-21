"""Meta-label gate: refuse the primary's entries the secondary model expects to lose.

At a candidate bar (the net's conviction is up and the trend is up), the meta model
has already scored the entry's expected net return — precomputed, honestly, into the
`meta` channel by `quantlab_system06.meta`. This module reads that verdict and vetoes
the entry when it is at or below `margin` (default 0.0 → require a positive expected
edge after costs). Where the meta model has no out-of-sample verdict (the earliest,
train-only candidates), the channel returns None and the module abstains — the primary
stands rather than trading on a leaked verdict.

Off (`margin is None`, the default, or no meta channel) → abstains entirely, so the
ensemble is byte-identical to the pre-meta behaviour until meta is deliberately turned
on and selected on validation (never on 2026).
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput


class Meta:
    def __init__(self, margin: float | None = None):
        self.name = "meta"
        self.weight = 0.0  # a filter: it vetoes, it never votes direction
        self.margin = margin

    def reset(self) -> None:
        pass

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.margin is None:
            return out
        ch, ns = view.channels, view.ns
        for symbol in view.candles:
            verdict = ch.meta(symbol, ns)
            if verdict is not None and verdict <= self.margin:
                out.vote(symbol, veto=True)
        return out
