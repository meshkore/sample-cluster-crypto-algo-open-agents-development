"""What the book actually bets on: the return spread between the extremes.

The information coefficient measures a linear relationship across the whole cross-section.
This book does not bet on that. It buys the top quarter by residual momentum and sells the
bottom quarter, so what pays it is the SPREAD between those two groups over the holding
period - and a signal can deliver that while the middle contributes nothing to the
correlation, which is exactly what the IC table implied.

2026 is the case that forced this: its IC is POSITIVE at 0.030, and the book's asset leg
still lost 11.0%. Those two facts are only compatible if the extremes behaved differently
from the centre. This measures the extremes directly, per year, so 2026 can be compared
against eight years the book survived.

Reported per year: the mean holding-period return of the top quarter, of the bottom quarter,
and the spread the book would have earned from being long the first and short the second.
Nothing here is optimised and no configuration is chosen.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "trading-system")

import quantlab_catalog as cat
from quantlab_catalog.paths import universe_file
from quantlab_system08 import residual as R
from quantlab_system08 import signal as S

WINDOW, LOOKBACK, SKIP, HOLD = 35, 18, 1, 14
SIDE = 0.25
MIN_HISTORY = 365


def compounded(series, days, i, n):
    if i - n < 0:
        return None
    acc = 1.0
    for d in days[i - n:i]:
        v = series.get(d)
        if v is None:
            return None
        acc *= (1.0 + v)
    return acc - 1.0


def main(universe: str = "universe_wide.json") -> int:
    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    syms = [str(s) for s in meta["symbols"]]
    bars = {s: b for s, b in cat.candles(syms, include_sealed=True).items() if b}
    rets = {s: R.simple_returns(R.daily_closes(b)) for s, b in bars.items()}
    rets = {s: v for s, v in rets.items() if v}

    factors = R.market_ex_self(sorted(rets))
    loads = R.residuals(rets, factors=factors, window=WINDOW)
    eps = R.residual_series(rets, loads, factors=factors)

    all_days = sorted({d for v in rets.values() for d in v})
    first = min(min(p) for p in loads.values())
    start = all_days.index(first) if first in all_days else 0
    reb_days = all_days[start::HOLD]
    idx = {d: i for i, d in enumerate(all_days)}

    rows = defaultdict(list)
    for day in reb_days:
        seasoned = S.seasoned_names(rets, day, MIN_HISTORY)
        scores = {}
        for sym in seasoned:
            sc = S.residual_momentum(eps.get(sym, {}), day, lookback=LOOKBACK, skip=SKIP)
            if sc is not None:
                scores[sym] = sc
        if len(scores) < 8:
            continue
        ranked = sorted(scores, key=lambda s: scores[s], reverse=True)
        k = max(2, int(len(ranked) * SIDE))
        i = idx[day]
        # The RAW forward return over the holding period, which is what the book earns.
        def fwd(sym):
            return compounded(rets.get(sym, {}), all_days, i + HOLD, HOLD)
        top = [fwd(s) for s in ranked[:k]]
        bot = [fwd(s) for s in ranked[-k:]]
        top = [v for v in top if v is not None]
        bot = [v for v in bot if v is not None]
        if len(top) < 2 or len(bot) < 2:
            continue
        rows[day[:4]].append((float(np.mean(top)), float(np.mean(bot))))

    print(f"{'year':<6}{'top q':>10}{'bottom q':>11}{'SPREAD':>10}{'rebals':>8}")
    for year in sorted(rows):
        t = float(np.mean([r[0] for r in rows[year]]))
        b = float(np.mean([r[1] for r in rows[year]]))
        print(f"{year:<6}{t:>10.4f}{b:>11.4f}{t - b:>10.4f}{len(rows[year]):>8}")
    print("\nThe book is long the top quarter and short the bottom quarter, so the SPREAD")
    print("column is its raw material. A negative spread means the ranking inverted.")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
