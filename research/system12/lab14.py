"""System 12 - task 14: a 12-year walk-forward lab on BTC daily (2014-2026), the strongest filter against luck we can build.

The book: long while BTC's 60-day momentum > 0 AND BTC > its 100-day average, half short when both are negative, flat
otherwise; 40% volatility target; 0.10%/side; decided at the close, traded the next day; shorts on the spot price (funding
not charged - an approximation before perps existed). Data: CoinMetrics daily BTC price and MVRV.
Each piece (the generator's catalogue, re-written for daily bars) is judged walk-forward: for year N (2016-2026) its
parameter - or "off" - is chosen on the Sharpe of years 2014..N-1, then read on N. 2016-2025 = 10 out-of-sample years;
2026 is printed, never used. A ROBUST piece improves more years than it worsens AND raises the mean.
Then the robust pieces are stacked greedily in walk-forward order of their 2016-2025 gain, keeping a piece only if the
stack's 10-year walk-forward Sharpe rises. -> robust/LAB14.md

    python research/system12/lab14.py
"""

from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd

import long12 as LG

OUT = LG.OUT
YEARS = list(range(2014, 2027))
WF = list(range(2016, 2027))


class Data:
    def __init__(self, asset: str = "btc"):
        px = LG.btc(asset)
        px = px[px.index >= "2013-01-01"]
        self.px, self.c = px, px.values
        self.r = px.pct_change().fillna(0).values
        self.year = px.index.year.values
        self.month = px.index.month.values
        self.dow = px.index.dayofweek.values
        vol = px.pct_change().rolling(30, min_periods=20).std() * np.sqrt(365)
        self.vt = np.nan_to_num(np.clip((0.4 / vol).values, 0, 1))
        mom, ma = px > px.shift(60), px > px.rolling(100).mean()
        self.book = np.where(mom & ma, 1.0, np.where(~mom & ~ma, -0.5, 0.0))
        mv = json.loads((LG.OUT.parent / "ext" / "mvrv.json").read_text(encoding="utf-8"))
        s = pd.Series({pd.Timestamp(k): v for k, v in mv.items()}).sort_index()
        self.mvrv = s.reindex(px.index.union(s.index)).sort_index().ffill().reindex(px.index).shift(1).values
        self.T = len(px)

    def roll(self, a, n, f):
        return getattr(pd.Series(a).rolling(n, min_periods=max(2, n // 2)), f)().values


def episodes_mult(d, pos, side, rule):
    leg = (pos > 0) if side > 0 else (pos < 0)
    m, st = np.ones(d.T), None
    for t in range(d.T):
        if not leg[t]:
            st = None
            continue
        if st is None:
            st = {"entry": d.c[t], "hi": d.c[t], "lo": d.c[t], "k": 1.0, "n": 0}
        st["hi"], st["lo"], st["n"] = max(st["hi"], d.c[t]), min(st["lo"], d.c[t]), st["n"] + 1
        st["k"] = rule(st, d.c[t])
        m[t] = st["k"]
    return m


def long_x(pos, m):
    return np.where(pos > 0, pos * m, pos)


def short_x(pos, m):
    return np.where(pos < 0, pos * m, pos)


def rsi(c, n=14):
    s = pd.Series(c).diff()
    up, dn = s.clip(lower=0).ewm(alpha=1 / n).mean(), (-s.clip(upper=0)).ewm(alpha=1 / n).mean()
    return (100 - 100 / (1 + up / dn)).values


PIECES = {
    "trail_short": ((0.06, 0.10, 0.15), lambda d, p, v: short_x(p, episodes_mult(d, p, -1, lambda s, c: 0.0 if s["k"] == 0 or c > s["lo"] * (1 + v) else 1.0))),
    "stop_long": ((0.05, 0.08, 0.12, 0.18), lambda d, p, v: long_x(p, episodes_mult(d, p, 1, lambda s, c: 0.0 if s["k"] == 0 or c < s["entry"] * (1 - v) else 1.0))),
    "trail_long": ((0.08, 0.12, 0.18, 0.25), lambda d, p, v: long_x(p, episodes_mult(d, p, 1, lambda s, c: 0.0 if s["k"] == 0 or c < s["hi"] * (1 - v) else 1.0))),
    "tp_long": ((0.15, 0.30, 0.50, 0.80), lambda d, p, v: long_x(p, episodes_mult(d, p, 1, lambda s, c: 0.5 if s["k"] == 0.5 or c > s["entry"] * (1 + v) else 1.0))),
    "pyramid_long": ((0.05, 0.10, 0.20), lambda d, p, v: long_x(p, episodes_mult(d, p, 1, lambda s, c: 1.5 if s["k"] == 1.5 or c > s["entry"] * (1 + v) else 1.0))),
    "trend_convex": ((0.2, 0.4, 0.8), lambda d, p, v: long_x(p, np.clip(1 + np.nan_to_num(d.c / np.r_[np.full(30, d.c[0]), d.c[:-30]] - 1) / v, 0.5, 2.0))),
    "entry_confirm": ((0.02, 0.05, 0.10), lambda d, p, v: long_x(p, episodes_mult(d, p, 1, lambda s, c: 1.0 if s["k"] == 1.0 and s["n"] > 1 or c > s["entry"] * (1 + v) else 0.0))),
    "entry_delay": ((1, 3, 7), lambda d, p, v: long_x(p, episodes_mult(d, p, 1, lambda s, c: 0.0 if s["n"] <= v else 1.0))),
    "vol_break": ((1.5, 2.0, 2.5), lambda d, p, v: long_x(p, np.where(np.nan_to_num(d.roll(d.r, 7, "std") / d.roll(d.r, 90, "std")) > v, 0.5, 1.0))),
    "crash_exit": ((0.10, 0.15, 0.20, 0.25), lambda d, p, v: long_x(p, np.where(1 - d.c / d.roll(d.c, 20, "max") > v, 0.0, 1.0))),
    "mayer_trim": ((2.0, 2.4), lambda d, p, v: long_x(p, np.where(np.nan_to_num(d.c / d.roll(d.c, 200, "mean")) > v, 0.5, 1.0))),
    "mvrv_trim": ((2.5, 3.0, 3.5), lambda d, p, v: long_x(p, np.where(np.nan_to_num(d.mvrv) > v, 0.5, 1.0))),
    "short_size": ((0.5, 1.5, 2.0), lambda d, p, v: short_x(p, np.full(d.T, v))),
    "long_size": ((1.1, 1.2, 1.3), lambda d, p, v: long_x(p, np.full(d.T, v))),
    "dd_adaptive": ((0.2, 0.3, 0.4), None),                          # needs the book's own equity: handled in apply()
    "breakout_boost": ((20, 55, 100), lambda d, p, v: long_x(p, np.where(d.c >= d.roll(d.c, v, "max") * 0.999, 1.5, 1.0))),
    "rsi_trim": ((70, 75, 80), lambda d, p, v: long_x(p, np.where(np.nan_to_num(rsi(d.c)) > v, 0.5, 1.0))),
    "ma_cross_exit": (((10, 30), (20, 50), (50, 100)), lambda d, p, v: long_x(p, (d.roll(d.c, v[0], "mean") >= d.roll(d.c, v[1], "mean")).astype(float))),
    "september_light": ((0.0, 0.5), lambda d, p, v: p * np.where(d.month == 9, v, 1.0)),
    "weekend_flat": ((0.0, 0.5), lambda d, p, v: p * np.where(d.dow >= 5, v, 1.0)),
}


def apply(d, pos, name, v):
    if v is None:
        return pos
    if name == "dd_adaptive":
        eq = np.cumprod(1 + LG.run(np.clip(pos * d.vt, -1, 1), d.r))
        dd = 1 - eq / np.maximum.accumulate(eq)
        return pos * np.clip(1 - dd / v, 0.25, 1.0)
    return PIECES[name][1](d, pos, v)


def daily_ret(d, pos):
    return LG.run(np.clip(pos * d.vt, -1, 1), d.r)


def sharpe(x):
    return float(x.mean() / x.std() * np.sqrt(365)) if x.std() > 0 else 0.0


def yr(d, x, y):
    return float(np.prod(1 + x[d.year == y]) - 1)


def walk(d, base, name):
    """Per year N: choose v (or None) on Sharpe of 2014..N-1, read N. Returns the walk-forward position and choices."""
    opts = [None] + list(PIECES[name][0])
    cand = {v: apply(d, base, name, v) for v in opts}
    rets = {v: daily_ret(d, p) for v, p in cand.items()}
    pos, ch = base.copy(), {}
    for N in WF:
        tr = (d.year >= 2014) & (d.year < N)
        v = max(opts, key=lambda o: sharpe(rets[o][tr]))
        ch[N] = v
        pos[d.year == N] = cand[v][d.year == N]
    return pos, ch


def main() -> int:
    d = Data()
    base_r = daily_ret(d, d.book)
    by = {y: yr(d, base_r, y) for y in YEARS}
    rows = []
    for name in PIECES:
        pos, ch = walk(d, d.book, name)
        r = daily_ret(d, pos)
        g = {y: yr(d, r, y) - by[y] for y in WF}
        better = sum(g[y] > 1e-4 for y in range(2016, 2026))
        worse = sum(g[y] < -1e-4 for y in range(2016, 2026))
        sh = sharpe(r[(d.year >= 2016) & (d.year <= 2025)]) - sharpe(base_r[(d.year >= 2016) & (d.year <= 2025)])
        rows.append((name, better, worse, float(np.mean([g[y] for y in range(2016, 2026)])), sh, g, ch))
    rows.sort(key=lambda t: -t[4])
    L = ["# Task 14 - 12-year walk-forward lab, BTC daily", "",
         "Book: long on (60-day momentum > 0 AND > 100-day average), half short when both negative, 40% vol target, 0.10%/side.", "",
         "| | " + " | ".join(map(str, YEARS)) + " |", "|---|" + "---|" * len(YEARS),
         "| book | " + " | ".join(f"{by[y]:+.0%}" for y in YEARS) + " |", "",
         "## Each piece, walk-forward 2016-2026 (gain vs the book, percentage points)", "",
         "| piece | better / worse (2016-25) | mean gain | Sharpe gain | " + " | ".join(map(str, WF)) + " | robust |",
         "|---|---|---|---|" + "---|" * (len(WF) + 1)]
    robust = []
    for name, b, w, mg, sh, g, ch in rows:
        ok = b > w and mg > 0 and sh > 0
        if ok:
            robust.append(name)
        L.append(f"| {name} | {b} / {w} | {mg:+.1%} | {sh:+.2f} | " + " | ".join(f"{g[y] * 100:+.0f}" for y in WF) + f" | {'YES' if ok else ''} |")
    # greedy stack of the robust pieces, each step walk-forward on top of the previous stack
    stack, pos = [], d.book.copy()
    cur = sharpe(daily_ret(d, pos)[(d.year >= 2016) & (d.year <= 2025)])
    for name in robust:
        p2, _ = walk(d, pos, name)
        s2 = sharpe(daily_ret(d, p2)[(d.year >= 2016) & (d.year <= 2025)])
        if s2 > cur + 0.02:
            stack.append(name)
            pos, cur = p2, s2
    sr = daily_ret(d, pos)
    e = np.cumprod(1 + sr[(d.year >= 2016) & (d.year <= 2025)])
    eb = np.cumprod(1 + base_r[(d.year >= 2016) & (d.year <= 2025)])
    L += ["", f"## Robust pieces stacked (walk-forward, kept only if the 2016-25 Sharpe rises): {', '.join(stack) or 'none'}", "",
          "| | " + " | ".join(map(str, YEARS)) + " | DD 2016-25 | Sharpe 2016-25 |", "|---|" + "---|" * (len(YEARS) + 2),
          "| book | " + " | ".join(f"{by[y]:+.0%}" for y in YEARS) + f" | {(1 - eb / np.maximum.accumulate(eb)).max():.0%} | "
          f"{sharpe(base_r[(d.year >= 2016) & (d.year <= 2025)]):.2f} |",
          "| book + stack | " + " | ".join(f"{yr(d, sr, y):+.0%}" for y in YEARS) + f" | {(1 - e / np.maximum.accumulate(e)).max():.0%} | {cur:.2f} |"]
    (OUT / "LAB14.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (OUT / "lab14.json").write_text(json.dumps({"robust": robust, "stack": stack}, indent=1), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
