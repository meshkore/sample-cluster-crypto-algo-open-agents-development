"""System 12 - task 11: did the Fed net-liquidity filter help a BTC trend rule in 2014-2020, years our data never covered?

Pre-registered (written before running): the rule and parameters the champion uses today (catalogue entry
mac-dharmatech-netliq-fairvalue, n = 126, lo = 0.0, hi = 1.0, used as a FILTER on longs), applied to a plain BTC trend rule
like System 12's main member (long while BTC's 60-day momentum > 0 AND BTC > its 100-day average), 40% volatility target,
spot BTC (no shorts, no funding), 0.10% per side, decided at the daily close, traded the next day.
Data: BTC PriceUSD (CoinMetrics community), WALCL / WTREGEN / RRPONTSYD and NASDAQCOM (FRED) - the S&P 500 series on FRED
starts in 2016, so the Nasdaq Composite stands in for it (the rule is a z-score spread; the overlap years check the swap).
All 8 parameter sets are shown too, to see whether the effect depends on the choice. -> robust/LONG.md

    python research/system12/long12.py
"""

from __future__ import annotations

import itertools
import json
import urllib.request

import numpy as np
import pandas as pd

from pathlib import Path

OUT = Path(__file__).resolve().parent / "robust"
UA = {"User-Agent": "quantlab-research/1.0"}
COST = 0.001


def fred(sid):
    txt = urllib.request.urlopen(urllib.request.Request(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=2010-01-01",
                                                        headers=UA), timeout=60).read().decode()
    rows = [ln.split(",") for ln in txt.strip().splitlines()[1:]]
    return pd.Series({pd.Timestamp(d): float(v) for d, v in rows if v not in (".", "")})


def btc(asset: str = "btc"):
    out, url = {}, (f"https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets={asset}&metrics=PriceUSD&frequency=1d"
                    "&start_time=2011-01-01&page_size=10000&paging_from=start")
    while url:
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))
        for r in d["data"]:
            out[pd.Timestamp(r["time"][:10])] = float(r["PriceUSD"])
        url = d.get("next_page_url")
    return pd.Series(out)


def z(s, n):
    return (s - s.rolling(n, min_periods=n).mean()) / s.rolling(n, min_periods=n).std()


def latch(on, off):
    st, out = 0.0, np.zeros(len(on))
    for t in range(len(on)):
        st = 1.0 if on[t] else (0.0 if off[t] else st)
        out[t] = st
    return out


def run(pos, r):
    pos = np.r_[0, pos[:-1]]                                  # decided at the close, held from the next day
    cost = np.abs(np.diff(np.r_[0, pos])) * COST
    return pos * r - cost


def main() -> int:
    OUT.mkdir(exist_ok=True)
    px = btc()
    idx = px.index
    ff = lambda s: s.reindex(idx.union(s.index)).sort_index().ffill().reindex(idx).shift(1)  # noqa: E731  (known next day)
    netliq = ff(fred("WALCL")) / 1000 - ff(fred("WTREGEN")) / 1000 - ff(fred("RRPONTSYD")).fillna(0)
    eq = {"nasdaq": ff(fred("NASDAQCOM")), "spx": ff(fred("SP500"))}
    r = px.pct_change().fillna(0).values
    vol = px.pct_change().rolling(30, min_periods=20).std() * np.sqrt(365)
    vt = np.nan_to_num(np.clip((0.4 / vol).values, 0, 1))
    base = ((px > px.shift(60)) & (px > px.rolling(100).mean())).astype(float).values
    year = idx.year.values
    years = list(range(2014, 2027))
    out = {}

    def yearly(d):
        return {y: float(np.prod(1 + d[year == y]) - 1) for y in years}

    def mdd(d, ys):
        e = np.cumprod(1 + d[np.isin(year, ys)])
        return float((1 - e / np.maximum.accumulate(e)).max())
    out["BTC buy and hold"] = (yearly(r), mdd(r, range(2014, 2021)))
    db = run(base * vt, r)
    out["trend rule (60d mom & > MA100)"] = (yearly(db), mdd(db, range(2014, 2021)))
    for (n, lo, hi) in itertools.product((126, 252), (0.0, 0.5), (1.0, 1.5)):
        for name, e in eq.items():
            if name == "spx" and (n, lo, hi) != (126, 0.0, 1.0):
                continue
            spread = (z(e, n) - z(netliq, n)).values
            gate = latch(spread < lo, spread > hi)
            d = run(base * gate * vt, r)
            tag = " <- pre-registered" if (n, lo, hi) == (126, 0.0, 1.0) and name == "nasdaq" else ""
            out[f"+ liquidity filter ({name}, n={n}, lo={lo}, hi={hi}){tag}"] = (yearly(d), mdd(d, range(2014, 2021)))
    L = ["# Task 11 - the net-liquidity filter in 2014-2020 (years the system never saw)", "",
         "Spot BTC, long only, 40% volatility target, 0.10%/side, decided at the close. 2014-2020 is the new evidence; "
         "2021-2026 is shown for reference (the spx row exists only from 2017).", "",
         "| strategy | " + " | ".join(map(str, years)) + " | DD 2014-20 |", "|---|" + "---|" * (len(years) + 1)]
    for k, (y, dd) in out.items():
        L.append(f"| {k} | " + " | ".join(f"{y[t]:+.0%}" for t in years) + f" | {dd:.0%} |")
    b = out["trend rule (60d mom & > MA100)"][0]
    pre = [v for k, v in out.items() if "pre-registered" in k][0][0]
    better = sum(pre[t] > b[t] + 1e-4 for t in range(2014, 2021))
    worse = sum(pre[t] < b[t] - 1e-4 for t in range(2014, 2021))
    L += ["", f"Pre-registered filter vs the plain trend rule, 2014-2020: better in {better} years, worse in {worse}."]
    (OUT / "LONG.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
