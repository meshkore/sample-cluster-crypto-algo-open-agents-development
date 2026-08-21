"""The neural-net expert: the TCN's per-bar conviction, as a module.

This is the primary directional module — the thing every earlier generation of
system 06 *was*. It carries no torch and no feature code: `infer.py` already ran
the net over every bar and wrote one probability per (symbol, bar) into the
channel table. Here we just read it.

Its opinion per symbol:
  - conviction = the model's probability of an up-swing (0..1),
  - veto = the causal slow-trend bit is DOWN — the model may like a name while the
    broad trend is against it; the trend bit keeps it out of the book. This is an
    ENTRY filter only (the orchestrator never force-exits on it), matching the
    long-standing finding that force-exiting a 15 m long book on every trend wobble
    churns it to death.
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput


class OracleNN:
    """Directional conviction from the trained net's precomputed probabilities."""

    def __init__(self, weight: float = 1.0):
        self.name = "oracle-nn"
        self.weight = float(weight)

    def reset(self) -> None:
        # Stateless: the whole model lives in the channel table, computed offline.
        pass

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        ch, ns = view.channels, view.ns
        for symbol in view.candles:
            conviction = ch.prob(symbol, ns)
            if conviction <= 0.0:
                continue  # abstain on names the model has no live signal for
            out.vote(symbol, conviction=conviction, veto=not ch.uptrend(symbol, ns))
        return out
