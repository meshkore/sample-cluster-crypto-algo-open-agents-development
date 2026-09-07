"""A96: let the net see the markets AROUND crypto — and only what we could get live.

Operator, 2026-09-05: "the inflation data are probably directly related to the market's
direction — Fed news in real time, the US Treasury, GDP readings, oil, the NASDAQ."
And, 2026-09-07, the constraint that shapes every line below: "make sure that whatever
it trains on is information we will be able to obtain in real time for executions from
today into the future."

That second sentence is the design. A backtest feature that cannot be fetched live is
not a feature, it is a leak with good manners. So:

**Source.** FRED's fredgraph CSV endpoint. Free, no API key, no account, and these
particular series are NOT revised after publication — a Treasury yield or a VIX close
for day D is the same number forever. That is what makes them safe; a revised series
(GDP, payrolls) would hand a backtest a value nobody had at the time, which is why
those belong to A87 with ALFRED point-in-time vintages and not here.

**The publication lag is per series and measured, not assumed.** At the 2026-09-07
harvest the daily series were stale by very different amounts:

    NASDAQCOM, T10Y2Y      published next business day
    DGS2, DGS10, VIXCLS    1-4 days behind
    DCOILWTICO             ~6 days behind
    DTWEXBGS               ~10 days behind

A single global lag would either leak (too small for the dollar) or throw away a week
of VIX (too large for the fast ones). So each series carries its own lag, set ABOVE the
worst staleness observed for it, and a bar may only read observations dated on or
before `bar_date - lag`. Conservative in the only direction that matters: if the real
feed is faster than the lag we assumed, the live system is better informed than the
backtest, never worse.

**Stationarity**, the same rule features.py already enforces: no levels. A net trained
on "NASDAQ = 14,000" has learned a number that never recurs. Everything here is a
change, a spread, or a trailing percentile.

**Operational consequence, stated so it cannot be forgotten:** shipping this means a
daily job that refreshes research/system06/external/reference_markets.json. If that job
dies, the features go stale and the book quietly trades on a frozen picture of the
world. `staleness_days` is exported for exactly that alarm.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

REFERENCE_FILE = Path("research/system06/external/reference_markets.json")

# series id -> (lag in days a bar must wait before reading an observation)
# Set above the worst staleness measured at harvest. Re-measure when the harvest runs;
# `check_lags` fails the suite if reality drifts past what is assumed here.
SERIES_LAG_DAYS: dict[str, int] = {
    "NASDAQCOM": 4,
    "T10Y2Y": 4,
    "DGS2": 6,
    "DGS10": 6,
    "VIXCLS": 6,
    "DCOILWTICO": 10,
    "DTWEXBGS": 14,
}

REFERENCE_FEATURE_COLUMNS: tuple[str, ...] = (
    "ref_vix_pct",      # VIX percentile within its trailing 2y — fear, scaled
    "ref_vix_chg20",    # log change of VIX over 20 observations — fear ACCELERATING
    "ref_ndx_ret20",    # NASDAQ 20-obs log return — the risk-asset tide
    "ref_ndx_ret60",    # the same, slower
    "ref_dxy_chg20",    # broad dollar 20-obs log change — global liquidity
    "ref_oil_ret20",    # WTI 20-obs log return — the real-economy shock channel
    "ref_y10_chg20",    # 10y yield change in pp — the discount rate moving
    "ref_curve",        # 10y-2y spread in pp — the regime signal, already stationary
)

_TRAIL = 504          # ~2 trading years, for the VIX percentile
_DAY_NS = 86_400_000_000_000


def _load(path: Path | str | None = None) -> dict:
    p = Path(path) if path else REFERENCE_FILE
    if not p.is_file():
        raise FileNotFoundError(
            f"{p} not found — run the reference harvest before training with A96")
    return json.loads(p.read_text(encoding="utf-8"))


def _series(raw: dict, sid: str) -> tuple[np.ndarray, np.ndarray]:
    """(observation dates as ns, values) sorted ascending, non-empty."""
    rows = (raw.get(sid) or {}).get("rows") or []
    if not rows:
        raise KeyError(f"reference series {sid} is missing or empty")
    dates = np.array([r[0] for r in rows], dtype="datetime64[D]").astype("datetime64[ns]")
    vals = np.array([float(r[1]) for r in rows], dtype=float)
    order = np.argsort(dates, kind="stable")
    return dates[order].astype(np.int64), vals[order]


def staleness_days(raw: dict, today_ns: int) -> dict[str, float]:
    """How far behind each series is right now — the alarm for a dead refresh job."""
    out = {}
    for sid in SERIES_LAG_DAYS:
        try:
            d, _v = _series(raw, sid)
        except KeyError:
            out[sid] = float("inf")
            continue
        out[sid] = (today_ns - int(d[-1])) / _DAY_NS
    return out


def _aligned(dates_ns: np.ndarray, values: np.ndarray, bar_ns: np.ndarray,
             lag_days: int) -> np.ndarray:
    """The most recent observation a bar is ALLOWED to have seen, per bar.

    `searchsorted(..., side="right") - 1` on the lagged cutoff gives the last
    observation dated at or before it; -1 (nothing old enough yet) becomes NaN, which
    finite_rows already drops, so the warm-up front behaves like every other feature's.
    """
    cutoff = bar_ns - lag_days * _DAY_NS
    idx = np.searchsorted(dates_ns, cutoff, side="right") - 1
    out = np.full(len(bar_ns), np.nan)
    ok = idx >= 0
    out[ok] = values[idx[ok]]
    return out


def _lagged_transform(dates_ns, values, bar_ns, lag_days, fn) -> np.ndarray:
    """Compute a transform ON THE DAILY SERIES, then align it to bars.

    Order matters and is the subtle part: transforming after alignment would compute a
    "20-observation return" across 15-minute bars — 20 bars is five hours, not a month —
    and the feature would silently mean something else entirely.
    """
    transformed = fn(values)
    return _aligned(dates_ns, transformed, bar_ns, lag_days)


# A 20-day log change beyond this is not a market move, it is a data event. Measured
# 2026-09-07: WTI printed NEGATIVE on 2020-04-20 (-$37, the expiry squeeze), and the
# logarithm of a negative price does not exist. Flooring the price silently produced
# ref_oil_ret20 = -30.6, a value that would have dominated the standardiser's mean and
# variance for that column and quietly rescaled every other row of it. Clipping states
# the same fact without letting one afternoon in 2020 define the feature's units.
_MAX_LOG_CHANGE = 1.5      # ~4.5x over the window, in either direction


def _log_change(v: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(v), np.nan)
    if len(v) > n:
        with np.errstate(divide="ignore", invalid="ignore"):
            a = np.where(v[n:] > 0, v[n:], np.nan)
            b = np.where(v[:-n] > 0, v[:-n], np.nan)
            out[n:] = np.clip(np.log(a / b), -_MAX_LOG_CHANGE, _MAX_LOG_CHANGE)
    # A non-positive endpoint leaves NaN, which then forward-fills from the last
    # ADMISSIBLE observation through _aligned - the bar sees the most recent valid
    # value, exactly as it would live, rather than a fabricated number.
    ok = np.isfinite(out)
    if ok.any():
        idx = np.maximum.accumulate(np.where(ok, np.arange(len(out)), 0))
        out = np.where(ok, out, np.where(np.arange(len(out)) >= np.argmax(ok),
                                         out[idx], np.nan))
    return out


def _diff(v: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(v), np.nan)
    if len(v) > n:
        out[n:] = v[n:] - v[:-n]
    return out


def _trailing_pct(v: np.ndarray, window: int = _TRAIL) -> np.ndarray:
    """Rank of each value within its own trailing window, in [0,1]. Causal by
    construction: position i is ranked against i-window..i only."""
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        lo = max(0, i - window + 1)
        if i - lo + 1 < 60:          # too little history to rank against
            continue
        block = v[lo:i + 1]
        out[i] = float((block <= v[i]).mean())
    return out


class ReferenceTable:
    """The reference panel, ready to answer `matrix_for(bar timestamps)`."""

    def __init__(self, path: Path | str | None = None):
        self.raw = _load(path)
        self.cols = REFERENCE_FEATURE_COLUMNS

    def matrix_for(self, timestamps: np.ndarray) -> np.ndarray:
        bar_ns = np.asarray(timestamps, dtype="datetime64[ns]").astype(np.int64)
        r = self.raw

        vix_d, vix_v = _series(r, "VIXCLS")
        ndx_d, ndx_v = _series(r, "NASDAQCOM")
        dxy_d, dxy_v = _series(r, "DTWEXBGS")
        oil_d, oil_v = _series(r, "DCOILWTICO")
        y10_d, y10_v = _series(r, "DGS10")
        crv_d, crv_v = _series(r, "T10Y2Y")

        L = SERIES_LAG_DAYS
        cols = [
            _lagged_transform(vix_d, vix_v, bar_ns, L["VIXCLS"], _trailing_pct),
            _lagged_transform(vix_d, vix_v, bar_ns, L["VIXCLS"], lambda v: _log_change(v, 20)),
            _lagged_transform(ndx_d, ndx_v, bar_ns, L["NASDAQCOM"], lambda v: _log_change(v, 20)),
            _lagged_transform(ndx_d, ndx_v, bar_ns, L["NASDAQCOM"], lambda v: _log_change(v, 60)),
            _lagged_transform(dxy_d, dxy_v, bar_ns, L["DTWEXBGS"], lambda v: _log_change(v, 20)),
            _lagged_transform(oil_d, oil_v, bar_ns, L["DCOILWTICO"], lambda v: _log_change(v, 20)),
            _lagged_transform(y10_d, y10_v, bar_ns, L["DGS10"], lambda v: _diff(v, 20)),
            _aligned(crv_d, crv_v, bar_ns, L["T10Y2Y"]),
        ]
        return np.column_stack(cols)
