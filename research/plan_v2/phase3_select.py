"""Plan v2, phase 3: selection redesign on a reduced space, honest execution (PLAN.md).

One pipeline, PIT only, research bars only (<= 2025):
  bars       15-minute candles resampled to 4h and 1d (UTC); a coin trades a bar only if it is in
             that year's PIT list (pit.union_lists, top 14 by turnover on 31 Dec of N-1)
  features   ~25 causal columns: returns over 1-90 days, volatility, distance to 20/50/100-day
             averages, RSI, dollar-volume z, taker share, range; BTC returns and regime, breadth and
             market return over the members; cross-sectional ranks
  target     ONE model, the expected NET return of an entry: close t+1 to close t+1+H, minus the
             0.45% round trip and twice the pair's impact (phase 0)
  model      ridge or HistGradientBoosting, 4 bagged fits on 80% row subsamples per seed set; walk-
             forward per test year N, trained on member rows of years < N whose label ends before N
  book       target weights at the close of t, executed at the close of t+1 (lag one own bar), on a
             common 4h grid; cost per side = 0.225% + square-root impact (sigma, ADV of N-1, $100k
             book); no stops, so intrabar order does not matter; cash is a valid position
  rule       hold the top K by prediction among coins with prediction > 0; a held coin stays while
             in the top 2K and above 0 (hysteresis); optional gate: nothing when BTC <= its 100d MA

Five swept levers (plan item 1), everything else fixed:
  timeframe 4h | 1d,  horizon H 1 | 3 | 7 days,  K 3 | 5 | 8,  gate on | off,  model ridge | gbm  -> 72
Nested selection per test year N in 2022-2025, on the years 2021..N-1 of each configuration:
  eligible  max DD <= 18% on those years (plan item 3; cash allowed, no "every year positive",
            no minimum trade count)
  score     p5 of the 10-day block-bootstrap Sharpe (the lower confidence bound)
  argmax    the best one's year N
  bagging   average of the executed weights of the top k (10, 20) configurations, re-costed
Benchmarks on the same book: rule c (EW members when BTC > MA100) and rule d (c, x2 top-7 by 90d).
Seed noise: per configuration and year, |return seed set 1 - seed set 2|, median vs 7.7 points.

    python research/plan_v2/phase3_select.py
"""

from __future__ import annotations

import json
import time
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
OUT = HERE / "phase3_results.json"
H4 = 4 * 3600 * 10**9
D1 = 24 * 3600 * 10**9
BARS_PER_DAY = {"4h": 6, "1d": 1}
TEST_YEARS = (2021, 2022, 2023, 2024, 2025)
NESTED_YEARS = (2022, 2023, 2024, 2025)
HALF_COST = 0.00225
BOOK = 100_000.0
DD_MAX = 0.18
SEED_SETS = {"s1": (11, 12, 13, 14), "s2": (21, 22, 23, 24)}
LEVERS = {"tf": ("4h", "1d"), "h_days": (1, 3, 7), "k": (3, 5, 8), "gate": (True, False), "model": ("ridge", "gbm")}
BAG_K = (10, 20)
BLOCK, DRAWS = 10, 1000


# ------------------------------------------------------------------ data

def load_bars() -> tuple[dict, dict]:
    """{tf: {coin: DataFrame(open, high, low, close, usd, taker)}} on each timeframe's own grid,
    and the PIT lists. Cached as parquet-free pickles (pandas)."""
    from system010_conditioned_rl import pit
    lists = {int(y): list(v) for y, v in pit.union_lists(pit.CAP, pit.UNION_YEARS).items()}
    CACHE.mkdir(exist_ok=True)
    f = CACHE / "bars.pkl"
    if f.exists():
        return pd.read_pickle(f), lists
    from quantlab_catalog.candles import research
    coins = sorted({s for v in lists.values() for s in v})
    out = {"4h": {}, "1d": {}}
    for s in coins:
        bars = research([s]).get(s) or []
        if not bars:
            continue
        df = pd.DataFrame({"ns": [np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64") for b in bars],
                           "open": [b.open for b in bars], "high": [b.high for b in bars],
                           "low": [b.low for b in bars], "close": [b.close for b in bars],
                           "usd": [b.volume * b.close for b in bars],
                           "tk": [(b.taker_buy_volume or 0.0) * b.close for b in bars]})
        for tf, step in (("4h", H4), ("1d", D1)):
            g = df.groupby(df["ns"] // step * step + step)   # stamped at the bar's CLOSE time
            r = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                              "close": g["close"].last(), "usd": g["usd"].sum(), "tk": g["tk"].sum()})
            r["taker"] = r["tk"] / r["usd"].replace(0, np.nan)
            out[tf][s] = r.drop(columns="tk")
        print(f"  {s}: {len(df):,} 15m bars", flush=True)
    pd.to_pickle(out, f)
    return out, lists


