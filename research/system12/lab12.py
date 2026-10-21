"""System 12 lab - the whole machine on System 12 (operator 2026-10-21: "dedicate all the CPU to system 12").

Endless random search over a much larger grammar than system12_ls.py, honest scoreboard:

    regime    1-3 signals from ~60 (BTC trend: averages, EMA slopes, momentum, MA-ratio rules, Donchian, RSI,
              Bollinger; risk: volatility regime, drawdown from the 1-year high; market: breadth, ETH/BTC;
              positioning: BTC funding; macro, lagged a day: S&P 500 and Nasdaq trend, VIX, dollar, Fed net
              liquidity, yields, Fear & Greed), combined by AND / mean / majority, with a hysteresis of 0-7 days
    long      BTC | ETH | BTC+ETH | equal weight | inverse volatility | 5 most traded
    short     none | BTC | BTC+ETH, when the regime is fully or mostly bearish, 25-100% size
    sizing    volatility target 0 / 30 / 40 / 50 / 60 / 80%, exposure in steps of 25%
    venue     USD-M perpetuals, 0.10%/side + impact, funding charged

Each worker writes its configurations with their per-fold objective (the law on 2019..N-1) and yearly returns.
The merger (`--merge`, run by the controller every few minutes) applies the selection walk-forward: for year N,
the average of the 20 best configurations on 2019..N-1, read on N. That chain is the honest result. 2026 is
only ever read, never used to choose.

    python research/system12/lab12.py --worker 3          (an endless worker)
    python research/system12/lab12.py --merge             -> lab/status.json, lab/history.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import system12 as S
import system12_ls as L

LAB = S.HERE / "lab"
STOP = LAB / "STOP"
FLUSH = 1000
LONG = ("BTC", "ETH", "BTC+ETH", "equal weight", "inverse volatility", "5 most traded")
SHORT_B = ("BTC", "BTC+ETH")
VT = (0.0, 0.3, 0.4, 0.5, 0.6, 0.8)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ the world, once per process

def build():
    eng, regs = L.setup()
    ctx, w = eng.ctx, eng.w
    C, M = ctx.C, ctx.M
    btc, eth = C[ctx.jb], C[ctx.je]
    sig = {k: v for k, v in S.signals(ctx).items()}
    ema = lambda s, n: s.ewm(span=n, adjust=False, min_periods=n // 2).mean()  # noqa: E731
    for n in (20, 50, 100, 200):
        e = ema(btc, n)
        sig[f"BTC EMA{n} rising"] = (e > e.shift(5)).values.astype(float)
    d = btc.diff()
    rsi = 100 - 100 / (1 + d.clip(lower=0).ewm(alpha=1 / 14).mean() / (-d.clip(upper=0)).ewm(alpha=1 / 14).mean())
    for t in (45, 50, 55):
        sig[f"BTC RSI14 > {t}"] = (rsi > t).values.astype(float)
    m20, s20 = btc.rolling(20).mean(), btc.rolling(20).std()
    sig["BTC above Bollinger mid"] = (btc > m20).values.astype(float)
    sig["BTC Bollinger %B > 0.8"] = (((btc - (m20 - 2 * s20)) / (4 * s20)) > 0.8).values.astype(float)
    vol = btc.pct_change().rolling(30).std()
    sig["BTC vol below 1y median"] = (vol < vol.rolling(365, min_periods=180).median()).values.astype(float)
    hi = btc.rolling(365, min_periods=100).max()
    for t in (0.2, 0.35):
        sig[f"BTC within {int(t * 100)}% of 1y high"] = (btc > hi * (1 - t)).values.astype(float)
    r = eth / btc
    sig["ETH/BTC > its 50d avg"] = (r > r.rolling(50).mean()).values.astype(float)
    f4 = w.fund4[:, ctx.jb]
    fd = pd.Series(f4).groupby(np.clip(np.searchsorted(w.P["1d"]["grid"], w.P4["grid"], side="left"), 0, ctx.nD - 1)).sum()
    fdaily = pd.Series(np.zeros(ctx.nD))
    fdaily[fd.index] = fd.values
    fdaily = fdaily.shift(1)
    sig["BTC funding 7d > 0"] = (fdaily.rolling(7).sum() > 0).values.astype(float)
    sig["BTC funding 7d < 0.1%"] = (fdaily.rolling(7).sum() < 0.001).values.astype(float)
    days = [str((g - 1).astype("datetime64[ns]"))[:10] for g in w.P["1d"]["grid"]]
    mac = {k: pd.Series(v) for k, v in L.R.macro_series(days).items()}
    for k, nm in (("spx", "S&P 500"), ("ndx", "Nasdaq")):
        for n in (50, 200):
            sig[f"{nm} > {n}d avg"] = (mac[k] > mac[k].rolling(n, min_periods=n // 2).mean()).values.astype(float)
    sig["VIX < 20"] = (mac["vix"] < 20).values.astype(float)
    sig["VIX < 25"] = (mac["vix"] < 25).values.astype(float)
    sig["dollar < 50d avg"] = (mac["dxy"] < mac["dxy"].rolling(50, min_periods=25).mean()).values.astype(float)
    sig["Fed net liquidity 60d rising"] = (mac["netliq"] > mac["netliq"].shift(60)).values.astype(float)
    sig["US 2y yield 60d falling"] = (mac["y2"] < mac["y2"].shift(60)).values.astype(float)
    sig["Fear & Greed > 50"] = (mac["fg"] > 50).values.astype(float)
    sig["Fear & Greed < 75"] = (mac["fg"] < 75).values.astype(float)
    sig = {k: np.nan_to_num(np.asarray(v, dtype=float)) for k, v in sig.items()}
    # extra long baskets
    bk = eng.bk
    usd = ctx.USD.rolling(30, min_periods=10).mean().values
    top = np.zeros((ctx.nD, ctx.S))
    for k in range(ctx.nD):
        j = np.where(M[k] & np.isfinite(usd[k]))[0]
        if len(j):
            p = j[np.argsort(usd[k, j])[-5:]]
            top[k, p] = 1 / len(p)
    extra = {"ETH": ctx.only(ctx.je, 1.0), "5 most traded": top}
    for k, v in extra.items():
        bk[k] = v
        eng.b4[k] = ctx.to4h(v)
        eng.bret[k] = np.nansum(v * np.nan_to_num(ctx.R.values), axis=1)
    return eng, sig


def regime(sig: dict, cfg: dict) -> np.ndarray:
    X = np.array([sig[s] for s in cfg["sig"]])
    op = cfg["op"]
    reg = X.min(axis=0) if op == "and" else X.mean(axis=0) if op == "mean" else (X.mean(axis=0) > 0.5).astype(float)
    h = cfg["hyst"]
    if h:                                    # a new level counts only after it held h days
        out, cur, run, cand = np.empty_like(reg), reg[0], 0, reg[0]
        for i, x in enumerate(reg):
            if x == cur:
                run = 0
            elif x == cand:
                run += 1
                if run >= h:
                    cur, run = x, 0
            else:
                cand, run = x, 1
                if h <= 1:
                    cur, run = x, 0
            out[i] = cur
        reg = out
    return reg


def gen(rng: random.Random, names: list[str]) -> dict:
    k = rng.choice((1, 2, 2, 3))
    short = None
    if rng.random() < 0.7:
        short = [rng.choice(SHORT_B), rng.choice((0.0, 0.0, 0.5)), rng.choice((0.25, 0.5, 0.5, 1.0))]
    return {"sig": sorted(rng.sample(names, k)), "op": rng.choice(("and", "mean", "maj")) if k > 1 else "and",
            "hyst": rng.choice((0, 0, 1, 3, 7)), "long": rng.choice(LONG), "vt": rng.choice(VT), "short": short}


def weights(eng, sig, cfg) -> np.ndarray:
    return eng.weights_ls(regime(sig, cfg), cfg["long"], cfg["vt"], tuple(cfg["short"]) if cfg["short"] else None)


KEEP = 300          # per worker and fold: the global top 20 of any fold is always inside the union of these
SAMPLE = 4000       # reservoir of yearly returns, for "median of all configurations"


def worker(wid: int) -> int:
    """Endless. Keeps, per fold, its KEEP best configurations (all the walk-forward selection can ever need)
    and a random sample of yearly returns; rewrites lab/w<id>.top.json every 2,000 configurations."""
    LAB.mkdir(parents=True, exist_ok=True)
    eng, sig = build()
    names = sorted(sig)
    dy = eng.dy
    rng = random.Random(wid * 7919 + int(time.time()))
    ft = LAB / f"w{wid}.top.json"
    prev = json.loads(ft.read_text(encoding="utf-8")) if ft.exists() else {}
    pool = {json.dumps(r["c"], sort_keys=True): r for r in prev.get("pool", [])}
    sample, total = prev.get("sample", []), prev.get("total", 0)
    n, t0 = 0, time.time()
    while not STOP.exists():
        cfg = gen(rng, names)
        key = json.dumps(cfg, sort_keys=True)
        if key in pool:
            continue
        d = eng.daily_ls(weights(eng, sig, cfg))
        obj = [round(float(B_obj(d, dy, N)), 4) for N in S.FOLDS]
        yy = L.B.yearly(d, dy, S.YEARS)
        y = [round(yy[v], 4) for v in S.YEARS]
        pool[key] = {"c": cfg, "o": obj, "y": y}
        n += 1
        total += 1
        if len(sample) < SAMPLE:
            sample.append(y)
        elif rng.random() < SAMPLE / total:
            sample[rng.randrange(SAMPLE)] = y
        if n % 2000 == 0 or STOP.exists():
            keep = set()
            for f in range(len(S.FOLDS)):
                keep |= set(sorted(pool, key=lambda k: -pool[k]["o"][f])[:KEEP])
            pool = {k: pool[k] for k in keep}
            tmp = LAB / f"w{wid}.top.tmp"
            tmp.write_text(json.dumps({"total": total, "pool": list(pool.values()), "sample": sample}), encoding="utf-8")
            os.replace(tmp, ft)
        if n % 100 == 0:
            (LAB / f"w{wid}.json").write_text(json.dumps({"worker": wid, "done": total, "session": n,
                                                         "per_min": round(n / max(1e-9, (time.time() - t0) / 60), 1),
                                                         "at": now(), "pid": os.getpid(), "last": describe(cfg)}), encoding="utf-8")
    return 0


def B_obj(d, dy, N) -> float:
    return L.B.objective_value(d, dy, tuple(range(S.FIRST, N)))[0]


# ------------------------------------------------------------------ merge: the walk-forward chain

def load_all() -> tuple[list, np.ndarray, np.ndarray, np.ndarray, int]:
    cfgs, O, Y, SM, total = [], [], [], [], 0
    seen = set()
    for f in sorted(LAB.glob("w*.top.json")):
        try:
            z = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        total += z.get("total", 0)
        SM += z.get("sample", [])
        for r in z.get("pool", []):
            k = json.dumps(r["c"], sort_keys=True)
            if k not in seen:
                seen.add(k)
                cfgs.append(r["c"])
                O.append(r["o"])
                Y.append(r["y"])
    return cfgs, np.array(O, dtype=np.float32), np.array(Y, dtype=np.float32), np.array(SM, dtype=np.float32), total


def describe(c: dict) -> str:
    op = {"and": " AND ", "mean": " + ", "maj": " / majority / "}[c["op"]]
    s = op.join(c["sig"])
    sh = f"short {c['short'][0]} {int(c['short'][2] * 100)}%" if c["short"] else "no short"
    conf = f" · {c['hyst']}d confirm" if c["hyst"] else ""
    vol = f", vol {int(c['vt'] * 100)}%" if c["vt"] else ""
    return f"{s}{conf} → long {c['long']}, {sh}{vol}"


def merge() -> int:
    LAB.mkdir(parents=True, exist_ok=True)
    cfgs, O, Y, SM, total = load_all()
    if len(cfgs) < 50:
        return 0
    eng, sig = build()
    dy = eng.dy
    yrs_idx = {y: i for i, y in enumerate(S.YEARS)}
    chain_d = np.zeros(len(dy))
    folds = {}
    expo = {}
    for f, N in enumerate(S.FOLDS):
        top = np.argsort(-O[:, f])[:S.TOPK]
        mem = [weights(eng, sig, cfgs[i]) for i in top]
        W = sum(mem) / len(mem)
        d = eng.daily_ls(W)
        m = dy == N
        chain_d[m] = d[m]
        folds[N] = {"ret": round(L.B.yearly(d, dy, (N,))[N], 4), "dd": round(L.B.max_dd(d[m]), 4),
                    "best": describe(cfgs[top[0]]), "median_all": round(float(np.median(SM[:, yrs_idx[N]])), 4) if len(SM) else None}
        rows = eng.w.P4["year"] == N
        expo[N] = round(float(np.abs(W[rows]).sum(axis=1).mean()), 3)
        if N == S.FOLDS[-1]:
            current = [describe(cfgs[i]) for i in top]

    hist = load_hist()
    hist.append({"at": now(), "n": total, **{str(N): folds[N]["ret"] for N in folds}})
    (LAB / "history.json").write_text(json.dumps(hist[-500:]), encoding="utf-8")
    ws = []
    for f in [x for x in sorted(LAB.glob("w*.json")) if x.stem[1:].isdigit()]:
        try:
            ws.append(json.loads(f.read_text(encoding="utf-8")))
        except ValueError:
            pass
    doc = {"at": now(), "configs": total, "signals": len(sig), "folds": folds, "exposure": expo, "current_book": current,
           "workers": ws, "chain_research": round(float(np.mean([folds[N]["ret"] for N in range(2021, 2026)])), 4),
           "positive_years": int(sum(folds[N]["ret"] > 0 for N in range(2021, 2027)))}
    tmp = LAB / "status.tmp"
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    os.replace(tmp, LAB / "status.json")
    np.save(LAB / "chain_daily.npy", chain_d)
    return 0


def load_hist() -> list:
    try:
        return json.loads((LAB / "history.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def write_doc(eng, chain_d, folds, expo) -> None:
    """The page's year-by-year document: the walk-forward chain from 2021 (2020 was chosen on 2019 alone, with
    four months of perpetuals - shown in the table, kept out of the chart), BTC and the equal-weight basket."""
    w, dy = eng.w, eng.dy
    dates = [str(x.astype("datetime64[ns]"))[:10] for x in H_dates(w)]
    ys = [y for y in range(2020, 2027)]
    ctx = eng.ctx
    btc = eng.daily(eng.weights(np.ones(ctx.nD), "BTC", 0))
    ew = eng.daily(eng.weights(np.ones(ctx.nD), "equal weight", 0))
    keep = np.isin(dy, range(2021, 2027))
    idx = np.flatnonzero(keep)
    eq_s, eq_b = np.cumprod(1 + chain_d[idx]), np.cumprod(1 + btc[idx])
    yr = lambda d, y: {"return": round(float(np.prod(1 + d[dy == y]) - 1), 4), "max_dd": round(L.B.max_dd(d[dy == y]), 4)}  # noqa: E731
    doc = {"id": "system12", "built": now(),
           "years": {y: {"scaled": yr(chain_d, y), "exposure": expo.get(y)} for y in ys},
           "benchmarks": {"btc": {"years": {y: yr(btc, y) for y in ys}}, "equal_weight": {"years": {y: yr(ew, y) for y in ys}}},
           "curve": {"dates": [dates[i] for i in idx], "scaled": [round(float(x), 5) for x in eq_s], "btc": [round(float(x), 5) for x in eq_b]},
           "research": stats(chain_d[np.isin(dy, range(2021, 2026))]), "forward": stats(chain_d[dy == 2026]),
           "btc_research": stats(btc[np.isin(dy, range(2021, 2026))]), "btc_forward": stats(btc[dy == 2026])}
    (LAB / "history_doc.json").write_text(json.dumps(doc), encoding="utf-8")


def H_dates(w):
    return L.H.to_daily(w, np.zeros(len(w.P4["grid"])))[2] - 1


def stats(d: np.ndarray) -> dict:
    return L.H.stats(d)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", type=int, default=None)
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    if a.merge:
        return merge()
    return worker(a.worker or 0)


if __name__ == "__main__":
    raise SystemExit(main())
