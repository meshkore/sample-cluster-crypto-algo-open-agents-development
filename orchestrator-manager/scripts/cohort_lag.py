"""Do the market's segments turn at the same time, or in a queue?

The operator's hypothesis: BTC leads, the major alts follow, the rest of the
alts follow them, and the memecoins come last -- each on a lag of weeks to
months. If that is true it is worth a great deal, because the cohort that turns
FIRST is a leading indicator for the ones that turn later, and the detector
currently averages all of them into one number that can only ever be a lagging
compromise.

This is the FIRST version and it is a measurement, not a strategy. It answers
two questions and stops:

  1. Can cohorts be assigned from the data we hold, without an external
     taxonomy? (We hold OHLCV and nothing else -- no sector labels, no supply,
     no categories.)
  2. Do the cohort composites lead or lag each other, and by how much?

WHAT THE COHORTS ARE, and why they are defined this way. With no external
labels the only signals available are listing date, turnover, and price
behaviour. Two of those carry real information about what kind of coin
something is:

  * LISTING DATE separates the 2017-2020 infrastructure era from the
    2021+ retail era and the 2023+ memecoin wave almost cleanly, because
    exchanges list what is being issued.
  * TURNOVER separates what institutions hold from what does not clear.

The `1000` prefix Binance uses for very low unit prices (1000PEPE, 1000CAT,
1000CHEEMS) is a genuine third signal and is reported, but there are only three
in this archive, so it is evidence and not a cohort.

Nothing here is asserted to BE a memecoin index. These are cohorts by age and
size, which is what the data supports, and the naming says so.

    python3 orchestrator-manager/scripts/cohort_lag.py
"""

from __future__ import annotations

import math
import sys
from datetime import datetime
from statistics import median

from market_shootout import composite, load_all, turnover_averages

# Where the eras are cut. Chosen from the listing histogram this script prints,
# not from a view about crypto: the point is that they are stated, visible, and
# a reader can move them.
ERAS = (
    (
        "2017-2020 · infrastructure era",
        None,
        datetime.fromisoformat("2021-01-01T00:00:00+00:00"),
    ),
    (
        "2021-2022 · retail era",
        datetime.fromisoformat("2021-01-01T00:00:00+00:00"),
        datetime.fromisoformat("2023-01-01T00:00:00+00:00"),
    ),
    (
        "2023+ · recent listings",
        datetime.fromisoformat("2023-01-01T00:00:00+00:00"),
        None,
    ),
)


