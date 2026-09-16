"""Rolling one-year hold analysis — "invest on the 1st of any month, are you up 12 months later?"

The operator's stability criterion: the best algorithm is not one that merely makes money
across several calendar years, but one where — whenever you happen to invest — a year later
you are (almost) always up. So for every month-start across the whole backtest (2018 .. incl.
the sealed 2026), we ask: if you invested that day and held 12 months, did you win or lose?
The headline is two numbers: how many monthly one-year holds WON, and how many LOST.

Method — one continuous backtest per config, then simulate each monthly cohort from it:
  - Run ONE continuous account over the full period with the 25% abort OFF (max_drawdown=1),
    because a single account back to 2018 trips the mandate in 2018/2022 and would be a poor
    measurement path. This gives a clean strategy P&L curve E(t).
  - A cohort entering at month m holds 12 months. Its return is E(m+12)/E(m)-1 — the ratio
    cancels everything before m, so it is exactly the strategy's return over that window.
  - Each cohort is its OWN account with the 25% mandate: scanning the window, if the cohort's
    equity ever falls 25% below its running peak, it aborts to cash and freezes there. So the
    abort is modelled per cohort (honestly), from a single backtest.

Long-only, research-only. 2026 is included ONLY as observation here (this is a descriptive
statistic of an already-fixed strategy, never a selection input).
"""

from __future__ import annotations

import bisect
from datetime import datetime
from typing import Any

from . import launch


def _add_months(dt: datetime, n: int) -> datetime:
    m = dt.month - 1 + n
    y = dt.year + m // 12
    return dt.replace(year=y, month=(m % 12) + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


def _series(equity: list[dict]) -> list[tuple[datetime, float]]:
    out = []
    for p in equity:
        ts = p.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        val = p.get("equity")
        if ts is not None and val is not None:
            out.append((ts, float(val)))
    out.sort(key=lambda x: x[0])
    return out


def rolling_12m(bars, stamps, signals: str, brain_kwargs: dict,
                hold_months: int = 12, abort: float = 0.25,
                trade_from: str = "2018-01-01T00:00:00+00:00") -> dict[str, Any] | None:
    """Two numbers (+ the distribution) for the monthly one-year-hold test."""
    bk = {**brain_kwargs, "max_drawdown": 1.0}  # abort OFF for the measurement path
    start, end = stamps[0], stamps[-1]
    r = launch.run_window(bars, start, trade_from, end, signals, "rolling", brain_kwargs=bk)
    series = _series(r.get("equity", []))
    if len(series) < 24:
        return None
    times = [t for t, _ in series]
    vals = [v for _, v in series]

    def val_at(t: datetime) -> float | None:
        i = bisect.bisect_right(times, t) - 1
        return vals[i] if i >= 0 else None

    def window_between(t0: datetime, t1: datetime) -> list[float]:
        lo = bisect.bisect_left(times, t0)
        hi = bisect.bisect_right(times, t1)
        return vals[lo:hi]

    # month starts from the first trade month to the last month that still allows a full hold
    first = _add_months(datetime.fromisoformat(trade_from), 0)
    last_entry = _add_months(times[-1], -hold_months)
    cohorts = []
    m = first
    while m <= last_entry:
        entry = val_at(m)
        exit_t = _add_months(m, hold_months)
        if entry and entry > 0:
            win_vals = window_between(m, exit_t)
            final = val_at(exit_t)
            if win_vals and final is not None:
                # per-cohort 25% mandate: peak from entry, freeze on a 25% drawdown
                peak = entry
                stopped = None
                for v in win_vals:
                    if v > peak:
                        peak = v
                    if peak > 0 and v <= peak * (1 - abort):
                        stopped = v
                        break
                end_val = stopped if stopped is not None else final
                cohorts.append({"start": m.strftime("%Y-%m"), "ret": end_val / entry - 1.0,
                                "stopped": stopped is not None})
        m = _add_months(m, 1)

    if not cohorts:
        return None
    rets = sorted(c["ret"] for c in cohorts)
    wins = sum(1 for x in rets if x > 0)
    n = len(rets)
    return {
        "wins": wins, "losses": n - wins, "n": n,
        "win_rate": wins / n,
        "worst": rets[0], "best": rets[-1], "median": rets[n // 2],
        "avg": sum(rets) / n,
        "hold_months": hold_months,
        "cohorts": cohorts,   # {start, ret, stopped} per month, for the distribution viz
    }
