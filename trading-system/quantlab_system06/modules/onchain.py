"""Network-activity gate: refuse new entries when the chain itself is unusually quiet.

The second non-price input (A70), and it earns its place by NOT being the first one:
measured against the Fear & Greed index the shipping book already uses, the two agree
only weakly (correlation +0.20; just 31% of the days this gate would block are already
blocked by fear). Two vetoes firing on the same days would be one veto with twice the
machinery - these are different days.

What it reads: the number of unique addresses transacting on the Bitcoin chain,
published daily, as a DEVIATION FROM ITS OWN TRAILING TREND. The level says nothing
tradable - the chain has grown for fifteen years - but "activity is unusually weak for
this period" is a statement about demand that price alone does not carry. On the
champion's 3,329 round trips it stratified monotonically: the weakest quartile returned
+0.107% per trade at 39% win, the strongest +0.867% at 47%.

The threshold is a statistical convention, not a fitted value: `activity_min` is a
z-score, and -1.0 is the ordinary "one standard deviation below normal" line. That
matters because the alternative - sweeping thresholds until one looks good on our own
trade map - is how a fold in the data gets mistaken for a signal.

Two honest limits, both recorded rather than smoothed over:
  * the source downsamples long histories to roughly one point every four days, so this
    is a slow regime signal and cannot time anything;
  * it is a BITCOIN-chain measure used to gate a multi-asset book, on the argument that
    chain activity proxies crypto demand generally - an assumption the experiment tests
    rather than assumes.

Causality: a bar reads only values published STRICTLY BEFORE it. Off (`activity_min`
is None, the default) -> the module abstains entirely.
"""

from __future__ import annotations

import bisect
import json
from pathlib import Path

from .base import MarketView, ModuleOutput

from quantlab_catalog.paths import external_file

DATA = external_file("chain_n-unique-addresses.json")
TRAIL = 30            # points of trailing history for the z-score (~4 months at this grid)
CONVENTIONAL = -1.0   # one standard deviation below normal; not fitted to our trades


class OnChain:
    def __init__(self, activity_min: float | None = None, data_path: str | Path = DATA,
                 trail: int = TRAIL):
        self.name = "onchain"
        self.weight = 0.0              # a veto module: never votes direction
        self.activity_min = None if activity_min is None else float(activity_min)
        self._ns: list[int] = []
        self._z: list[float] = []
        if self.activity_min is not None:
            try:
                rows = sorted(json.loads(Path(data_path).read_text(encoding="utf-8")),
                              key=lambda r: int(r["t_s"]))
                vals = [float(r["value"]) for r in rows]
                for i in range(len(vals)):
                    if i < trail:
                        continue
                    window = vals[i - trail:i]
                    mean = sum(window) / trail
                    var = sum((v - mean) ** 2 for v in window) / trail
                    sd = var ** 0.5
                    self._ns.append(int(rows[i]["t_s"]) * 1_000_000_000)
                    self._z.append((vals[i] - mean) / sd if sd > 0 else 0.0)
            except Exception:  # noqa: BLE001 - no feed -> abstain, never crash a run
                self._ns, self._z = [], []

    def reset(self) -> None:
        pass

    def z_at(self, ns: int) -> float | None:
        """The most recent activity z published STRICTLY BEFORE this bar."""
        if not self._ns:
            return None
        i = bisect.bisect_left(self._ns, ns) - 1
        return self._z[i] if i >= 0 else None

    def evaluate(self, view: MarketView) -> ModuleOutput:
        out = ModuleOutput()
        if self.activity_min is None or not self._ns:
            return out
        z = self.z_at(view.ns)
        if z is None or z >= self.activity_min:
            return out
        for symbol in view.candles:
            out.vote(symbol, veto=True)
        out.note = f"onchain: chain activity {z:+.2f}sd below normal - no new entries"
        return out