def cohorts(market, turnover, stamps):
    """Assign every asset to a cohort from listing date and turnover alone."""
    first_seen = {s: min(series) for s, series in market.items()}
    typical = {
        s: median([v for v in turnover[s].values() if v > 0] or [0.0]) for s in market
    }
    ranked = sorted(market, key=lambda s: typical[s], reverse=True)
    top_decile = set(ranked[: max(1, len(ranked) // 10)])

    groups: dict[str, list[str]] = {
        "BTC": ["BTCUSDT"],
        "majors (top decile turnover, listed pre-2021)": [],
        "established alts (pre-2021, outside the top decile)": [],
        "retail-era alts (2021-2022)": [],
        "recent listings (2023+)": [],
    }
    cut = ERAS[0][2]
    retail_end = ERAS[1][2]
    for symbol in market:
        if symbol == "BTCUSDT":
            continue
        listed = first_seen[symbol]
        if listed < cut:
            key = (
                "majors (top decile turnover, listed pre-2021)"
                if symbol in top_decile
                else "established alts (pre-2021, outside the top decile)"
            )
        elif listed < retail_end:
            key = "retail-era alts (2021-2022)"
        else:
            key = "recent listings (2023+)"
        groups[key].append(symbol)
    return groups, first_seen, typical


def returns_of(level):
    return [
        math.log(level[i] / level[i - 1]) if level[i - 1] > 0 else 0.0
        for i in range(1, len(level))
    ]


def correlate_at(a, b, lag):
    """Correlation of `a` with `b` shifted by `lag` bars.

    Positive lag asks: does A today look like B `lag` bars ago -- that is, does
    B LEAD A. Overlapping windows only; no padding, because padding a series
    with zeros invents calm days and drags every correlation toward nothing.
    """
    if lag > 0:
        x, y = a[lag:], b[: len(b) - lag]
    elif lag < 0:
        x, y = a[: len(a) + lag], b[-lag:]
    else:
        x, y = a, b
    n = min(len(x), len(y))
    if n < 200:
        return None
    x, y = x[:n], y[:n]
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    if sx == 0 or sy == 0:
        return None
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / (sx * sy)


def smooth(series, window=30):
    """A trailing mean, so a lag is read off the swing and not off the noise."""
    out, total = [], 0.0
    for i, value in enumerate(series):
        total += value
        if i >= window:
            total -= series[i - window]
        out.append(total / min(i + 1, window))
    return out


def peaks_and_troughs(level, stamps):
    """When this cohort topped and bottomed, on a smoothed level."""
    high = max(range(len(level)), key=lambda i: level[i])
    low_after = min(range(high, len(level)), key=lambda i: level[i])
    return stamps[high], stamps[low_after]


def main() -> int:
    print("loading the archive…", flush=True)
    market = load_all()
    stamps = sorted({s for series in market.values() for s in series})
    turnover = turnover_averages(market)
    groups, first_seen, typical = cohorts(market, turnover, stamps)

    print(f"\n{len(market)} assets · {stamps[0]:%Y-%m-%d} → {stamps[-1]:%Y-%m-%d}")
    print("\nListings by era, which is what makes the cohorts assignable at all:")
    for name, start, end in ERAS:
        count = sum(
            1
            for s, when in first_seen.items()
            if (start is None or when >= start) and (end is None or when < end)
        )
        print(f"  {name:<34} {count:>4} assets")
    thousand = [s for s in market if s.startswith("1000")]
    print(
        f"  of which use Binance's 1000x low-price convention: {len(thousand)} "
        f"({', '.join(sorted(thousand)) or 'none'})"
    )

    print("\nCohorts:")
    levels = {}
    for name, members in groups.items():
        if not members:
            continue
        print(f"  {name:<52} {len(members):>4} assets")
        levels[name] = composite(market, stamps, "equal", turnover, tuple(members))

    broad = composite(market, stamps, "equal", turnover)
    levels["THE WHOLE MARKET"] = broad

    print("\nWhen each cohort topped, and where it bottomed after that.")
    print("On a 30-bar smoothed composite, so a top is a swing and not a spike.\n")
    print(f"  {'cohort':<52} {'peak':<10} {'low after':<10}")
    for name, level in levels.items():
        smoothed = smooth(level)
        top, bottom = peaks_and_troughs(smoothed, stamps)
        peak_level = max(smoothed)
        below = 1 - smoothed[-1] / peak_level if peak_level else 0.0
        print(
            f"  {name:<52} {top:%Y-%m-%d} {bottom:%Y-%m-%d}"
            f"   now {below:>5.0%} below its peak"
        )

    print("\nLead and lag against the whole market, in days.")
    print("Positive means the market LEADS the cohort -- the cohort follows.")
    print("Read as a first measurement: a correlation peak this flat is a hint,")
    print("not a tradable signal.\n")
    market_returns = smooth(returns_of(broad), 7)
    print(f"  {'cohort':<52} {'best lag':>10} {'corr':>8} {'corr at 0':>10}")
    for name, level in levels.items():
        if name == "THE WHOLE MARKET":
            continue
        cohort_returns = smooth(returns_of(level), 7)
        best, score = None, -2.0
        for lag in range(-90, 91):
            found = correlate_at(cohort_returns, market_returns, lag)
            if found is not None and found > score:
                best, score = lag, found
        zero = correlate_at(cohort_returns, market_returns, 0)
        print(
            f"  {name:<52} {best:>+9}d {score:>8.3f} "
            f"{(f'{zero:.3f}' if zero is not None else '--'):>10}"
        )

    print("\n  Every cohort here is defined by AGE and SIZE, which is what the")
    print("  archive supports. None of them is a memecoin index: this laboratory")
    print("  holds no sector labels and inventing them from price would be a")
    print("  taxonomy fitted to the answer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
