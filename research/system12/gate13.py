"""System 12 - task 13: the long-history gate. Do the champion's pieces help in 2014-2020, years the system never saw?

Pre-registered: a System-12-like BTC book on daily data - long while BTC's 60-day momentum > 0 AND BTC > its 100-day average,
half short when both are negative, flat otherwise; 40% volatility target; 0.10%/side; shorts on the spot price (BitMEX perps
existed from 2016; funding is not charged here - an approximation). Pieces with the parameters the champion uses for 2026:
    G00233 = trail_short (cover a short once BTC is 10% above its low since the short began)
             + trend_convex (longs x clip(1 + 30-day BTC return / 0.2, 0.5, 2), gross <= 100%)
A piece passes the gate if it is not worse than the book in more years than it is better, 2014-2020. -> robust/GATE.md

    python research/system12/gate13.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import long12 as LG

YEARS = range(2014, 2021)


def book(px):
    mom = px > px.shift(60)
    ma = px > px.rolling(100).mean()
    return np.where(mom & ma, 1.0, np.where(~mom & ~ma, -0.5, 0.0))


def trail_short(px, pos, p):
    out, low, active, stopped = pos.copy(), None, False, False
    c = px.values
    for t in range(len(pos)):
        if pos[t] < 0:
            if not active:
                active, stopped, low = True, False, c[t]
            low = min(low, c[t])
            if stopped or c[t] > low * (1 + p):
                stopped = True
                out[t] = 0.0
        else:
            active = False
    return out


def trend_convex(px, pos, p):
    m30 = (px / px.shift(30) - 1).fillna(0).values
    k = np.clip(1 + m30 / p, 0.5, 2.0)
    out = np.where(pos > 0, pos * k, pos)
    return np.clip(out, -1, 1)


def main() -> int:
    px = LG.btc()
    r = px.pct_change().fillna(0).values
    vt = np.nan_to_num(np.clip((0.4 / (px.pct_change().rolling(30, min_periods=20).std() * np.sqrt(365))).values, 0, 1))
    year = px.index.year.values
    base = book(px)
    variants = {"book (trend long, half short)": base,
                "+ trail_short 10%": trail_short(px, base, 0.10),
                "+ trend_convex 0.2": trend_convex(px, base, 0.2),
                "+ both (G00233)": trend_convex(px, trail_short(px, base, 0.10), 0.2)}
    res = {}
    for k, pos in variants.items():
        d = LG.run(np.clip(pos * vt, -1, 1), r)
        e = np.cumprod(1 + d[np.isin(year, YEARS)])
        res[k] = ({y: float(np.prod(1 + d[year == y]) - 1) for y in range(2014, 2027)}, float((1 - e / np.maximum.accumulate(e)).max()))
    yrs = list(range(2014, 2027))
    L = ["# Task 13 - long-history gate for the champion's pieces (2014-2020)", "",
         "| variant | " + " | ".join(map(str, yrs)) + " | DD 2014-20 | 2014-20 better / worse |", "|---|" + "---|" * (len(yrs) + 2)]
    b = res["book (trend long, half short)"][0]
    for k, (y, dd) in res.items():
        bw = sum(y[t] > b[t] + 1e-4 for t in YEARS), sum(y[t] < b[t] - 1e-4 for t in YEARS)
        L.append(f"| {k} | " + " | ".join(f"{y[t]:+.0%}" for t in yrs) + f" | {dd:.0%} | {bw[0]} / {bw[1]} |")
    (LG.OUT / "GATE.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
