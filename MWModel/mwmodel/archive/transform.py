"""LEVELS ARE A TRAP: one named function per way of making a series usable.

A model handed the level of the Federal Reserve's balance sheet does not learn about
liquidity. It learns the calendar - the number rises through the record, so does the price of
everything, and the fit is a date detector. The same is true of an index, a supply, a
capitalisation and a price. So the panel is stationary by default and levels must be asked for
by name.

EVERY FUNCTION HERE IS CAUSAL BY CONSTRUCTION. They operate on a column that `clock.py` has
already resolved as-of each day, so position *k* in the input is what was knowable on day *k*
and nothing later. A trailing window over that column cannot see forward even in principle,
which is a much stronger guarantee than "we remembered to shift it".
"""

from __future__ import annotations

import math

import numpy as np

Column = list[float | None]


def _arr(col: Column) -> np.ndarray:
    return np.array([np.nan if v is None else float(v) for v in col], dtype=np.float64)


def _back(days: list[str] | None, n: int, k: int) -> np.ndarray:
    """For each row, the index of the row `k` CALENDAR days earlier - or -1 if there is none.

    Lookbacks have to be in calendar days rather than in rows, and the difference is not
    cosmetic. A panel built on a daily grid makes them coincide; one built on month-ends, or
    on trading days, or on a hand-picked list of evaluation dates makes "365 rows ago" mean
    thirty years ago or last week. A year-on-year figure computed on a 24-row panel silently
    became all-NaN, which is exactly the kind of quiet emptiness a model learns as a date.
    """
    if not days:
        return np.arange(-k, n - k)
    import bisect
    from datetime import date, timedelta
    ds = [date.fromisoformat(d[:10]) for d in days[:n]]
    iso = [d.isoformat() for d in ds]
    out = np.empty(n, dtype=np.int64)
    for i, d in enumerate(ds):
        target = (d - timedelta(days=k)).isoformat()
        j = bisect.bisect_right(iso, target) - 1
        out[i] = j
    return out


def _shifted(col: Column, k: int, days: list[str] | None):
    """`(current, previous)` aligned, with NaN wherever no row is `k` days behind."""
    a = _arr(col)
    idx = _back(days, len(a), k)
    prev = np.full(len(a), np.nan)
    ok = idx >= 0
    prev[ok] = a[idx[ok]]
    return a, prev


def level(col: Column, **_) -> np.ndarray:
    """The raw value. Legitimate for things that are already stationary - a rate in percent,
    a spread, a sentiment index bounded 0-100 - and a mistake for everything else."""
    return _arr(col)


def diff(col: Column, k: int = 1, days: list[str] | None = None, **_) -> np.ndarray:
    a, prev = _shifted(col, k, days)
    return a - prev


def pct_change(col: Column, k: int = 1, days: list[str] | None = None, **_) -> np.ndarray:
    a, prev = _shifted(col, k, days)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(prev > 0, a / prev - 1.0, np.nan)


def log_change(col: Column, k: int = 60, days: list[str] | None = None,
               **_) -> np.ndarray:
    """The default for anything that grows: a balance sheet, a supply, an index, a price.

    Sixty days rather than one because the channel being measured is slow. Daily noise in the
    Fed's balance sheet is a settlement artefact; the two-month change is the tide.
    """
    a, prev = _shifted(col, k, days)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where((prev > 0) & (a > 0), a / prev, np.nan)
        return np.log(r)


def yoy(col: Column, k: int = 365, days: list[str] | None = None, **_) -> np.ndarray:
    """Year-on-year change, which for a CPI index is the number everyone actually quotes.

    The lookback is in CALENDAR days, so it is a year whatever grid the panel is built on.
    The inflation rate a person knew in June is June's release against the previous June's,
    and if the archive cannot say that on an irregular grid it cannot say it at all.
    """
    return pct_change(col, k, days)


def percentile(col: Column, win: int = 504, **_) -> np.ndarray:
    """Where today's value sits in its own trailing two years, 0-1.

    The honest way to use a series whose regime changes - the VIX at 20 means one thing in
    2017 and another in 2020. Two years is chosen to be long enough to contain a regime and
    short enough not to average two of them.
    """
    a = _arr(col)
    out = np.full(len(a), np.nan)
    for i in range(len(a)):
        lo = max(0, i - win + 1)
        w = a[lo:i + 1]
        w = w[np.isfinite(w)]
        if len(w) >= 30 and math.isfinite(a[i]):
            out[i] = float((w <= a[i]).mean())
    return out


def zscore(col: Column, win: int = 504, **_) -> np.ndarray:
    a = _arr(col)
    out = np.full(len(a), np.nan)
    for i in range(len(a)):
        w = a[max(0, i - win + 1):i + 1]
        w = w[np.isfinite(w)]
        if len(w) >= 30 and w.std() > 1e-12 and math.isfinite(a[i]):
            out[i] = float((a[i] - w.mean()) / w.std())
    return out


def ratio(col: Column, other: Column | None = None, **_) -> np.ndarray:
    a = _arr(col)
    b = _arr(other if other is not None else col)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b != 0, a / b, np.nan)


def spread(col: Column, other: Column | None = None, **_) -> np.ndarray:
    return _arr(col) - _arr(other if other is not None else col)


def real_rate(col: Column, other: Column | None = None, **_) -> np.ndarray:
    """A nominal rate minus an inflation rate, both in percent.

    The cross-regional version of this is the operator's whole point: an investor facing a
    negative real rate at home and one facing five percent are not the same buyer, and the
    difference between them is not visible in any single global series.
    """
    infl = _arr(other if other is not None else col)
    if infl.max(initial=0) <= 1.0:        # a fraction rather than percentage points
        infl = infl * 100.0
    return _arr(col) - infl


FUNCTIONS = {"level": level, "diff": diff, "pct_change": pct_change,
             "log_change": log_change, "yoy": yoy, "percentile": percentile,
             "zscore": zscore, "ratio": ratio, "spread": spread, "real_rate": real_rate}


def apply(name: str, col: Column, **kwargs) -> np.ndarray:
    """`kwargs` reach the transform verbatim; `days` is what makes lookbacks calendar-true.

    THE DAY LIST IS NOT ASSUMED TO BE SORTED OR UNIQUE, and that is not defensive
    programming - it is a bug this caught. System 09's feature matrix has one row per
    (symbol, day) and is grouped BY SYMBOL, so its day column runs 2017..2025 once per asset.
    Every lookback here reads "the value k calendar days before this row", which on such a
    list is meaningless: the first reading after each symbol boundary looks backwards into
    another symbol's future. The whole macro block silently collapsed to 2% coverage.

    A market-wide stream's value depends only on the day, so the fix is exact rather than a
    patch: collapse to the unique sorted days, transform there, and scatter the result back to
    the rows. Sorted, unique input takes the same path and is unchanged.
    """
    fn = FUNCTIONS.get(name)
    if fn is None:
        raise KeyError(f"unknown transform {name!r}; have {sorted(FUNCTIONS)}")
    days = kwargs.get("days")
    if not days:
        return fn(col, **kwargs)

    keys = [d[:10] for d in days]
    uniq = sorted(set(keys))
    if len(uniq) == len(keys) and keys == uniq:
        return fn(col, **kwargs)

    first: dict[str, float | None] = {}
    for k, v in zip(keys, col):
        if k not in first or (first[k] is None and v is not None):
            first[k] = v
    kwargs = dict(kwargs, days=uniq)
    out = fn([first[d] for d in uniq], **kwargs)
    at = {d: i for i, d in enumerate(uniq)}
    return np.asarray([out[at[k]] for k in keys], dtype=np.float64)
