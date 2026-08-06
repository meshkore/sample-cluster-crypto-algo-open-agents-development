"""Which assets are FINISHED? Volume-based terminal-decline detection.

The operator's idea: inside a bear market, some assets are simply over -- no
bounce is worth taking -- and volume should say which. Testing that directly.

Split: TRAIN <=2021-12-31, HOLDOUT 2022-01-01..2025-12-31 (contains the whole
2022 bear). 2026 is not opened anywhere in this file.

For every liquid asset on every bear-regime day, measure forward returns
conditional on volume-decay and structure conditions, separately on train and
holdout. A condition that only works on train is noise.
"""

import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "src")

from quantlab.data import DataManager
from quantlab.regime import REFERENCE_BASKET, MarketRegime, build_market_timeline

RES = (
    Path.home() / "Library/Application Support/QuantLab/data/research/processed/binance"
)
LIQ = 10_000_000.0
CUTOFF = datetime(2026, 1, 1)
SPLIT = datetime(2022, 1, 1)
HORIZONS = (7, 30)


def load(symbol):
    d = RES / symbol / "1d"
    files = (
        sorted(d.glob("*.csv"), key=lambda p: p.stat().st_size) if d.is_dir() else []
    )
    if not files:
        return [], []
    days, rows = [], []
    with files[-1].open() as fh:
        for r in csv.DictReader(fh):
            s = datetime.fromisoformat(r["timestamp"]).replace(tzinfo=None)
            if s >= CUTOFF:
                continue
            days.append(s)
            rows.append((float(r["close"]), float(r["volume"]), float(r["high"])))
    return days, rows


assets = {}
for sym in sorted(p.name for p in RES.iterdir() if (p / "1d").is_dir()):
    d, r = load(sym)
    if len(d) >= 300:
        assets[sym] = (d, r)

basket = {}
for s in REFERENCE_BASKET:
    dd = RES / s / "1d"
    f = sorted(dd.glob("*.csv"), key=lambda p: p.stat().st_size)
    if f:
        basket[s] = [b for b in DataManager.load_csv(f[-1]) if b.timestamp.year < 2026]
tl = build_market_timeline(basket)
labels = {
    s.replace(tzinfo=None).date(): label for s, label in zip(tl.stamps, tl.labels)
}
print(f"{len(assets)} assets; train <=2021, holdout 2022-2025\n", flush=True)


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


buckets = defaultdict(lambda: [0, 0.0, 0])
for sym, (days, rows) in assets.items():
    closes = [r[0] for r in rows]
    vols = [r[0] * r[1] for r in rows]  # dollar turnover
    highs = [r[2] for r in rows]
    for i, day in enumerate(days):
        if i < 200 or i + max(HORIZONS) >= len(days):
            continue
        if labels.get(day.date()) is not MarketRegime.BEAR:
            continue
        recent = vols[i - 19 : i + 1]
        if mean(recent) < LIQ:
            continue
        era = "train" if day < SPLIT else "holdout"

        # Volume decay: turnover now versus turnover 3 months ago.
        older = vols[i - 89 : i - 69]
        decay = mean(recent) / mean(older) if mean(older) else 1.0
        # Structure: distance below the asset's own 200-day high.
        below = closes[i] / max(highs[i - 199 : i + 1]) - 1
        # Persistent lower highs: is the recent high under the older high?
        lower_highs = max(highs[i - 29 : i + 1]) < max(highs[i - 89 : i - 29])

        conds = {
            "all bear days": True,
            "volume decayed <0.5x": decay < 0.5,
            "volume decayed <0.8x": decay < 0.8,
            "volume EXPANDING >1.5x": decay > 1.5,
            "down >80% from 200d high": below <= -0.80,
            "down >60% from 200d high": below <= -0.60,
            "lower highs": lower_highs,
            "DEAD: decay<0.5 AND lower highs": decay < 0.5 and lower_highs,
            "ALIVE: decay>1.2 AND not lower highs": decay > 1.2 and not lower_highs,
        }
        for name, ok in conds.items():
            if not ok:
                continue
            for h in HORIZONS:
                fwd = closes[i + h] / closes[i] - 1
                e = buckets[(era, name, h)]
                e[0] += 1
                e[1] += fwd
                e[2] += fwd > 0

for h in HORIZONS:
    print(f"=== inside BEAR, forward {h}d — TRAIN (<=2021) vs HOLDOUT (2022-25)")
    print(f"{'condition':38s}{'TRAIN':>26s}{'HOLDOUT':>26s}")
    for name in (
        "all bear days",
        "volume decayed <0.5x",
        "volume decayed <0.8x",
        "volume EXPANDING >1.5x",
        "down >60% from 200d high",
        "down >80% from 200d high",
        "lower highs",
        "DEAD: decay<0.5 AND lower highs",
        "ALIVE: decay>1.2 AND not lower highs",
    ):
        row = f"{name:38s}"
        for era in ("train", "holdout"):
            n, tot, w = buckets[(era, name, h)]
            row += f"{tot / n:+9.2%} {n:8d} {w / n:4.0%}" if n else f"{'-':>26s}"
        print(row)
    print()
