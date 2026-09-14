"""H - THE WORLD OUTSIDE CRYPTO, as an input to what participants do.

The operator has asked for this more than once: *"habrá que tomar datos de noticias, del precio
de todos los activos del mercado, de todos los países, de todas las commodities, datos de
inflación, datos económicos."* The reason it belongs in THIS system rather than in a return
model is structural. System 09's boundary - the money entering and leaving crypto - is the one
channel v1 could not observe and had to infer as a residual. What drives that residual is not
in the crypto tape at all. It is the price of holding dollars.

WHAT IS HERE, AND WHY EACH ONE
Every series below is already in the shared catalogue, harvested from FRED by system 06, so
this module downloads nothing.

  WALCL       the Federal Reserve's balance sheet - the tide every risk asset floats on
  RRPONTSYD   overnight reverse repo - liquidity parked AWAY from markets. WALCL minus this
              is closer to what actually reaches asset prices than either alone
  WM2NS       broad money
  DGS2        the policy rate as the market prices it, and the OPPORTUNITY COST of holding a
              coin that yields nothing. This is the most direct macro channel into a
              participant's decision to hold cash instead
  DGS10       the long rate - the discount rate on every future cash flow
  T10Y2Y      the curve, already stationary, the regime variable
  DTWEXBGS    the broad dollar. Crypto is priced in it; when it rises, everything else falls
  VIXCLS      equity fear
  BAMLH0A0HYM2  high-yield credit spread - where risk appetite actually breaks first
  SP500, NASDAQCOM  the risk-asset tide
  DCOILWTICO  the real-economy shock channel
  DEXUSEU     the other side of the dollar

THE CLOCK, WHICH IS THE WHOLE DIFFICULTY
Macro data is published LATE and revised afterwards. A feature that uses Tuesday's balance
sheet on Tuesday is using a number nobody had until Thursday, and a model trained that way
learns to read the future. So every series is shifted by its publication lag before it is
used, taken from system 06's measured table where one exists and set conservatively where it
does not. That shift is not a detail; it is the difference between a macro layer and a leak.

Features are RATES OF CHANGE and percentile ranks, never levels. A level is non-stationary -
the balance sheet in 2017 and in 2025 are different worlds - and a model given levels learns
the calendar.
"""

from __future__ import annotations

import bisect
from datetime import date, timedelta

import numpy as np

import quantlab_catalog as cat

#: series -> publication lag in days. The measured values come from system 06's table; the
#: weekly and monthly series are given a lag at least as long as their own release cadence,
#: which is the conservative choice when the true one has not been measured.
LAG_DAYS: dict[str, int] = {
    "WALCL": 9,          # weekly, Thursday release, for the Wednesday position
    "RRPONTSYD": 2,
    "WM2NS": 30,         # monthly, and late
    "DGS2": 6, "DGS10": 6, "T10Y2Y": 4,
    "DTWEXBGS": 14, "VIXCLS": 6, "NASDAQCOM": 4, "SP500": 4,
    "DCOILWTICO": 10, "DEXUSEU": 6, "BAMLH0A0HYM2": 6,
}

#: The feature block this module contributes, in order. Named so the strict-addition test can
#: report which family paid for itself.
NAMES: tuple[str, ...] = (
    "w_netliq_chg60",    # (balance sheet - reverse repo), 60-day log change: the tide
    "w_m2_chg120",       # broad money, slow
    "w_dgs2",            # the short rate in percentage points - the cost of not holding cash
    "w_dgs2_chg60",      # and whether it is rising
    "w_curve",           # 10y - 2y
    "w_dxy_chg60",       # the dollar
    "w_vix_pct",         # fear, as a percentile of its own trailing two years
    "w_hy_chg60",        # high-yield spread change - risk appetite breaking
    "w_spx_ret60",       # the risk tide
    "w_oil_ret60",
)


