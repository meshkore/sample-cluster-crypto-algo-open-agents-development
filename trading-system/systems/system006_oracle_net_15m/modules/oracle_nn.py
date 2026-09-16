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

`trend_soft` turns that veto from a wall into a dimmer, and it exists because of a
measured diagnosis rather than a hunch. The strategy's worst calendar years are the
bear and sideways ones, and in those this veto holds average exposure between one and
nine percent — the entire defence is to stop trading. A defence of "stay flat" bounds
the worst year near ZERO by construction: it cannot lose much, and it cannot earn
anything either. That is why every sizing, gating and money-management lever tested so
far moved the result so little; they all act on trades the system chooses to take, and
none can produce a return in a year when the book is deliberately empty.

With `trend_soft > 0` a down-trend name is no longer refused: it may be entered at that
fraction of normal size. Zero keeps the wall exactly as it was, so the default is
byte-identical to every result on record.
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput


class OracleNN:
    """Directional conviction from the trained net's precomputed probabilities."""

    def __init__(self, weight: float = 1.0, trend_soft: float = 0.0):
        self.name = "oracle-nn"
        self.weight = float(weight)
        # 0.0 = the trend bit is a hard veto (unchanged behaviour); >0 = enter anyway at
        # this fraction of normal size. Bounded at 1.0: this lever exists to trade the
        # flat years SMALL, never to trade them larger than an uptrend.
        self.trend_soft = min(max(float(trend_soft), 0.0), 1.0)

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
            down = not ch.uptrend(symbol, ns)
            if down and self.trend_soft > 0:
                out.vote(symbol, conviction=conviction, veto=False,
                         size_mult=self.trend_soft)
            else:
                out.vote(symbol, conviction=conviction, veto=down)
        return out
