"""Classics 11 - published, rule-based crypto strategies, tested honestly on System 11's own data
(operator 2026-10-21: "read published strategies that claim good out-of-sample results and test them").

Same honesty rules as the System 11 book:
  data       history_v2.world(cap): point-in-time top-`cap` lists per year (delisted included), 4h grid
  decision   every signal is computed on DAILY closes and read at the last daily close before each 4h row
             (rocket11.Data.to4h / dk logic, one 4h bar of extra delay); a coin is held only while it is a
             member of that year's list and has a finite close
  book       long-only spot, weights >= 0, sum <= 1; 0.225%/side + ADV impact via history_v2.bar_returns
  years      each calendar year 2020..2026 from the same capital (no compounding across years)
  params     the published parameters first; where a rule has a free parameter, a walk-forward line picks it
             for year N by daily Sharpe over 2019..N-1 (2019 is the warm-up year for the 2020 pick)
  2026       forward test: computed and reported, never used to choose anything
  equal risk each daily series is rescaled (k x daily return) so its 2020-2025 max drawdown is 25%, the System 11
             paper scale; k > 1 means leverage a spot book cannot take - it is a comparison, not a book

    python research/plan_v2/classics11.py            # caps 14 and 20
Writes research/plan_v2/classics11/{results.json, REPORT.md}.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import history_v2 as H
import phase3_select as P3

HERE = Path(__file__).resolve().parent
OUT = HERE / "classics11"
YEARS = tuple(range(2020, 2027))
RESEARCH = tuple(range(2020, 2026))
WF_FROM = 2019
DD_TARGET = 0.25
S11 = {"name": "System 11 (paper scale, reference)", "source": "our book",
       "years": {2020: 0.59, 2021: 0.96, 2022: -0.12, 2023: 0.38, 2024: 0.19, 2025: 0.08, 2026: 0.015}, "max_dd": 0.25,
       "sharpe_2020_2025": 1.40}  # lab/history/cap14-spot_long-xs-base-mlp.json research.sharpe
S11_LAW = {2020: 0.89, 2021: 1.29, 2022: -0.16, 2023: 0.66, 2024: 0.30, 2025: 0.02, 2026: 0.04}


# ------------------------------------------------------------------ data

class Ctx:
    def __init__(self, w):
        self.w = w
        P1, P4 = w.P["1d"], w.P4
        self.coins = P1["coins"]
        self.jb = self.coins.index("BTCUSDT")
        self.je = self.coins.index("ETHUSDT")
        self.C = pd.DataFrame(P1["close"])
        self.HI, self.LO = pd.DataFrame(P1["high"]), pd.DataFrame(P1["low"])
        self.USD = pd.DataFrame(P1["usd"])
        self.M = P1["member"] & np.isfinite(P1["close"])
        self.R = self.C / self.C.shift(1) - 1
        day = ((P1["grid"] - 1) // P3.D1).astype("int64")          # the day a close-stamped bar belongs to
        self.wd = (day + 3) % 7                                     # Monday = 0
        dd = day.astype("datetime64[D]")
        self.dom = (dd - dd.astype("datetime64[M]")).astype(int) + 1
        self.month_end = np.r_[dd[1:].astype("datetime64[M]") != dd[:-1].astype("datetime64[M]"), False]
        prev = np.r_[P4["grid"][0], P4["grid"][:-1]]
        self.dk = np.searchsorted(P1["grid"], prev, side="right") - 1
        self.nD, self.S = self.C.shape

    # weights -----------------------------------------------------------------
    def to4h(self, D: np.ndarray) -> np.ndarray:
        D = np.nan_to_num(np.asarray(D, dtype=float))
        W = D[np.clip(self.dk, 0, None)].copy()
        W[self.dk < 0] = 0.0
        W = np.where(self.w.P4["member"] & np.isfinite(self.w.P4["close"]), W, 0.0)
        s = W.sum(axis=1, keepdims=True)
        return np.where(s > 1.0, W / np.maximum(s, 1e-12), np.clip(W, 0, None))

    def run(self, W4: np.ndarray):
        r, _ = H.bar_returns(self.w, W4, P3.HALF_COST, None)
        d, dy, _ = H.to_daily(self.w, r)
        return d, dy

    # helpers -----------------------------------------------------------------
    def only(self, j: int, x) -> np.ndarray:
        D = np.zeros((self.nD, self.S))
        D[:, j] = np.asarray(x, dtype=float)
        return D

    def hold_on(self, D: np.ndarray, when: np.ndarray) -> np.ndarray:
        """Recompute only on `when` days, carry the last target otherwise."""
        idx = np.where(when, np.arange(self.nD), -1)
        idx = np.maximum.accumulate(idx)
        out = D[np.clip(idx, 0, None)].copy()
        out[idx < 0] = 0.0
        return out

    def weekly(self, D):
        return self.hold_on(D, self.wd == 6)        # Sunday's close = the Monday 00:00 bar

    def monthly(self, D):
        return self.hold_on(D, self.month_end)

    def tercile(self, score, top: bool, frac: float = 1 / 3) -> np.ndarray:
        """Equal weight on the top (or bottom) third of today's members by `score`."""
        X = np.asarray(score, dtype=float)
        D = np.zeros((self.nD, self.S))
        for k in range(self.nD):
            ok = self.M[k] & np.isfinite(X[k])
            n = int(ok.sum())
            if n == 0:
                continue
            q = max(1, int(round(n * frac)))
            j = np.where(ok)[0]
            o = np.argsort(X[k, j])
            pick = j[o[-q:]] if top else j[o[:q]]
            D[k, pick] = 1.0 / q
        return D

    def ew(self, mask=None) -> np.ndarray:
        M = self.M if mask is None else (self.M & mask)
        n = self.M.sum(axis=1, keepdims=True)
        return np.where(M, 1.0 / np.maximum(n, 1), 0.0)

    def ewma_vol(self, com: int = 60) -> np.ndarray:
        return np.sqrt((self.R ** 2).ewm(com=com, min_periods=30).mean().values * 365)

    def ma_above(self, n: int) -> np.ndarray:
        return (self.C > self.C.rolling(n, min_periods=n).mean()).values


