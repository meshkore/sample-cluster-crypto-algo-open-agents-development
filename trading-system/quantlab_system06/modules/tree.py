"""The decision-tree voter: a second, independent directional opinion.

Operator idea A32. Every other module in this system either scales size or vetoes —
only `oracle_nn` ever says "I want to be long this name". That is why `consensus_k >= 2`
has been a no-op-that-kills since A12, and why the sizing modules cannot rescue a year
like sealed 2026, where the oracle's trades are simply break-even: multiplying a
zero-edge position by 1.3 leaves zero edge.

This module is the second voter. `tree.py` fits a gradient-boosted tree on candlestick
shapes and probabilistic statistics — different features, a different label and a
different inductive bias from the TCN — and publishes a causal, walk-forward P(up) per
bar. Here that probability becomes a conviction, so the orchestrator's weighted vote
combines two genuinely different disciplines instead of amplifying one.

`weight` is the lever: 0 disables the vote entirely (the module abstains and the system
behaves exactly as before), and a positive weight gives the tree that much say against
the oracle's weight of 1.0. Bars with no verdict — the walk-forward's first training
block — are abstained on rather than guessed.
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput


class Tree:
    def __init__(self, tree_weight: float = 0.0):
        self.name = "tree"
        self.weight = float(tree_weight)   # >0 -> its conviction joins the directional vote

    def reset(self) -> None:
        pass

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.weight <= 0:
            return out
        ch, ns = view.channels, view.ns
        voted = 0
        for symbol in view.candles:
            prob = ch.tree(symbol, ns)
            if prob is None:
                continue          # no walk-forward verdict for this bar -> abstain
            out.vote(symbol, conviction=float(prob))
            voted += 1
        if voted:
            out.note = f"tree: voted on {voted} name(s)"
        return out
