"""System 12 - task 8: hourly effects (catalogue entries we could not test on daily bars).

Pre-registered (written before running), BTCUSDT spot hourly bars from Binance, 2018-01 to today:
  (a) the published "21:00-23:00 UTC" effect (Quantpedia): long BTC from the 21:00 open to the 23:00 open every day,
      flat otherwise. Costs: 0.10% per side (taker, our book's cost) and 0.02% per side (maker, best case).
  (b) walk-forward: for year N, the 2-hour window (start hour 0-23) with the best mean return on years 2018..N-1, traded in N.
Verdict: worth combining with System 12 only if positive after taker costs in at least 6 of the 8 full years 2018-2025.
-> robust/HOURLY.md

    python research/system12/hour12.py
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "robust"
CACHE = Path(__file__).resolve().parent / "ext" / "btc_1h.csv"


def download() -> pd.DataFrame:
    if CACHE.exists() and time.time() - CACHE.stat().st_mtime < 86400:
        return pd.read_csv(CACHE, index_col=0, parse_dates=True)
    rows, t0 = [], int(pd.Timestamp("2018-01-01").timestamp() * 1000)
    end = int(time.time() * 1000)
    while t0 < end:
        url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&startTime={t0}&limit=1000"
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "quantlab-research/1.0"}), timeout=60))
        if not d:
            break
        rows += [(k[0], float(k[1]), float(k[4])) for k in d]
        t0 = d[-1][0] + 3_600_000
        time.sleep(0.2)
    df = pd.DataFrame(rows, columns=["t", "open", "close"]).drop_duplicates("t")
    df.index = pd.to_datetime(df["t"], unit="ms")
    df = df[["open", "close"]]
    df = df[df.index < pd.Timestamp.utcnow().tz_localize(None).floor("h")]   # closed bars only
    df.to_csv(CACHE)
    return df


def window_returns(df, start, length=2):
    """Daily return of holding from the `start` hour's open to the open `length` hours later."""
    o = df["open"]
    a = o[o.index.hour == start]
    b = o.shift(-length).reindex(a.index)
    return (b / a - 1).dropna()


def yearly(r, cost):
    net = r - 2 * cost
    return {y: float(np.prod(1 + net[net.index.year == y]) - 1) for y in sorted(set(net.index.year))}


def main() -> int:
    df = download()
    years = list(range(2018, 2027))
    L = ["# Task 8 - hourly effects on BTC (2018-2026)", "", f"{len(df):,} hourly bars, {df.index[0]:%Y-%m-%d} to {df.index[-1]:%Y-%m-%d %H:00} UTC.", "",
         "| strategy | costs/side | " + " | ".join(map(str, years)) + " | positive 2018-25 |", "|---|---|" + "---|" * (len(years) + 1)]
    r21 = window_returns(df, 21)
    for cost in (0.0, 0.0002, 0.001):
        y = yearly(r21, cost)
        L.append(f"| (a) long 21:00-23:00 UTC | {cost:.2%} | " + " | ".join(f"{y.get(t, 0):+.0%}" for t in years)
                 + f" | {sum(y.get(t, 0) > 0 for t in range(2018, 2026))}/8 |")
    allw = {h: window_returns(df, h) for h in range(24)}
    for cost in (0.0002, 0.001):
        res, picks = {}, {}
        for N in range(2019, 2027):
            best = max(range(24), key=lambda h: allw[h][(allw[h].index.year < N)].mean())
            picks[N] = best
            res[N] = yearly(allw[best][allw[best].index.year == N], cost).get(N, 0)
        L.append(f"| (b) best 2h window on earlier years | {cost:.2%} | n/a | " + " | ".join(f"{res[t]:+.0%} ({picks[t]}h)" for t in range(2019, 2027))
                 + f" | {sum(res[t] > 0 for t in range(2019, 2026))}/7 |")
    mean_by_hour = pd.DataFrame({h: allw[h].groupby(allw[h].index.year).mean() * 1e4 for h in range(24)})
    L += ["", "## Mean return of each 2-hour window, by year (basis points per day)", "",
          "| year | " + " | ".join(f"{h}h" for h in range(24)) + " |", "|---|" + "---|" * 24]
    for yv, row in mean_by_hour.iterrows():
        L.append(f"| {yv} | " + " | ".join(f"{v:+.0f}" for v in row.values) + " |")
    (OUT / "HOURLY.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
