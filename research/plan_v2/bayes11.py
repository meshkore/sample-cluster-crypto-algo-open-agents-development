"""Bayes 11 - a Bayesian search (Optuna TPE) over every way of turning System 11's model votes into a book
(operator 2026-10-21: "a Bayesian algorithm that plays with all the coins and all the combinations and finds what
works best in all these years, especially the last ones").

Input: the System 11 law book (rocket11/cache/base.npz): per year, the 10 configurations chosen by the law and
each one's own weights - i.e. which coins the models pick, 4h by 4h, out of sample, both seed sets.

Search space (one trial = one complete book)
    m          how many of the year's configurations vote (1-10)
    vmin       minimum votes a coin needs to be held
    topn       hold at most the n most-voted coins (1-14)
    weight     bag weights | votes^p | equal
    exposure   the bag's own exposure x lev (capped at 100%), or a fixed % of the book whenever anything is picked
    cap        maximum weight of one coin
    btc_ma     hold nothing while BTC is below its n-day average (0 = off)
    coin_ema   do not hold a coin below its own n-day EMA (0 = off)
    band       rebalance a coin only when its target moves more than this (cuts trading costs)

Objective on the training years: the law (recency-weighted mean yearly return, weights doubling toward today)
+ 3 points per positive year - 3 x the drawdown above 25%; the worse of the two seed sets.

Honesty: the search is WALK-FORWARD. For each year N (2021-2026) the search sees only years 2020..N-1, and the
best book found is then run on year N, which it never saw. The chained year-N results are what this method
would really have earned. 2026 is the final fold: chosen on 2020-2025, read on 2026, never used to choose.
Costs: 0.225%/side + impact, fills at the next 4h bar (history_v2.bar_returns).

    python research/plan_v2/bayes11.py --trials 3000      -> bayes11/{status.json, REPORT.md, trials_<N>.jsonl}
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import optuna
import pandas as pd

import history_v2 as H
import phase3_select as P3
import rocket11 as R

HERE = Path(__file__).resolve().parent
OUT = HERE / "bayes11"
STATUS = OUT / "status.json"
REPORT = OUT / "REPORT.md"
STOP = OUT / "STOP"
FOLDS = tuple(range(2021, 2027))
FIRST = 2020
MAX_DD = 0.25
MAS = (0, 50, 100, 150, 200)
EMAS = (0, 20, 50, 100, 200)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Book:
    """Everything a trial needs, precomputed once."""

    def __init__(self, w, base):
        self.w = w
        D = R.Data(w)
        self.seeds = {}
        for ss, b in base.items():
            st = b["stack"].astype(np.float32)
            on = st > 1e-9
            self.seeds[ss] = {"V": np.cumsum(on, axis=0, dtype=np.int16),            # V[m-1] = votes of the first m configs
                              "B": np.cumsum(st, axis=0) / np.arange(1, st.shape[0] + 1)[:, None, None]}
        btc = D.btc
        self.btc_ok = {n: D.to4h(D.bc((btc > btc.rolling(n, min_periods=n // 2).mean()).values | btc.rolling(n).mean().isna().values))[:, 0]
                       for n in MAS if n}
        self.coin_ok = {n: D.to4h(((D.c1 >= D.c1.ewm(span=n, adjust=False, min_periods=n // 2).mean()) | D.c1.isna()).values)
                        for n in EMAS if n}
        self.year = w.P4["year"]
        self.dy = H.to_daily(w, np.zeros(len(w.P4["grid"])))[1]

    def weights(self, ss: str, p: dict) -> np.ndarray:
        S = self.seeds[ss]
        m = p["m"]
        V, B = S["V"][m - 1].astype(np.float32), S["B"][m - 1]
        sel = (V >= min(p["vmin"], m)) & (B > 1e-9)
        if p["topn"] < V.shape[1]:
            key = np.where(sel, V + B / (B.max() + 1e-12), -1.0)
            kth = -np.sort(-key, axis=1)[:, p["topn"] - 1: p["topn"]]
            sel &= key >= kth
        if p["coin_ema"]:
            sel &= self.coin_ok[p["coin_ema"]]
        raw = {"bag": B, "votes": V ** p.get("p", 1.0), "equal": np.ones_like(B)}[p["weight"]] * sel
        tot = raw.sum(axis=1, keepdims=True)
        share = np.divide(raw, tot, out=np.zeros_like(raw), where=tot > 0)
        gross = np.minimum(1.0, B.sum(axis=1, keepdims=True) * p["lev"]) if p["exposure"] == "bag" else np.full_like(tot, p["gross"])
        Wt = np.minimum(share * gross, p["cap"])
        if p["btc_ma"]:
            Wt *= self.btc_ok[p["btc_ma"]][:, None]
        if p["band"] > 0:
            Wt = band(Wt, p["band"])
        return Wt

    def daily(self, ss: str, p: dict) -> np.ndarray:
        r, _ = H.bar_returns(self.w, self.weights(ss, p), P3.HALF_COST, None)
        return H.to_daily(self.w, r)[0]


def band(Wt: np.ndarray, b: float) -> np.ndarray:
    """Keep the held weight until the target moves more than b; a coin that leaves the picks is sold at once."""
    out = np.empty_like(Wt)
    cur = np.zeros(Wt.shape[1], dtype=Wt.dtype)
    for i in range(Wt.shape[0]):
        t = Wt[i]
        cur = np.where((t == 0) | (np.abs(t - cur) > b), t, cur)
        out[i] = cur
    return out


def yearly(d: np.ndarray, dy: np.ndarray, years) -> dict:
    return {int(y): float(np.prod(1 + d[dy == y]) - 1) for y in years}


def max_dd(d: np.ndarray) -> float:
    if not len(d):
        return 0.0
    eq = np.cumprod(1 + d)
    return float((1 - eq / np.maximum.accumulate(eq)).max())


def objective_value(d: np.ndarray, dy: np.ndarray, years) -> tuple[float, dict, float]:
    yr = yearly(d, dy, years)
    r = [yr[y] for y in years]
    law = R.law_mean(r)
    dd = max_dd(d[np.isin(dy, years)])
    return law + 0.03 * sum(x > 0 for x in r) - 3 * max(0.0, dd - MAX_DD), yr, dd


def suggest(t: optuna.Trial) -> dict:
    p = {"m": t.suggest_int("m", 1, 10), "vmin": t.suggest_int("vmin", 1, 10), "topn": t.suggest_int("topn", 1, 14),
         "weight": t.suggest_categorical("weight", ["bag", "votes", "equal"])}
    if p["weight"] == "votes":
        p["p"] = t.suggest_float("p", 0.5, 3.0)
    p["exposure"] = t.suggest_categorical("exposure", ["bag", "fixed"])
    if p["exposure"] == "bag":
        p["lev"] = t.suggest_float("lev", 0.5, 5.0, log=True)
    else:
        p["gross"] = t.suggest_float("gross", 0.1, 1.0)
    p["cap"] = t.suggest_float("cap", 0.05, 1.0)
    p["btc_ma"] = t.suggest_categorical("btc_ma", list(MAS))
    p["coin_ema"] = t.suggest_categorical("coin_ema", list(EMAS))
    p["band"] = t.suggest_categorical("band", [0.0, 0.005, 0.01, 0.02, 0.04])
    return p


def suggest_robust(t: optuna.Trial) -> dict:
    """Robust mode (operator go 2026-10-21): only the four levers that kept coming back - how many coins, how much
    is invested, the BTC trend gate, the rebalance band. The rest is fixed at the plain System 11 book."""
    return {"m": 10, "vmin": 1, "weight": "votes", "p": 1.0, "exposure": "bag", "cap": 1.0, "coin_ema": 0,
            "topn": t.suggest_int("topn", 1, 14), "lev": t.suggest_float("lev", 0.5, 5.0, log=True),
            "btc_ma": t.suggest_categorical("btc_ma", [0, 50, 100, 200]), "band": t.suggest_categorical("band", [0.0, 0.01, 0.02, 0.04])}


TOP_K = 50


BASE_P = {"m": 10, "vmin": 1, "topn": 14, "weight": "bag", "exposure": "bag", "lev": 1.0, "cap": 1.0, "btc_ma": 0, "coin_ema": 0, "band": 0.0}


def describe(p: dict) -> str:
    e = f"bag exposure x{p['lev']:.2f}" if p["exposure"] == "bag" else f"fixed {p['gross']:.0%} invested"
    wt = f"votes^{p['p']:.1f}" if p["weight"] == "votes" else p["weight"]
    return (f"{p['m']} configs vote, >= {min(p['vmin'], p['m'])} votes, top {p['topn']} coins, {wt} weights, {e}, cap {p['cap']:.0%}/coin"
            + (f", BTC > MA{p['btc_ma']}" if p["btc_ma"] else "") + (f", coin > EMA{p['coin_ema']}" if p["coin_ema"] else "")
            + (f", band {p['band']:.1%}" if p["band"] else ""))


def write_status(doc: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    for _ in range(20):
        try:
            os.replace(tmp, STATUS)
            return
        except PermissionError:
            time.sleep(0.2)


def run(trials: int, robust: bool = False) -> int:
    global OUT, STATUS, REPORT, STOP
    if robust:
        OUT = HERE / "bayes11_robust"
        STATUS, REPORT, STOP = OUT / "status.json", OUT / "REPORT.md", OUT / "STOP"
    pick = suggest_robust if robust else suggest
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "run.pid").write_text(str(os.getpid()))
    cut = np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None), "ns").astype("int64")
    w = H.world(R.SPEC["cap"], int(cut))
    z = np.load(R.CACHE / "base.npz")
    base = {ss: {"W": z[f"{ss}_W"], "stack": z[f"{ss}_stack"]} for ss in ("s1", "s2")}
    T, S = w.P4["close"].shape
    for b_ in base.values():                         # bars newer than the cache: flat (no position), never invented
        assert b_["W"].shape[1] == S and b_["W"].shape[0] <= T, "rocket11 base cache does not match - rebuild it"
        if b_["W"].shape[0] < T:
            n = T - b_["W"].shape[0]
            b_["W"] = np.r_[b_["W"], np.zeros((n, S), b_["W"].dtype)]
            b_["stack"] = np.concatenate([b_["stack"], np.zeros((b_["stack"].shape[0], n, S), b_["stack"].dtype)], axis=1)
    bk = Book(w, base)
    dy = bk.dy
    ref = {ss: bk.daily(ss, BASE_P) for ss in bk.seeds}
    ref_years = {ss: yearly(ref[ss], dy, H.BOOK_YEARS) for ss in ref}
    doc = {"started": now(), "trials_per_fold": trials, "spec": "cap14-spot_long-xs-base-mlp-law", "folds": {},
           "base": {"years": min(ref_years.values(), key=lambda y: sum(y[k] for k in range(2020, 2026))),
                    "dd": max(max_dd(ref[ss][np.isin(dy, H.RESEARCH_YEARS)]) for ss in ref)},
           "state": "running"}
    write_status(doc)
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    for N in FOLDS:
        if STOP.exists():
            break
        train = tuple(range(FIRST, N))
        cur = doc["folds"].setdefault(str(N), {"train": f"{FIRST}-{N - 1}", "done": 0, "of": trials})
        log = (OUT / f"trials_{N}.jsonl").open("w", encoding="utf-8")
        t0 = time.time()

        def obj(t: optuna.Trial) -> float:
            p = pick(t)
            vals = {}
            for ss in bk.seeds:
                v, yr, dd = objective_value(bk.daily(ss, p), dy, train)
                vals[ss] = (v, yr, dd)
            worst = min(vals, key=lambda s: vals[s][0])
            v, yr, dd = vals[worst]
            log.write(json.dumps({"n": t.number, "v": round(v, 4), "p": p, "years": {k: round(x, 4) for k, x in yr.items()}, "dd": round(dd, 4)}) + "\n")
            cur["done"] = t.number + 1
            if cur.get("best") is None or v > cur["best"]["v"]:
                cur["best"] = {"v": round(v, 4), "p": p, "text": describe(p), "train_years": {k: round(x, 4) for k, x in yr.items()}, "dd": round(dd, 4)}
            if (t.number + 1) % 25 == 0:
                cur["per_min"] = round((t.number + 1) / max(1e-9, (time.time() - t0) / 60), 1)
                doc["updated"] = now()
                write_status(doc)
            if STOP.exists():
                t.study.stop()
            return v

        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=N, multivariate=True, n_startup_trials=200))
        study.enqueue_trial({k: v for k, v in BASE_P.items() if not robust or k in ("topn", "lev", "btc_ma", "band")})
        study.optimize(obj, n_trials=trials, gc_after_trial=False)
        log.close()
        p = cur["best"]["p"]
        top = sorted((t for t in study.trials if t.value is not None), key=lambda t: -t.value)[:TOP_K]
        if robust:                                   # the book = the average of the 50 best books, not the single best
            cur["consensus"] = {"k": len(top), "topn_median": float(np.median([t.params["topn"] for t in top])),
                                "lev_median": round(float(np.median([t.params["lev"] for t in top])), 2),
                                "btc_ma_share": {str(m): round(sum(t.params["btc_ma"] == m for t in top) / len(top), 2) for m in (0, 50, 100, 200)},
                                "band_median": float(np.median([t.params["band"] for t in top]))}
            c = cur["consensus"]
            cur["best"]["text"] = (f"average of the {c['k']} best books: ~{c['topn_median']:.0f} coins, bag exposure x{c['lev_median']}, "
                                   f"BTC gate {', '.join(f'MA{k}' if k != '0' else 'off' for k, v in c['btc_ma_share'].items() if v >= 0.2)}, band {c['band_median']:.0%}")
        oos = {}
        for ss in bk.seeds:
            if robust:
                Wc = sum(bk.weights(ss, {**suggest_robust_fixed(), **t.params}) for t in top) / len(top)
                r_, _ = H.bar_returns(bk.w, Wc, P3.HALF_COST, None)
                d = H.to_daily(bk.w, r_)[0]
            else:
                d = bk.daily(ss, p)
            oos[ss] = {"ret": round(yearly(d, dy, (N,))[N], 4), "dd": round(max_dd(d[dy == N]), 4)}
        cur["oos"] = min(oos.values(), key=lambda x: x["ret"])
        cur["oos_seeds"] = oos
        cur["base_oos"] = round(min(ref_years[ss][N] for ss in ref_years), 4)
        cur["minutes"] = round((time.time() - t0) / 60, 1)
        doc["updated"] = now()
        write_status(doc)
        report(doc)
    doc["state"] = "stopped" if STOP.exists() else "done"
    doc["finished"] = now()
    write_status(doc)
    report(doc)
    return 0


def report(doc: dict) -> None:
    L = ["# Bayes 11 - walk-forward Bayesian search over the System 11 book", "",
         f"Updated {doc.get('updated', '')}. Each year is read with the book the search chose on the years BEFORE it. "
         "Worse of two seed sets. Costs charged.", "",
         "| year | searched on | trials | best book found (on the past) | that book in this year | System 11 law book, unscaled |",
         "|---|---|---|---|---|---|"]
    for N, f in doc["folds"].items():
        if "oos" not in f:
            continue
        L.append(f"| {N}{' (forward)' if N == '2026' else ''} | {f['train']} | {f['done']} | {f['best']['text']} | "
                 f"{f['oos']['ret']:+.1%} (DD {f['oos']['dd']:.0%}) | {f['base_oos']:+.1%} |")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


def suggest_robust_fixed() -> dict:
    return {"m": 10, "vmin": 1, "weight": "votes", "p": 1.0, "exposure": "bag", "cap": 1.0, "coin_ema": 0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3000)
    ap.add_argument("--robust", action="store_true")
    a = ap.parse_args()
    return run(a.trials, a.robust)


if __name__ == "__main__":
    raise SystemExit(main())