def year_of(ns: np.ndarray) -> np.ndarray:
    # a bar stamped at its close belongs to the year its OPEN is in
    return (ns - 1).astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970


def panel(bars: dict, tf: str, lists: dict) -> dict:
    """Aligned matrices on one timeframe: close (T x S), member mask, grid, coins."""
    coins = sorted(bars[tf])
    grid = np.unique(np.concatenate([bars[tf][s].index.values for s in coins]))
    grid = grid[(year_of(grid) >= 2020) & (year_of(grid) <= 2025)]
    cols = {}
    for c in ("open", "high", "low", "close", "usd", "taker"):
        cols[c] = np.column_stack([bars[tf][s][c].reindex(grid).values for s in coins]).astype(float)
    yr = year_of(grid)
    member = np.zeros((len(grid), len(coins)), dtype=bool)
    for y, v in lists.items():
        for j, s in enumerate(coins):
            if s in v:
                member[yr == y, j] = True
    member &= np.isfinite(cols["close"])
    return {"grid": grid, "coins": coins, "year": yr, "member": member, **cols}


# ------------------------------------------------------------------ features

def features(P: dict, tf: str) -> tuple[np.ndarray, list[str]]:
    """(T x S x F) causal features; every column at bar t reads bars <= t only."""
    n = BARS_PER_DAY[tf]
    c = pd.DataFrame(P["close"])
    lr = np.log(c).diff()
    f, names = [], []

    def add(name, x):
        f.append(np.asarray(x, dtype=float)); names.append(name)
    for d in (1, 3, 7, 14, 30, 60, 90):
        add(f"ret_{d}d", c / c.shift(d * n) - 1)
    if n > 1:
        add("ret_1bar", c / c.shift(1) - 1)
    for d in (20, 60):
        add(f"vol_{d}d", lr.rolling(d * n, min_periods=d * n // 2).std())
    add("vol_ratio", f[names.index("vol_20d")] / (f[names.index("vol_60d")] + 1e-12))
    for d in (20, 50, 100):
        add(f"ma_{d}d", c / c.rolling(d * n, min_periods=d * n // 2).mean() - 1)
    up = lr.clip(lower=0).rolling(14).mean(); dn = (-lr.clip(upper=0)).rolling(14).mean()
    add("rsi14", up / (up + dn + 1e-12))
    lu = np.log(pd.DataFrame(P["usd"]).replace(0, np.nan))
    add("dvol_z", (lu - lu.rolling(30 * n, min_periods=10 * n).mean()) / (lu.rolling(30 * n, min_periods=10 * n).std() + 1e-9))
    add("taker", pd.DataFrame(P["taker"]).rolling(n).mean() - 0.5)
    add("range", ((pd.DataFrame(P["high"]) - pd.DataFrame(P["low"])) / c).rolling(n).mean())
    # market columns, broadcast to every coin
    j_btc = P["coins"].index("BTCUSDT")
    btc = c[j_btc]
    T, S = c.shape
    bc = lambda x: np.repeat(np.asarray(x, dtype=float)[:, None], S, axis=1)  # noqa: E731
    for d in (1, 7, 30):
        add(f"btc_ret_{d}d", bc(btc / btc.shift(d * n) - 1))
    add("btc_regime", bc((btc > btc.rolling(100 * n, min_periods=100 * n).mean()).astype(float)))
    mem = P["member"]
    ma50 = f[names.index("ma_50d")]
    with np.errstate(invalid="ignore"):
        add("breadth", bc(np.nansum((ma50 > 0) & mem, axis=1) / np.maximum(mem.sum(axis=1), 1)))
        r7 = np.where(mem, f[names.index("ret_7d")], np.nan)
        add("mkt_ret_7d", bc(np.nanmean(r7, axis=1)))
    for nm in ("ret_30d", "ret_7d", "vol_20d", "dvol_z"):
        x = np.where(mem, f[names.index(nm)], np.nan)
        add(f"xrank_{nm}", pd.DataFrame(x).rank(axis=1, pct=True).values)
    X = np.stack(f, axis=2)
    X[~mem] = np.nan
    return X, names


# ------------------------------------------------------------------ costs and target

def impact(P: dict, tf: str) -> np.ndarray:
    """(years 2020..2026 x S) per-side impact from year N-1 medians (year N when N-1 is empty);
    order = the largest stake of a $100k book with K = 3."""
    n = BARS_PER_DAY[tf]
    out = np.zeros((7, len(P["coins"])))
    c, usd, yr = P["close"], P["usd"], P["year"]
    for i, y in enumerate(range(2020, 2027)):
        for j in range(len(P["coins"])):
            sel = (yr == y - 1) & np.isfinite(c[:, j])
            if sel.sum() < 30 * n:
                sel = (yr == y) & np.isfinite(c[:, j])
            if sel.sum() < 10 * n:
                out[i, j] = 0.003
                continue
            cd, ud = c[sel, j][n - 1::n], usd[sel, j][: (sel.sum() // n) * n].reshape(-1, n).sum(axis=1)
            sig = np.std(np.diff(np.log(cd))) if len(cd) > 2 else 0.05
            out[i, j] = float(sig * np.sqrt(BOOK / 3 / max(np.median(ud), 1.0)))
    return out


def target(P: dict, tf: str, h_days: int, imp: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Net return of an entry decided at t: close t+1 -> close t+1+H, minus the round trip;
    and the bar index the label ends on (for the embargo)."""
    n = BARS_PER_DAY[tf]
    H = h_days * n
    c = P["close"]
    T = len(c)
    y = np.full_like(c, np.nan)
    y[: T - 1 - H] = c[1 + H:] / c[1: T - H] - 1
    yi = np.clip(P["year"] - 2020, 0, 6)
    y -= 2 * HALF_COST + 2 * imp[yi]
    end = np.minimum(np.arange(T) + 1 + H, T - 1)
    return np.clip(y, -0.5, 0.5), end


# ------------------------------------------------------------------ models

def fit_predict(X, y, end, P, model: str, seeds, N: int) -> np.ndarray:
    """Train on member rows of years < N whose label ends before N; predict year N's bars."""
    yr = P["year"]
    T, S, F = X.shape
    first_N = int(np.searchsorted(P["grid"], np.datetime64(f"{N}-01-01", "ns").astype("int64"), side="right"))
    tr_rows = (yr < N) & (end < first_N)
    Xt = X[tr_rows].reshape(-1, F); yt = y[tr_rows].reshape(-1)
    ok = np.isfinite(Xt).all(axis=1) & np.isfinite(yt)
    Xt, yt = Xt[ok], yt[ok]
    te = yr == N
    Xp = X[te].reshape(-1, F)
    okp = np.isfinite(Xp).all(axis=1)
    pred = np.full(len(Xp), np.nan)
    if len(yt) < 500 or not okp.any():
        return np.full((int(te.sum()), S), np.nan)
    mu, sd = Xt.mean(axis=0), Xt.std(axis=0) + 1e-9
    acc = np.zeros(int(okp.sum()))
    for seed in seeds:
        rng = np.random.default_rng(seed)
        pick = rng.random(len(yt)) < 0.8
        if model == "ridge":
            m = Ridge(alpha=10.0).fit((Xt[pick] - mu) / sd, yt[pick])
            acc += m.predict((Xp[okp] - mu) / sd)
        else:
            m = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                              min_samples_leaf=200, random_state=seed)
            acc += m.fit(Xt[pick], yt[pick]).predict(Xp[okp])
    pred[okp] = acc / len(seeds)
    return pred.reshape(int(te.sum()), S)


# ------------------------------------------------------------------ book on the 4h grid

def decide(pred: np.ndarray, member: np.ndarray, k: int, gate_ok: np.ndarray | None, hold: int = 1) -> np.ndarray:
    """Target weights at each bar's close, consistent with the target: a coin is entered when it
    is in the top k with prediction > 0 and a slot is free, then HELD for `hold` bars (the label's
    horizon); at expiry it is kept, without a trade, while still in the top 2k and above 0. A coin
    leaving the PIT list or the gate closing sells at once. 1/k of the book per slot."""
    T, S = pred.shape
    W = np.zeros((T, S))
    held = np.zeros(S, dtype=bool)
    since = np.zeros(S, dtype=int)
    for t in range(T):
        if gate_ok is not None and not gate_ok[t]:
            held[:] = False
            continue
        p = np.where(member[t] & np.isfinite(pred[t]), pred[t], -np.inf)
        order = np.argsort(-p)
        rank = np.empty(S, dtype=int); rank[order] = np.arange(S)
        since[held] += 1
        expired = held & (since >= hold)
        drop = (held & ~member[t]) | (expired & ~((rank < 2 * k) & (p > 0)))
        held &= ~drop
        since[expired & held] = 0          # extended without a trade
        free = k - int(held.sum())
        if free > 0:
            cand = [j for j in order[:k] if not held[j] and p[j] > 0][:free]
            held[cand] = True
            since[cand] = 0
        W[t, held] = 1.0 / k
    return W


def to_exec_4h(W: np.ndarray, grid_tf: np.ndarray, grid4: np.ndarray) -> np.ndarray:
    """Weights decided at bar t of its own grid, executed at bar t+1's close, mapped onto the 4h
    grid: the 4h interval starting at T4[i] holds the last decision executed at or before T4[i]."""
    exec_at = np.r_[grid_tf[1:], np.iinfo(np.int64).max]
    i = np.searchsorted(exec_at, grid4, side="right") - 1
    out = np.zeros((len(grid4), W.shape[1]))
    ok = i >= 0
    out[ok] = W[i[ok]]
    return out


def simulate(Wx: np.ndarray, P4: dict, imp4: np.ndarray) -> dict:
    """Executed 4h weights -> net 4h returns -> daily returns per year, DD, trades proxy."""
    c = P4["close"]
    R = np.zeros_like(c)
    R[:-1] = np.nan_to_num(c[1:] / c[:-1] - 1)
    alive = np.isfinite(c)
    Wx = np.where(alive, Wx, 0.0)
    dW = np.abs(np.diff(np.r_[np.zeros((1, Wx.shape[1])), Wx], axis=0))
    yi = np.clip(P4["year"] - 2020, 0, 6)
    cost = (dW * (HALF_COST + imp4[yi])).sum(axis=1)
    gross = (Wx * R).sum(axis=1)
    r = gross - cost
    day = P4["grid"] // D1
    last = np.r_[day[1:] != day[:-1], True]

    def to_daily(x):
        eod = np.cumprod(1 + x)[last]
        return np.r_[eod[0] - 1, eod[1:] / eod[:-1] - 1]
    dyear = year_of(P4["grid"][last])
    yr4 = P4["year"]
    return {"daily": to_daily(r), "gross_daily": to_daily(gross), "dyear": dyear,
            "turnover_per_year": {int(y): round(float(dW[yr4 == y].sum()), 1) for y in TEST_YEARS},
            "exposure_per_year": {int(y): round(float(Wx[yr4 == y].sum(axis=1).mean()), 3) for y in TEST_YEARS}}


def year_stats(sim: dict, years) -> dict:
    out = {}
    for y in years:
        d = sim["daily"][sim["dyear"] == y]
        if not len(d):
            continue
        eq = np.cumprod(1 + d)
        g = sim["gross_daily"][sim["dyear"] == y]
        out[int(y)] = {"return": round(float(eq[-1] - 1), 4), "max_dd": round(float((1 - eq / np.maximum.accumulate(eq)).max()), 4),
                       "gross": round(float(np.prod(1 + g) - 1), 4),
                       "turnover": sim["turnover_per_year"].get(int(y)), "exposure": sim["exposure_per_year"].get(int(y))}
    return out


def boot_sharpe_p5(d: np.ndarray, seed: int = 3) -> float:
    n = len(d)
    if n < 60 or d.std() == 0:
        return -np.inf
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / BLOCK))
    idx = (rng.integers(0, n, (DRAWS, nb))[:, :, None] + np.arange(BLOCK)).reshape(DRAWS, -1)[:, :n] % n
    s = d[idx]
    sh = s.mean(1) / (s.std(1, ddof=1) + 1e-12) * np.sqrt(365)
    return float(np.percentile(sh, 5))


def ci(d: np.ndarray) -> dict:
    n = len(d)
    rng = np.random.default_rng(7)
    nb = int(np.ceil(n / BLOCK))
    idx = (rng.integers(0, n, (5000, nb))[:, :, None] + np.arange(BLOCK)).reshape(5000, -1)[:, :n] % n
    s = d[idx]
    ann = np.exp(np.log1p(s).sum(1) * 365 / n) - 1
    sh = s.mean(1) / (s.std(1, ddof=1) + 1e-12) * np.sqrt(365)
    eq = np.cumprod(1 + d)
    q = lambda a: [round(float(v), 4) for v in np.percentile(a, [5, 50, 95])]  # noqa: E731
    return {"ann_return": round(float(np.exp(np.log1p(d).sum() * 365 / n) - 1), 4), "ann_p5_p50_p95": q(ann),
            "sharpe": round(float(d.mean() / (d.std(ddof=1) + 1e-12) * np.sqrt(365)), 3), "sharpe_p5_p50_p95": q(sh),
            "max_dd": round(float((1 - eq / np.maximum.accumulate(eq)).max()), 4),
            "total": round(float(eq[-1] - 1), 4)}


# ------------------------------------------------------------------ main

def prepare() -> dict:
    """Panels, features, costs, gate and walk-forward predictions (shared with phase 4)."""
    t0 = time.time()
    bars, lists = load_bars()
    P = {tf: panel(bars, tf, lists) for tf in ("4h", "1d")}
    P4 = P["4h"]
    assert P["1d"]["coins"] == P4["coins"]
    imp = {tf: impact(P[tf], tf) for tf in P}
    X = {tf: features(P[tf], tf) for tf in P}
    print(f"[{time.time() - t0:.0f}s] panels: 4h {P4['close'].shape}, 1d {P['1d']['close'].shape}, "
          f"{len(X['4h'][1])} features", flush=True)
    gate = {}
    for tf in P:
        n = BARS_PER_DAY[tf]
        btc = pd.Series(P[tf]["close"][:, P[tf]["coins"].index("BTCUSDT")])
        gate[tf] = (btc > btc.rolling(100 * n, min_periods=100 * n).mean()).values
    # predictions per (tf, H, model, seed set), years 2021-2025
    preds = {}
    IC = {}
    for tf, h, model, ss in product(LEVERS["tf"], LEVERS["h_days"], LEVERS["model"], SEED_SETS):
        y, end = target(P[tf], tf, h, imp[tf])
        pr = np.full_like(P[tf]["close"], np.nan)
        for N in TEST_YEARS:
            pr[P[tf]["year"] == N] = fit_predict(X[tf][0], y, end, P[tf], model, SEED_SETS[ss], N)
        preds[(tf, h, model, ss)] = pr
        ics = {}
        for N in TEST_YEARS:
            rows = np.flatnonzero(P[tf]["year"] == N)
            vals = []
            for t in rows[:: max(1, BARS_PER_DAY[tf])]:
                a, b = pr[t], y[t]
                ok = np.isfinite(a) & np.isfinite(b) & P[tf]["member"][t]
                if ok.sum() >= 5:
                    vals.append(pd.Series(a[ok]).corr(pd.Series(b[ok]), method="spearman"))
            hit = np.isfinite(pr[rows]) & np.isfinite(y[rows]) & (pr[rows] > 0)
            ics[N] = {"ic": round(float(np.nanmean(vals)), 4) if vals else None,
                      "ic_t": round(float(np.nanmean(vals) / (np.nanstd(vals) + 1e-12) * np.sqrt(len(vals))), 2) if vals else None,
                      "share_pred_pos": round(float(hit.mean()), 3),
                      "net_when_pred_pos": round(float(np.nanmean(y[rows][hit])), 5) if hit.any() else None,
                      "net_all": round(float(np.nanmean(np.where(P[tf]["member"][rows], y[rows], np.nan))), 5)}
        IC[f"{tf} H={h}d {model} {ss}"] = ics
        print(f"[{time.time() - t0:.0f}s] fitted {tf} H={h}d {model} {ss}", flush=True)
    return {"P": P, "P4": P4, "imp": imp, "X": X, "gate": gate, "preds": preds, "IC": IC, "t0": t0}


def main() -> int:
    st = prepare()
    P, P4, imp, gate, preds, IC, t0 = (st[k] for k in ("P", "P4", "imp", "gate", "preds", "IC", "t0"))
    # every configuration: executed 4h weights, simulation
    cfgs = [dict(zip(LEVERS, v)) for v in product(*LEVERS.values())]
    runs = {}
    for ss in SEED_SETS:
        for cfg in cfgs:
            tf = cfg["tf"]
            W = decide(preds[(tf, cfg["h_days"], cfg["model"], ss)], P[tf]["member"], cfg["k"],
                       gate[tf] if cfg["gate"] else None, hold=cfg["h_days"] * BARS_PER_DAY[tf])
            Wx = to_exec_4h(W, P[tf]["grid"], P4["grid"])
            sim = simulate(Wx, P4, imp["4h"])
            key = json.dumps(cfg, sort_keys=True)
            runs[(ss, key)] = {"Wx": Wx, "sim": sim, "years": year_stats(sim, TEST_YEARS)}
        print(f"[{time.time() - t0:.0f}s] simulated {len(cfgs)} configurations on {ss}", flush=True)
    # benchmarks c and d on the same book (daily decisions, monthly membership refresh for d)
    Pd = P["1d"]
    bench = {}
    mem, gd = Pd["member"], gate["1d"]
    Wc = np.where(mem & gd[:, None], 1.0, 0.0)
    Wc = Wc / np.maximum(Wc.sum(axis=1, keepdims=True), 1)
    r90 = pd.DataFrame(Pd["close"]).pct_change(90).values
    month = Pd["grid"].astype("datetime64[ns]").astype("datetime64[M]")
    Wd = np.zeros_like(Wc)
    cur = None
    for t in range(len(Wc)):
        if cur is None or month[t] != month[t - 1]:
            p = np.where(mem[t] & np.isfinite(r90[t]), r90[t], -np.inf)
            top = np.argsort(-p)[:7]
            cur = np.ones(Wc.shape[1]); cur[top] = 2.0
        w = np.where(mem[t] & gd[t], cur, 0.0)
        Wd[t] = w / max(w.sum(), 1e-12) if w.sum() > 0 else 0.0
    for name, W in (("rule_c", Wc), ("rule_d", Wd)):
        sim = simulate(to_exec_4h(W, Pd["grid"], P4["grid"]), P4, imp["4h"])
        bench[name] = {"years": year_stats(sim, TEST_YEARS),
                       "nested_span": ci(sim["daily"][np.isin(sim["dyear"], NESTED_YEARS)])}
    # nested selection
    res = {"configs": len(cfgs), "levers": LEVERS, "benchmarks": bench, "seed_sets": {}, "ic": IC}
    for ss in SEED_SETS:
        picks, curves = {}, {"argmax": [], **{f"bag{k}": [] for k in BAG_K}}
        for N in NESTED_YEARS:
            past = tuple(y for y in TEST_YEARS if y < N)
            scored = []
            for cfg in cfgs:
                run = runs[(ss, json.dumps(cfg, sort_keys=True))]
                if max(run["years"][y]["max_dd"] for y in past) > DD_MAX:
                    continue
                d = run["sim"]["daily"][np.isin(run["sim"]["dyear"], past)]
                scored.append((boot_sharpe_p5(d), json.dumps(cfg, sort_keys=True)))
            scored.sort(reverse=True)
            picks[N] = {"eligible": len(scored), "top": [(round(s, 3), k) for s, k in scored[:5]]}
            sel_rows = P4["year"] == N
            if not scored:   # nothing passes: cash
                for c_ in curves:
                    curves[c_].append(np.zeros(int((np.unique(P4["grid"][sel_rows] // D1)).size)))
                continue
            for name, kk in (("argmax", 1), *((f"bag{k}", k) for k in BAG_K)):
                keys = [k for _, k in scored[:kk]]
                Wx = np.mean([runs[(ss, k)]["Wx"] for k in keys], axis=0)
                sim = simulate(Wx, P4, imp["4h"])
                curves[name].append(sim["daily"][sim["dyear"] == N])
                picks[N].setdefault("year_return", {})[name] = year_stats(sim, (N,)).get(N)
        res["seed_sets"][ss] = {"picks": picks, "curves": {k: ci(np.concatenate(v)) for k, v in curves.items()}}
    # seed noise: same configuration, other seed set
    diffs = []
    for cfg in cfgs:
        key = json.dumps(cfg, sort_keys=True)
        for y in TEST_YEARS:
            diffs.append(abs(runs[("s1", key)]["years"][y]["return"] - runs[("s2", key)]["years"][y]["return"]))
    res["seed_noise_points"] = {"median": round(float(np.median(diffs)) * 100, 2),
                                "p75": round(float(np.percentile(diffs, 75)) * 100, 2),
                                "p90": round(float(np.percentile(diffs, 90)) * 100, 2), "old_system_median": 7.7}
    res["all_configs"] = {f"{ss} {k}": v["years"] for (ss, k), v in runs.items()}
    res["minutes"] = round((time.time() - t0) / 60, 1)
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("benchmarks", "seed_noise_points")}, indent=1, default=str))
    for ss in SEED_SETS:
        print(ss, json.dumps(res["seed_sets"][ss]["curves"], default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