# ------------------------------------------------------------------ strategies (daily targets)

def donchian_state(ctx: Ctx, n: int) -> np.ndarray:
    """Zarattini-Pagani-Barbon: enter when the close breaks above the max close of the previous n days;
    trailing stop = max(previous stop, midpoint of max and min close over n days); exit below the stop."""
    C = ctx.C
    up = C.shift(1).rolling(n, min_periods=n).max().values
    mid = ((C.rolling(n, min_periods=n).max() + C.rolling(n, min_periods=n).min()) / 2).values
    c = C.values
    st = np.zeros_like(c)
    on = np.zeros(ctx.S, dtype=bool)
    stop = np.full(ctx.S, -np.inf)
    for k in range(ctx.nD):
        ck = c[k]
        with np.errstate(invalid="ignore"):
            enter = ~on & (ck > up[k])
            stop = np.where(enter, mid[k], np.where(on, np.fmax(stop, mid[k]), -np.inf))
            exitn = on & (ck < stop)
        on = (on | enter) & ~exitn & np.isfinite(ck)
        st[k] = on
    return st


def strategies(ctx: Ctx) -> list[dict]:
    """Each entry: name, source, rule, claim, pub (daily target or ('4h', W4)), grid {param: target} or None."""
    C, M, jb, je = ctx.C, ctx.M, ctx.jb, ctx.je
    btc = C[jb]
    vol = ctx.ewma_vol()
    out = []

    def add(name, source, rule, claim, pub, grid=None, pub_key=None):
        out.append(dict(name=name, source=source, rule=rule, claim=claim, pub=pub, grid=grid, pub_key=pub_key))

    # benchmarks
    add("BTC buy & hold", "benchmark", "100% BTC", "-", ctx.only(jb, np.ones(ctx.nD)))
    add("EW basket of members", "benchmark (LTW CMKT analogue, equal weight)", "1/N of every member, held continuously", "-", ctx.ew())
    g100 = (btc > btc.rolling(100, min_periods=100).mean()).values
    add("EW basket when BTC > MA100", "benchmark (System 11 gate)", "EW basket while BTC close > 100-day MA, else cash", "-",
        ctx.ew() * g100[:, None])

    # 1 Liu-Tsyvinski-Wu momentum
    mom = {n: ctx.weekly(ctx.tercile(C / C.shift(n) - 1, top=True)) for n in (7, 14, 21, 28)}
    add("XS momentum (top third, 3-week)", "Liu, Tsyvinski & Wu (2022) J. Finance 'Common risk factors in cryptocurrency'",
        "weekly: long the top third of members by past 3-week return, equal weight",
        "CMOM 3-week long-short ~3%/week, t>3 (2014-2018)", mom[21], mom, 21)
    # 2 size (proxy: dollar volume)
    size = {n: ctx.weekly(ctx.tercile(ctx.USD.rolling(n, min_periods=n).mean().values, top=False)) for n in (7, 30, 90)}
    add("XS size (small third, turnover proxy)", "Liu, Tsyvinski & Wu (2022) J. Finance",
        "weekly: long the smallest third of members (size proxied by mean daily USD volume, no market cap on disk)",
        "CSIZE small-minus-big ~3%/week (2014-2018)", size[30], size, 30)
    # 3 time-series momentum BTC
    ts = {n: ctx.weekly(ctx.only(jb, (btc / btc.shift(n) - 1 > 0).values)) for n in (7, 14, 28)}
    add("BTC TS momentum (1-week)", "Liu & Tsyvinski (2021) RFS 'Risks and returns of cryptocurrency'",
        "weekly: hold BTC next week if its past-week return > 0, else cash",
        "past 1-week return predicts 1-8 weeks ahead; long-cash Sharpe above buy & hold", ts[7], ts, 7)
    # 4 Detzel et al. MA ratio
    mas = (5, 10, 20, 50, 100)
    det = {n: ctx.only(jb, (btc > btc.rolling(n, min_periods=n).mean()).values) for n in mas + (200,)}
    add("BTC MA-ratio rules (5-100d ensemble)", "Detzel, Liu, Strauss, Zhou & Zhu (2021) Financial Management",
        "daily: BTC exposure = share of n in {5,10,20,50,100} with close > MA(n), rest in cash",
        "OOS R2 > 0 and Sharpe ~2x buy & hold (2011-2018)", np.mean([det[n] for n in mas], axis=0), det, None)
    # 5 short-term reversal
    rev = {n: ctx.tercile(C / C.shift(n) - 1, top=False) for n in (1, 2, 3, 5)}
    add("XS short-term reversal (1-day)", "Zaremba, Bilgin, Long, Mercik & Szczygielski (2021) IRFA 'Up or down?'",
        "daily: long the bottom third of members by yesterday's return",
        "daily reversal premium, strongest in small illiquid coins", rev[1], rev, 1)
    # 6 low volatility
    lv = {n: ctx.weekly(ctx.tercile(ctx.R.rolling(n, min_periods=n).std().values, top=False)) for n in (14, 30, 60, 90)}
    add("XS low volatility (30d)", "Burggraf & Rudolf (2021) J. Asset Mgmt 'Cryptocurrencies and the low volatility anomaly'",
        "weekly: long the lowest-volatility third of members (30-day daily std)",
        "low-vol portfolios beat high-vol on a risk-adjusted basis", lv[30], lv, 30)
    # 7 idiosyncratic volatility
    mkt = ctx.R.where(M).mean(axis=1)
    ivs = {}
    for n in (30, 60):
        cov = ctx.R.rolling(n, min_periods=n).cov(mkt)
        beta = cov.div(mkt.rolling(n, min_periods=n).var(), axis=0)
        res = ctx.R.sub(beta.mul(mkt, axis=0))
        ivs[n] = ctx.weekly(ctx.tercile(res.rolling(n, min_periods=n).std().values, top=True))
    add("XS high idiosyncratic vol (30d)", "Zhang & Li (2020) RIBAF 'Is idiosyncratic volatility priced in crypto?'",
        "weekly: long the top third of members by 30-day residual vol vs the EW market",
        "positive IVOL-return relation, significant", ivs[30], ivs, 30)
    # 8 illiquidity
    ami = {n: ctx.weekly(ctx.tercile((ctx.R.abs() / ctx.USD.replace(0, np.nan)).rolling(n, min_periods=n).mean().values, top=True))
           for n in (7, 30, 90)}
    add("XS illiquidity (Amihud 30d)", "Zhang & Li (2021) FRL / Wei (2018) Econ. Letters - illiquidity premium",
        "weekly: long the most illiquid third of members (mean |r|/USD volume, 30 days)",
        "illiquid coins earn higher next-week returns", ami[30], ami, 30)
    # 9 dual momentum BTC/ETH
    def dual(n):
        rb, re = (btc / btc.shift(n) - 1).values, (C[je] / C[je].shift(n) - 1).values
        D = np.zeros((ctx.nD, ctx.S))
        with np.errstate(invalid="ignore"):
            pick_e = M[:, je] & (re > rb)
            best = np.where(pick_e, re, rb)
            D[:, je] = pick_e & (best > 0)
            D[:, jb] = ~pick_e & (best > 0)
        return ctx.monthly(D)
    du = {n: dual(n) for n in (30, 60, 90, 180, 365)}
    add("Dual momentum BTC/ETH (12m)", "Antonacci (2014) 'Dual Momentum Investing', applied to BTC/ETH",
        "monthly: hold the better of BTC/ETH by 12-month return if it is > 0, else cash",
        "equity/bond evidence; crypto use is practitioner", du[365], du, 365)
    # 10 vol-scaled TSMOM
    def tsm(lbs, step):
        sig = np.mean([np.sign((C / C.shift(n) - 1).values) for n in lbs], axis=0)
        pos = np.clip(np.nan_to_num(sig), 0, None) * np.clip(0.40 / vol, 0, 1)
        n = M.sum(axis=1, keepdims=True)
        D = np.where(M, np.nan_to_num(pos) / np.maximum(n, 1), 0.0)
        return step(D)
    add("Vol-scaled TSMOM (12m, 40% vol)", "Moskowitz, Ooi & Pedersen (2012) JFE",
        "monthly: per member coin, long if 12-month return > 0, sized 40%/ex-ante vol (cap 1), 1/N each",
        "TSMOM Sharpe > 1 across 58 futures (1985-2009)", tsm((365,), ctx.monthly))
    add("Vol-scaled TSMOM (1/3/12m blend)", "Hurst, Ooi & Pedersen (2017) 'A century of evidence on trend-following'",
        "monthly: per coin signal = mean sign of 1/3/12-month returns (long part only), sized 40%/vol, 1/N each",
        "positive in every decade since 1880; crypto use is practitioner", tsm((30, 91, 365), ctx.monthly))
    # 11 per-coin MA trend
    mt = {n: ctx.ew(ctx.ma_above(n)) for n in (20, 50, 100, 200)}
    add("Per-coin MA trend (20/50/100/200 ensemble)", "Hudson & Urquhart (2021) Ann. Oper. Res.; Corbet et al. (2019) FRL",
        "daily: each member coin gets 1/N x share of n in {20,50,100,200} with close > MA(n)",
        "MA rules show significant predictability and beat buy & hold in crypto", np.mean(list(mt.values()), axis=0), mt, None)
    # 12 Donchian ensemble (Zarattini et al. 2025)
    lbs = (5, 10, 20, 30, 60, 90, 150, 250, 360)
    st = np.mean([donchian_state(ctx, n) for n in lbs], axis=0)
    vol90 = ctx.R.rolling(90, min_periods=30).std().values * np.sqrt(365)
    pos = st * np.clip(np.nan_to_num(0.25 / vol90), 0, 1)
    n = M.sum(axis=1, keepdims=True)
    add("Donchian ensemble, vol-targeted", "Zarattini, Pagani & Barbon (2025) SFI 25-80 'Catching crypto trends'",
        "daily: per coin, mean over 9 lookbacks (5..360d) of breakout state with midpoint trailing stop, sized 25%/vol90 (cap 1 spot), 1/N",
        "top-20 rotating portfolio: net Sharpe > 1.5, alpha 10.8%/yr vs BTC", np.where(M, pos / np.maximum(n, 1), 0.0))
    # 13 52-week high
    hi = {n: ctx.weekly(ctx.tercile((C / C.rolling(n, min_periods=60).max()).values, top=True)) for n in (90, 180, 365)}
    add("XS nearness to 52-week high", "Jia, Simkins, Yan, Zhang & Zhao (2025) SSRN 5386180 (George & Hwang 2004 in crypto)",
        "weekly: long the third of members closest to their 365-day high",
        "significant positive Nearness52 premium in the cross-section", hi[365], hi, 365)
    # 14 BTC dominance rotation
    def rot(n):
        r = (C / C.shift(n) - 1).values
        alts = M.copy()
        alts[:, jb] = False
        with np.errstate(invalid="ignore"):
            ra = np.nanmean(np.where(alts, r, np.nan), axis=1)
        go_alt = np.nan_to_num(ra) > np.nan_to_num(r[:, jb])
        na = alts.sum(axis=1, keepdims=True)
        D = np.where(alts, 1.0 / np.maximum(na, 1), 0.0) * go_alt[:, None]
        D[:, jb] = ~go_alt
        return ctx.weekly(D)
    ro = {n: rot(n) for n in (7, 14, 30, 60, 90)}
    add("BTC-dominance rotation (30d)", "practitioner ('altseason' index, blockchaincenter.net)",
        "weekly: hold the EW alt basket if its 30-day return beats BTC's, else hold BTC",
        "no peer-reviewed evidence", ro[30], ro, 30)
    # 15 calendar effects (4h level: the calendar is known in advance)
    g4 = ctx.w.P4["grid"]
    day4 = (g4 // P3.D1).astype("int64")                         # the day the holding interval [close i, close i+1) starts in
    wd4 = (day4 + 3) % 7
    W4 = np.zeros_like(ctx.w.P4["close"])
    W4[:, jb] = (wd4 == 0)
    add("BTC Monday effect", "Caporale & Plastun (2019) FRL 'The day of the week effect in the cryptocurrency market'",
        "hold BTC only during Mondays (UTC), cash otherwise", "abnormally high BTC returns on Mondays (2013-2017)", ("4h", W4))
    dd4 = day4.astype("datetime64[D]")
    dom4 = (dd4 - dd4.astype("datetime64[M]")).astype(int) + 1
    last4 = (dd4 + 1).astype("datetime64[M]") != dd4.astype("datetime64[M]")
    W4t = np.zeros_like(ctx.w.P4["close"])
    W4t[:, jb] = last4 | (dom4 <= 3)
    add("BTC turn of month", "Kaiser (2019) FRL 'Seasonality in cryptocurrencies' (equity ToM rule)",
        "hold BTC from the last day of a month through day 3 of the next, cash otherwise",
        "mixed: most crypto seasonalities do not survive", ("4h", W4t))
    return out


# ------------------------------------------------------------------ metrics

def per_year(d, dy, years=YEARS) -> dict:
    return {y: float(np.prod(1 + d[dy == y]) - 1) for y in years if (dy == y).any()}


def maxdd(d) -> float:
    eq = np.cumprod(1 + d)
    return float((1 - eq / np.maximum.accumulate(eq)).max()) if len(d) else 0.0


def sharpe(d) -> float:
    return float(d.mean() / (d.std(ddof=1) + 1e-12) * np.sqrt(365)) if len(d) > 2 else 0.0


def equal_risk_k(d) -> float:
    if maxdd(d) <= 0:
        return 0.0
    lo, hi = 0.0, 20.0
    for _ in range(60):
        m = (lo + hi) / 2
        if maxdd(np.clip(m * d, -0.99, None)) > DD_TARGET:
            hi = m
        else:
            lo = m
    return lo


def measure(d, dy) -> dict:
    res = np.isin(dy, RESEARCH)
    k = equal_risk_k(d[res])
    ds = np.clip(k * d, -0.99, None)
    py, pk = per_year(d, dy), per_year(ds, dy)
    return {"years": py, "max_dd": maxdd(d[res]), "sharpe": sharpe(d[res]), "k": k, "eq_years": pk,
            "eq_avg": float(np.mean([pk[y] for y in RESEARCH])), "avg": float(np.mean([py[y] for y in RESEARCH])),
            "pos_years": int(sum(py[y] > 0 for y in RESEARCH))}


def walk_forward(ctx: Ctx, grid: dict) -> tuple[np.ndarray, dict]:
    """Year N uses the parameter with the best daily Sharpe over 2019..N-1 (whole weight path switched at Jan 1)."""
    runs = {p: ctx.to4h(D) for p, D in grid.items()}
    rets = {p: ctx.run(W) for p, W in runs.items()}
    W = np.zeros_like(ctx.w.P4["close"])
    yr4 = ctx.w.P4["year"]
    picks = {}
    for N in YEARS:
        sc = {}
        for p, (d, dy) in rets.items():
            sel = (dy >= WF_FROM) & (dy < N)
            sc[p] = sharpe(d[sel])
        best = max(sc, key=sc.get)
        picks[N] = best
        W[yr4 == N] = runs[best][yr4 == N]
    return W, picks


# ------------------------------------------------------------------ main

def run_cap(cap: int, cut: int) -> list[dict]:
    w = H.world(cap, cut)
    ctx = Ctx(w)
    rows = []
    for s in strategies(ctx):
        W4 = s["pub"][1] if isinstance(s["pub"], tuple) else ctx.to4h(s["pub"])
        d, dy = ctx.run(W4)
        row = {"name": s["name"], "source": s["source"], "rule": s["rule"], "claim": s["claim"], "line": "published",
               **measure(d, dy)}
        row["exposure"] = float(np.mean(W4[np.isin(w.P4["year"], RESEARCH)].sum(axis=1)))
        rows.append(row)
        if s["grid"] and len(s["grid"]) > 1:
            Wf, picks = walk_forward(ctx, s["grid"])
            d, dy = ctx.run(Wf)
            r2 = {"name": s["name"] + " [walk-forward]", "source": s["source"], "rule": "parameter chosen on 2019..N-1 Sharpe",
                  "claim": "", "line": "walk-forward", "picks": {str(k): v for k, v in picks.items()}, **measure(d, dy)}
            r2["exposure"] = float(np.mean(Wf[np.isin(w.P4["year"], RESEARCH)].sum(axis=1)))
            rows.append(r2)
        print(f"cap{cap} {rows[-1]['name']}: eq_avg {rows[-1]['eq_avg']:+.3f}", flush=True)
    return rows


def pct(x, nd=0):
    return f"{x * 100:+.{nd}f}"


def report(res: dict) -> str:
    s11y = S11["years"]
    s11avg = float(np.mean([s11y[y] for y in RESEARCH]))
    L = ["# Classics 11 - published crypto strategies on System 11's data", "",
         f"Generated {res['generated']}. Script: `research/plan_v2/classics11.py`. Long-only spot, PIT top-N members, "
         "0.225%/side + ADV impact, signals read at the last daily close before each 4h decision. Each year from the "
         "same capital. DD and Sharpe on 2020-2025. **EqR** = the 2020-2025 average yearly return after rescaling the "
         "daily series to a 25% max DD (System 11 paper scale; k>1 is a comparison only, a spot book cannot lever). "
         "2026 (to date) is forward: never used to choose. Walk-forward lines choose their parameter for year N on 2019..N-1.", ""]
    for cap in res["caps"]:
        rows = res["caps"][cap]
        L += [f"## Top-{cap} universe", "",
              "| strategy | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | DD | Sharpe | expo | k | EqR avg | EqR 2025 | EqR 2026 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        L.append("| " + S11["name"] + " | " + " | ".join(pct(s11y[y]) for y in YEARS) + " | 25 | 1.40 | - | 1 | "
                 + f"{pct(s11avg)} | {pct(s11y[2025])} | {pct(s11y[2026], 1)} |")
        L.append("| System 11 law book (unscaled, reference) | " + " | ".join(pct(S11_LAW[y]) for y in YEARS) + " | 39 | - | - | - | - | - | - |")
        for r in rows:
            y = r["years"]
            L.append(f"| {r['name']} | " + " | ".join(pct(y.get(Y, 0)) for Y in YEARS)
                     + f" | {r['max_dd'] * 100:.0f} | {r['sharpe']:.2f} | {r['exposure']:.2f} | {r['k']:.2f} | {pct(r['eq_avg'])} | "
                     + f"{pct(r['eq_years'][2025])} | {pct(r['eq_years'].get(2026, 0), 1)} |")
        beat = [r["name"] for r in rows if r["eq_avg"] > s11avg]
        b25 = [r["name"] for r in rows if r["eq_years"][2025] > s11y[2025]]
        b26 = [r["name"] for r in rows if r["eq_years"].get(2026, 0) > s11y[2026]]
        all3 = [n for n in beat if n in b25 and n in b26]
        L += ["", f"Beat System 11 at equal risk (2020-25 avg > {pct(s11avg)}%): " + (", ".join(beat) or "none"),
              f"Beat System 11 in 2025 at equal risk (> {pct(s11y[2025])}%): " + (", ".join(b25) or "none"),
              f"Beat System 11 in 2026 YTD at equal risk (> {pct(s11y[2026], 1)}%): " + (", ".join(b26) or "none"),
              "All three: " + (", ".join(all3) or "none"), ""]
    L += ["## Sources and rules", "", "| strategy | source | rule | published claim |", "|---|---|---|---|"]
    for r in res["caps"][next(iter(res["caps"]))]:
        if r["line"] == "published":
            L.append(f"| {r['name']} | {r['source']} | {r['rule']} | {r['claim']} |")
    L += ["", "## Caveats", "",
          "- The universe is small (6 members in 2020, 13-14 later at cap 14): cross-sectional terciles are 2-5 coins, so "
          "factor results are noisy and differ in kind from the papers' 500-2000-coin samples.",
          "- No market caps on disk: size is proxied by mean daily USD volume (overlaps with illiquidity).",
          "- The papers' samples mostly end before 2020; our 2020-2026 test is genuinely out of their sample.",
          "- Equal-risk rescaling multiplies daily returns (costs included) and assumes leverage is available when k > 1.",
          "- 2026 is to date; one partial year is not evidence either way.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--caps", type=int, nargs="+", default=[14, 20])
    a = ap.parse_args()
    cut = int(np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None), "ns").astype("int64"))
    res = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "dd_target": DD_TARGET,
           "system11": {"paper_scale": S11["years"], "law_book_unscaled": S11_LAW}, "caps": {}}
    for cap in a.caps:
        res["caps"][cap] = run_cap(cap, cut)
    OUT.mkdir(parents=True, exist_ok=True)

    def js(o):
        if isinstance(o, dict):
            return {str(k): js(v) for k, v in o.items()}
        if isinstance(o, list):
            return [js(v) for v in o]
        if isinstance(o, (np.floating, float)):
            return round(float(o), 5)
        if isinstance(o, np.integer):
            return int(o)
        return o
    (OUT / "results.json").write_text(json.dumps(js(res), indent=1), encoding="utf-8")
    (OUT / "REPORT.md").write_text(report(res), encoding="utf-8")
    print("wrote", OUT / "REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
