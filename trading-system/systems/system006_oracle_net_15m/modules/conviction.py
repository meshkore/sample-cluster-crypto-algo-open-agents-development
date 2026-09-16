"""Size by certainty: a trade the model is sure about gets more capital than a marginal one.

The operator's original request (2026-08-29): "cuando tengamos operaciones muy seguras,
aumentamos el valor de las inversiones, y cuando las operaciones son más dudosas... se
reduce el tamaño". The book already RANKS by conviction - scarce slots go to the highest
scorer - but every accepted trade then gets the same notional, so a 0.99 and a 0.76 are
funded identically once both are in.

This is the missing piece, and it is the classical one: Kelly says stake in proportion
to edge. Here the edge proxy is how far the conviction clears the entry bar, mapped
linearly onto a bounded multiplier:

    edge   = (conviction - enter) / (1 - enter)        # 0 at the bar, 1 at certainty
    mult   = 1 + strength * (2 * edge - 1)             # 1-strength .. 1+strength

so `conviction_sizing = 0.3` funds a barely-passing trade at 0.7x and a near-certain one
at 1.3x, with the average unchanged - it REDISTRIBUTES capital across accepted trades
rather than adding exposure. That distinction matters: every lever that added exposure by
admitting worse trades has been refuted here (looser filters, extra slots, soft trend,
late pyramiding), while the one that redistributed by expectancy (the learned money model)
is the largest measured win in the project.

Note what this does NOT do: it never adds after entry. P25 measured that adding at +3%
buys the late part of a move, when conviction has already decayed - so this acts once,
at the moment the evidence is freshest.

Off (`conviction_sizing = 0`, the default) -> abstains entirely.
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput

FLOOR = 0.4     # never fund a trade below this fraction of the equal-weight size
CAP = 1.8       # nor above this - a bounded tilt, not a concentration bet


class Conviction:
    """Sizes by certainty, centred on the convictions the book ACTUALLY sees.

    The first version centred the tilt on the midpoint of the theoretical range
    (enter..1.0) and lost, dose-ordered, with exposure falling 7.88% -> 5.69%. The
    measurement named the flaw: unbiased over the RANGE is not unbiased over the
    POPULATION. Accepted entries cluster just above the bar, so a tilt centred on
    the midpoint shrinks nearly all of them - it was a de-facto exposure cut wearing
    a redistribution's clothes, and cutting exposure has lost every time here.

    So the centre is now learned from the book's own history, causally: a rolling
    median of the convictions it has actually accepted. No fitted constant, no
    lookahead - early bars simply run untilted until the window fills.
    """

    def __init__(self, conviction_sizing: float = 0.0, enter: float = 0.75,
                 window: int = 200, warmup: int = 30):
        self.name = "conviction"
        self.weight = 0.0                     # sizing only; never votes direction
        self.strength = float(conviction_sizing)
        self.enter = float(enter)
        self.window = int(window)
        self.warmup = int(warmup)
        self._seen: list[float] = []

    def reset(self) -> None:
        self._seen = []

    def _centre(self) -> float | None:
        if len(self._seen) < self.warmup:
            return None                        # not enough history to centre honestly
        ordered = sorted(self._seen)
        return ordered[len(ordered) // 2]

    def observe(self, conviction: float) -> None:
        self._seen.append(conviction)
        if len(self._seen) > self.window:
            del self._seen[0]

    def multiplier(self, conviction: float, centre: float | None = None) -> float:
        centre = self._centre() if centre is None else centre
        if centre is None:
            return 1.0
        # Distance from the median accepted conviction, scaled by the room above the
        # bar. Positive above the median, negative below - so the tilt redistributes
        # around what this book really trades rather than around an abstract midpoint.
        span = max(1.0 - self.enter, 1e-9)
        edge = (conviction - centre) / span
        mult = 1.0 + self.strength * 2.0 * edge
        return min(max(mult, FLOOR), CAP)

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.strength <= 0:
            return out
        ch, ns = view.channels, view.ns
        sized = 0
        for symbol in view.candles:
            if symbol in view.held:
                continue                      # entries only - never re-sizes a position
            conviction = ch.prob(symbol, ns)
            if conviction < self.enter:
                continue                      # not a candidate; other modules will refuse it
            self.observe(conviction)
            mult = self.multiplier(conviction)
            if mult != 1.0:
                out.vote(symbol, size_mult=mult)
                sized += 1
        if sized:
            out.note = f"conviction: sized {sized} candidate(s) by certainty"
        return out
