"""Extreme-fear veto, from the REAL Fear & Greed index (A65, new information).

Measured before built (A65 stage 1, 3,158 champion round trips joined to the
index's previous-day value): entries taken on the most fearful days returned
-0.10% per trade at 34% win, against +0.96% at 48% in the greedy quartile - a
near-monotone gradient, and the only losing bucket in the whole map. A trend
book has no business opening new positions into market-wide panic: its edge is
continuation, and panic days are where continuation breaks.

Note the SIGN. The `sentiment` module (built earlier from a price proxy) is
contrarian - it presses size into fear. On the real index, for this book, that is
backwards; the data says avoid, not press. Both modules exist and both are off by
default; this one is the one with an external measurement behind it.

The threshold is the index's OWN published boundary for "Extreme Fear" (25), not
a value fitted to our trade map - so the lever carries no selection optimism.

Causality: a bar may only read a value published strictly BEFORE it. The index
publishes daily; we take the most recent day whose timestamp is strictly less
than the bar's, so a live bar sees exactly what a backtest bar sees.

Off (`fng_min <= 0`, the default, or no data file) -> the module abstains
entirely, so an off-by-default config is byte-identical to the prior path.
"""

from __future__ import annotations

import bisect
import json
from pathlib import Path

from .base import MarketView, ModuleOutput

from quantlab_catalog.paths import external_file

DATA = external_file("feargreed.json")
EXTREME_FEAR = 25.0        # the index's own published boundary; never fitted here


class Crowd:
    def __init__(self, fng_min: float = 0.0, data_path: str | Path = DATA):
        self.name = "crowd"
        self.weight = 0.0            # a veto module: never votes direction
        self.fng_min = float(fng_min)
        self._ns: list[int] = []
        self._val: list[float] = []
        if self.fng_min > 0:
            try:
                rows = json.loads(Path(data_path).read_text(encoding="utf-8"))
                rows.sort(key=lambda r: int(r["t_s"]))
                self._ns = [int(r["t_s"]) * 1_000_000_000 for r in rows]
                self._val = [float(r["value"]) for r in rows]
            except Exception:  # noqa: BLE001 - no feed -> abstain, never crash the run
                self._ns, self._val = [], []

    def reset(self) -> None:
        pass

    def value_at(self, ns: int) -> float | None:
        """The most recent index value published STRICTLY BEFORE this bar."""
        if not self._ns:
            return None
        i = bisect.bisect_left(self._ns, ns) - 1
        if i < 0:
            return None
        return self._val[i]

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.fng_min <= 0 or not self._ns:
            return out
        fg = self.value_at(view.ns)
        if fg is None or fg >= self.fng_min:
            return out
        for symbol in view.candles:
            out.vote(symbol, veto=True)
        out.note = f"crowd: extreme fear ({fg:.0f} < {self.fng_min:.0f}) - no new entries"
        return out
