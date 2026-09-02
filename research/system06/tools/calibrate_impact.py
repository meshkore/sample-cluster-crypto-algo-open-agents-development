"""Calibrate IMPACT_BPS from this universe's own liquidity, instead of guessing it.

    PYTHONPATH=trading-system python research/system06/tools/calibrate_impact.py

The square-root impact law says cost_bps = k * sqrt(participation). We need k. Rather
than importing a number from a paper written about equities, measure the market's own
response in our own candles: within each symbol, regress the bar's realised range
against how much value traded in it, and read off how many bps the price typically
moves when a bar's volume is fully consumed.

The estimator, deliberately crude and conservative:

  For each symbol, take bars with volume, compute range_bps = (high-low)/open * 10000
  and traded value. A bar that trades V and moves R bps means the market absorbed V
  for R bps of movement. An order that IS the whole bar therefore expects an impact on
  the order of the median bar's range - so k ~ median(range_bps) is a defensible
  anchor for "what it costs to be the entire bar", which is exactly what impact_bps
  is defined as.

We then take the MEDIAN across symbols and round up, because being wrong in the
direction of overcharging ourselves is the only safe direction to be wrong in.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"


def main() -> int:
    sys.path.insert(0, "trading-system")
    from quantlab_system06 import universe
    from quantlab_system06.dataset import Dataset

    symbols = universe.load()
    ds = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    bars = ds.combined()

    rows = {}
    for sym, series in bars.items():
        o = np.array([b.open for b in series], float)
        h = np.array([b.high for b in series], float)
        lo = np.array([b.low for b in series], float)
        c = np.array([b.close for b in series], float)
        v = np.array([getattr(b, "volume", 0.0) for b in series], float)
        value = c * v
        ok = (v > 0) & (o > 0)
        if ok.sum() < 1000:
            continue
        rng_bps = (h[ok] - lo[ok]) / o[ok] * 10_000.0
        rows[sym] = {
            "median_range_bps": float(np.median(rng_bps)),
            "median_bar_value_usd": float(np.median(value[ok])),
            "p10_bar_value_usd": float(np.percentile(value[ok], 10)),
            "bars": int(ok.sum()),
        }

    med = float(np.median([r["median_range_bps"] for r in rows.values()]))
    print(f"{'symbol':>10} {'median range':>13} {'median bar $':>15} {'p10 bar $':>13}")
    for sym, r in sorted(rows.items(), key=lambda kv: -kv[1]["median_bar_value_usd"]):
        print(f"{sym:>10} {r['median_range_bps']:>12.1f}b {r['median_bar_value_usd']:>14,.0f} "
              f"{r['p10_bar_value_usd']:>12,.0f}")
    k = float(np.ceil(med / 5.0) * 5.0)
    print(f"\nmedian bar range across symbols: {med:.1f} bps -> IMPACT_BPS = {k:.0f}")
    print("Read: an order equal to a whole 15m bar's volume pays about one bar's range,")
    print("which is what moving the entire book through a candle costs. At 1% of a bar")
    print(f"it costs {k * 0.1:.1f} bps, at 0.1% about {k * 0.0316:.1f} bps.")

    out = ROOT / "rnd" / "impact_calibration.json"
    out.write_text(json.dumps({"per_symbol": rows, "median_range_bps": med,
                               "impact_bps": k}, indent=1), encoding="utf-8")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
