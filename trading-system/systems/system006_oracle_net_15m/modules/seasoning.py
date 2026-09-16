"""Seasoning: a symbol is not tradable until IT has enough history at that moment.

The universe screen already demands ~4.4 years of history - but it asks that
question TODAY, once, for the whole backtest. That is a subtly different question
from the one a live book faces at each bar, and the difference is measurable: in
the 2019 and 2020 walk-forward cutoffs, and again in 2018 for the full-history
candidate, the wide universe lost badly, and those are exactly the years when
most of its symbols were freshly listed. A coin that has 4 years of history in
2026 had four MONTHS of it in 2018, and the book was trading it as if the screen
had vetted it.

This module asks the causal version of the question: at THIS bar, how much of its
own history does this symbol have? Below `min_age_days` it is vetoed. Nothing is
fitted to a particular year - the rule is the same one the universe screen already
believes in, applied at the right time.

Age is measured from the symbol's first signal bar, which is the first thing the
book could have known about it. Off (`min_age_days <= 0`, the default) -> abstains.
"""

from __future__ import annotations

from .base import MarketView, ModuleOutput

NS_PER_DAY = 86_400_000_000_000


class Seasoning:
    def __init__(self, min_age_days: float = 0.0):
        self.name = "seasoning"
        self.weight = 0.0                 # a veto module: never votes direction
        self.min_age_days = float(min_age_days)
        self._first: dict[str, int] = {}  # symbol -> first known bar, cached

    def reset(self) -> None:
        pass                              # the cache is a property of the data, not the run

    def _first_ns(self, view: MarketView, symbol: str) -> int | None:
        if symbol not in self._first:
            table = getattr(view.channels, "_table", {}).get(symbol) or {}
            prob = table.get("prob") or {}
            self._first[symbol] = min(prob) if prob else None
        return self._first[symbol]

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.min_age_days <= 0:
            return out
        need = self.min_age_days * NS_PER_DAY
        vetoed = 0
        for symbol in view.candles:
            first = self._first_ns(view, symbol)
            if first is None:
                continue                  # no signal history at all -> other modules abstain too
            if view.ns - first < need:
                out.vote(symbol, veto=True)
                vetoed += 1
        if vetoed:
            out.note = (f"seasoning: {vetoed} name(s) too young "
                        f"(< {self.min_age_days:.0f}d of own history)")
        return out