def _series(sid: str) -> tuple[list[str], list[float]]:
    raw = cat.reference_markets().get(sid)
    if not raw:
        return [], []
    # Rows are [date, value] pairs. FRED writes "." for a missing observation and the
    # catalogue keeps it, because a hole in a series is information and filling it here would
    # hide a market holiday inside a feature.
    days, vals = [], []
    for row in raw.get("rows", []):
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        day, v = row[0], row[1]
        if v in (None, ".", ""):
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
        days.append(str(day)[:10])
    return days, vals


def _shift(day: str, n: int) -> str:
    y, m, d = (int(x) for x in day.split("-"))
    return (date(y, m, d) + timedelta(days=n)).isoformat()


class Series:
    """One macro series, readable only as of a date it was actually published."""

    def __init__(self, sid: str) -> None:
        self.sid = sid
        self.days, self.vals = _series(sid)
        self.lag = LAG_DAYS.get(sid, 30)

    def at(self, day: str, back: int = 0) -> float | None:
        """The latest value PUBLISHED on or before `day`, optionally `back` observations
        earlier. Returns None rather than guessing when the series has not started."""
        if not self.days:
            return None
        cutoff = _shift(day, -self.lag)
        i = bisect.bisect_right(self.days, cutoff) - 1 - back
        return self.vals[i] if i >= 0 else None

    def pct_rank(self, day: str, window: int = 504) -> float | None:
        """Where today sits in its own trailing two years. Stationary by construction."""
        if not self.days:
            return None
        cutoff = _shift(day, -self.lag)
        i = bisect.bisect_right(self.days, cutoff) - 1
        if i < 60:
            return None
        lo = max(0, i - window)
        hist = self.vals[lo:i + 1]
        return float(sum(1 for v in hist if v <= self.vals[i]) / len(hist))


def _chg(s: Series, day: str, back: int, log: bool = True) -> float:
    a, b = s.at(day), s.at(day, back=back)
    if a is None or b is None or b == 0:
        return 0.0
    if log:
        if a <= 0 or b <= 0:
            return 0.0
        return float(np.log(a / b))
    return float(a - b)


def block(days: list[str]) -> np.ndarray:
    """The macro feature block, one row per day, aligned to publication.

    Missing is ZERO, not forward-filled from the future and not dropped: before a series
    exists the honest statement is "this channel carries no information yet", and a zeroed
    change says exactly that without deleting the row.
    """
    s = {sid: Series(sid) for sid in
         ("WALCL", "RRPONTSYD", "WM2NS", "DGS2", "DGS10", "T10Y2Y",
          "DTWEXBGS", "VIXCLS", "BAMLH0A0HYM2", "SP500", "DCOILWTICO")}
    out = np.zeros((len(days), len(NAMES)), dtype=np.float32)
    for i, day in enumerate(days):
        walcl, rrp = s["WALCL"].at(day), s["RRPONTSYD"].at(day)
        walcl_b = s["WALCL"].at(day, back=12)
        rrp_b = s["RRPONTSYD"].at(day, back=60)
        net = (walcl - (rrp or 0.0)) if walcl else None
        net_b = (walcl_b - (rrp_b or 0.0)) if walcl_b else None
        row = [
            float(np.log(net / net_b)) if (net and net_b and net > 0 and net_b > 0) else 0.0,
            _chg(s["WM2NS"], day, 4),
            (s["DGS2"].at(day) or 0.0),
            _chg(s["DGS2"], day, 60, log=False),
            (s["T10Y2Y"].at(day) or 0.0),
            _chg(s["DTWEXBGS"], day, 60),
            (s["VIXCLS"].pct_rank(day) or 0.5),
            _chg(s["BAMLH0A0HYM2"], day, 60, log=False),
            _chg(s["SP500"], day, 60),
            _chg(s["DCOILWTICO"], day, 60),
        ]
        out[i] = [v if np.isfinite(v) else 0.0 for v in row]
    return out


def coverage(days: list[str]) -> dict:
    """How much of the record each channel can actually speak for. Reported, never assumed."""
    x = block(days)
    return {name: float((x[:, i] != 0.0).mean()) for i, name in enumerate(NAMES)}
