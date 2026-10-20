"""Full-history walk-forward of a lab spec, for the Live view: research years 2019-2025 out of sample,
then 2026-01-01 -> today as the forward test (never trained on, never used to select anything).

Procedure = the paper book's (paper_v2.py), rolled forward one year at a time:
  models     for each year N (2019..2026), every (timeframe, horizon) refitted on rows < N (label-end
             embargo); 2026 sees only <= 2025
  selection  for each year N >= 2020: of the 36 inner configurations, the 10 with the best p5 bootstrap
             Sharpe over the out-of-sample years 2019..N-1, bagged
  scale      exposure x min(1, 0.18 / the bag's max DD over 2019..N-1)  (ex ante; the 18% DD budget)
  book       decide at a bar's close, fill at the next (4h grid), 0.225%/side spot or 0.10% perp,
             + ADV impact; phase 4 risk layer; BTC > MA100 gate
  universe   2020-2026: the frozen PIT lists (top `cap` by 30-day turnover on 31 Dec of N-1, delisted
             included). 2018-2019 (training / first selection year only): the same ranking with a USD 1M
             floor and 90 days of history, because no coin met the USD 10M / 540-day rule then.
Both seed sets s1 and s2 are run; the page shows the worse by 2020-2025 Sharpe (2026 never decides).
Writes lab/history/<spec>.json and lab/history/progress.json (live progress for the page). Display
only: nothing here feeds the lab's selection or the paper book.

    python research/plan_v2/history_v2.py                 # the paper candidate + the lab's top specs
    python research/plan_v2/history_v2.py --spec cap14-spot_long-xs-base-mlp
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

import lab_v2 as LV
import phase3_select as P3
import phase3b_longshort as P3B
import phase4_risk as P4R

HERE = Path(__file__).resolve().parent
OUT = HERE / "lab" / "history"
CACHE = OUT / "cache"
PROG = OUT / "progress.json"
MODEL_YEARS = tuple(range(2019, 2027))
BOOK_YEARS = tuple(range(2020, 2027))
RESEARCH_YEARS = tuple(range(2020, 2026))
FORWARD_YEAR = 2026
Y0 = 2018                                    # first list year; impact rows are indexed from it
BAG = 10
DD_BUDGET = 0.18
EARLY_FLOOR, EARLY_DAYS = 1e6, 90


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Progress:
    """Throttled progress file the dashboard reads every second."""

    def __init__(self, spec_id: str, total: int):
        self.d = {"spec": spec_id, "started": now(), "pid": os.getpid(), "done": 0, "total": total,
                  "stage": "starting", "curve": [], "years": {}}
        self.t = 0.0
        OUT.mkdir(parents=True, exist_ok=True)

    def step(self, stage: str, n: int = 1, force: bool = False, **kw):
        self.d["done"] += n
        self.d["stage"] = stage
        self.d.update(kw)
        if force or time.time() - self.t > 1.0:
            self.t = time.time()
            self.d["at"] = now()
            tmp = PROG.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.d, default=str), encoding="utf-8")
            os.replace(tmp, PROG)


# ------------------------------------------------------------------ data

def lists_for(cap: int) -> dict[int, list[str]]:
    from system010_conditioned_rl import pit
    from system010_conditioned_rl import universe_pit as U
    lists = {int(y): list(v) for y, v in pit.union_lists(cap, pit.UNION_YEARS).items()}
    lists[2026] = list(U.load(2026, cap))
    f = CACHE / "early_lists.json"
    if f.exists():
        early = {int(k): v for k, v in json.loads(f.read_text()).items()}
    else:
        stats = {}
        for s in U.on_disk():
            ns, c, v = U.read_candles(s)
            stats[s] = {y: U.stats_at(ns, c, v, y) for y in (2018, 2019)}
        early = {y: U.eligible(stats, y, floor=EARLY_FLOOR, min_days=EARLY_DAYS) for y in (2018, 2019)}
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(early))
    for y in (2018, 2019):
        lists[y] = early[y][:cap]
    return lists


def coin_bars(s: str) -> dict:
    """{tf: frame} for one coin, research + sealed bars, cached for 6 hours."""
    from quantlab_catalog.candles import candles
    f = CACHE / f"bars_{s}.pkl"
    if f.exists() and time.time() - f.stat().st_mtime < 6 * 3600:
        return pd.read_pickle(f)
    b = candles([s], include_sealed=True).get(s) or []
    df = pd.DataFrame({"ns": [np.datetime64(x.timestamp.replace(tzinfo=None), "ns").astype("int64") for x in b],
                       "open": [x.open for x in b], "high": [x.high for x in b], "low": [x.low for x in b],
                       "close": [x.close for x in b], "usd": [x.volume * x.close for x in b],
                       "tk": [(x.taker_buy_volume or 0.0) * x.close for x in b]})
    fr = {}
    for tf, step in (("4h", P3.H4), ("1d", P3.D1)):
        g = df.groupby(df["ns"] // step * step + step)
        r = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                          "close": g["close"].last(), "usd": g["usd"].sum(), "tk": g["tk"].sum(), "n": g["close"].count()})
        r = r[r["n"] == step // (15 * 60 * 10**9)]
        r["taker"] = r["tk"] / r["usd"].replace(0, np.nan)
        fr[tf] = r.drop(columns=["tk", "n"])
    CACHE.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(fr, f)
    return fr


def impact(P: dict, tf: str) -> np.ndarray:
    """P3.impact with rows for 2018..2026 (row i = year Y0 + i)."""
    n = P3.BARS_PER_DAY[tf]
    years = range(Y0, 2027)
    out = np.zeros((len(years), len(P["coins"])))
    c, usd, yr = P["close"], P["usd"], P["year"]
    for i, y in enumerate(years):
        for j in range(len(P["coins"])):
            sel = (yr == y - 1) & np.isfinite(c[:, j])
            if sel.sum() < 30 * n:
                sel = (yr == y) & np.isfinite(c[:, j])
            if sel.sum() < 10 * n:
                out[i, j] = 0.003
                continue
            cd, ud = c[sel, j][n - 1::n], usd[sel, j][: (sel.sum() // n) * n].reshape(-1, n).sum(axis=1)
            sig = np.std(np.diff(np.log(cd))) if len(cd) > 2 else 0.05
            out[i, j] = float(sig * np.sqrt(P3.BOOK / 3 / max(np.median(ud), 1.0)))
    return out


def world(cap: int, cut_ns: int) -> SimpleNamespace:
    lists = lists_for(cap)
    coins = sorted({s for v in lists.values() for s in v})
    bars = {"4h": {}, "1d": {}}
    for s in coins:
        fr = coin_bars(s)
        for tf in bars:
            bars[tf][s] = fr[tf][fr[tf].index < cut_ns]
    P = {}
    for tf in ("4h", "1d"):
        grid = np.unique(np.concatenate([bars[tf][s].index.values for s in coins]))
        grid = grid[P3.year_of(grid) >= Y0]
        cols = {c: np.column_stack([bars[tf][s][c].reindex(grid).values for s in coins]).astype(float)
                for c in ("open", "high", "low", "close", "usd", "taker")}
        yr = P3.year_of(grid)
        member = np.zeros((len(grid), len(coins)), dtype=bool)
        for y, v in lists.items():
            for j, s in enumerate(coins):
                if s in v:
                    member[yr == y, j] = True
        member &= np.isfinite(cols["close"])
        P[tf] = {"grid": grid, "coins": coins, "year": yr, "member": member, **cols}
    w = SimpleNamespace(cap=cap, lists=lists, P=P, P4=P["4h"])
    w.imp = {tf: impact(P[tf], tf) for tf in P}
    w.X = {tf: P3.features(P[tf], tf)[0] for tf in P}
    w.gate = {}
    for tf in P:
        n = P3.BARS_PER_DAY[tf]
        btc = pd.Series(P[tf]["close"][:, P[tf]["coins"].index("BTCUSDT")])
        w.gate[tf] = (btc > btc.rolling(100 * n, min_periods=100 * n).mean()).values
    w.sig, w.cov = P4R.daily_risk(P["1d"])
    w.day_of_bar = np.searchsorted(P["1d"]["grid"], w.P4["grid"], side="right") - 1
    fund4, _ = P3B.funding_panel(w.P4)
    can4 = np.zeros_like(fund4, dtype=bool)          # a perpetual existed (cache end ignored: live coins)
    for j, s in enumerate(coins):
        f = P3.CACHE / f"funding_{s}.json"
        rows = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        if rows:
            can4[:, j] = w.P4["grid"] >= rows[0]["t_ms"] * 10**6
    w.fund4 = fund4
    idx1 = np.clip(np.searchsorted(w.P4["grid"], P["1d"]["grid"]), 0, len(w.P4["grid"]) - 1)
    w.perp = {"4h": can4, "1d": can4[idx1]}
    return w


# ------------------------------------------------------------------ models and books

def xs_target(P: dict, tf: str, h: int):
    n = P3.BARS_PER_DAY[tf]
    c = P["close"]
    H = h * n
    g = np.full_like(c, np.nan)
    g[: len(c) - 1 - H] = c[1 + H:] / c[1: len(c) - H] - 1
    g = np.where(P["member"], g, np.nan)
    with np.errstate(invalid="ignore"):
        y = np.clip(g - np.nanmean(g, axis=1, keepdims=True), -0.5, 0.5)
    end = np.minimum(np.arange(len(c)) + 1 + H, len(c) - 1)
    return y, end


def preds(w, tf, h, model, seeds, spec, cache, prog):
    key = (tf, h, model, tuple(seeds))
    if key in cache:
        return cache[key]
    P = w.P[tf]
    if model == "ens":
        parts = []
        for m in ("ridge", "gbm", "mlp"):
            a = preds(w, tf, h, m, seeds, spec, cache, prog)
            parts.append(pd.DataFrame(np.where(P["member"], a, np.nan)).rank(axis=1, pct=True).values - 0.5)
        with np.errstate(invalid="ignore"):
            cache[key] = np.nanmean(np.stack(parts), axis=0)
        return cache[key]
    if spec["target"] == "xs":
        y, end = xs_target(P, tf, h)
    else:
        y, end = P3.target(P, tf, h, w.imp[tf][np.clip(np.arange(7) + 2020 - Y0, 0, None)])
    pr = np.full_like(P["close"], np.nan)
    for N in MODEL_YEARS:
        prog.step(f"training {model} {tf} {h}d for {N} (data < {N})")
        if model in ("mlp", "mlp_big"):
            fp = LV.fit_predict_mlp(w.X[tf], y, end, P, seeds, N, big=(model == "mlp_big"))
        else:
            fp = P3.fit_predict(w.X[tf], y, end, P, model, seeds, N)
        pr[P["year"] == N] = fp
    cache[key] = pr
    return pr


def book(w, spec, cfg, pr):
    tf = cfg["tf"]
    P = w.P[tf]
    hold = cfg["h_days"] * P3.BARS_PER_DAY[tf]
    member = P["member"] & (w.perp[tf] if spec["venue"] == "perp_long" else True)
    p = pr if spec["target"] == "net" else np.where(np.isfinite(pr), pr + 1.0, np.nan)
    W = P3.decide(p, member, cfg["k"], w.gate[tf], hold=hold)
    Wx = P3.to_exec_4h(W, P["grid"], w.P4["grid"])
    return P4R.risk_weights(Wx, w.P4, w.day_of_bar, w.sig, w.cov)


def bar_returns(w, W, half, fund):
    """Net 4h returns of executed weights."""
    c = w.P4["close"]
    R = np.zeros_like(c)
    R[:-1] = np.nan_to_num(c[1:] / c[:-1] - 1)
    W = np.where(np.isfinite(c), W, 0.0)
    dW = np.abs(np.diff(np.r_[np.zeros((1, W.shape[1])), W], axis=0))
    yi = np.clip(w.P4["year"] - Y0, 0, 2026 - Y0)
    cost = (dW * (half + w.imp["4h"][yi])).sum(axis=1)
    fpl = -(W * fund).sum(axis=1) if fund is not None else 0.0
    r = (W * R).sum(axis=1) - cost + fpl
    r[-1] = 0.0                                    # the last bar's return is not known yet
    return r, W


def to_daily(w, r):
    day = w.P4["grid"] // P3.D1
    last = np.r_[day[1:] != day[:-1], True]
    e = np.cumprod(1 + r)[last]
    return np.r_[e[0] - 1, e[1:] / e[:-1] - 1], P3.year_of(w.P4["grid"][last]), w.P4["grid"][last]


def stats(d: np.ndarray) -> dict:
    if not len(d):
        return {}
    eq = np.cumprod(1 + d)
    sh = float(d.mean() / (d.std(ddof=1) + 1e-12) * np.sqrt(365)) if len(d) > 2 else 0.0
    return {"return": round(float(eq[-1] - 1), 4), "max_dd": round(float((1 - eq / np.maximum.accumulate(eq)).max()), 4),
            "sharpe": round(sh, 3), "ann": round(float(np.exp(np.log1p(d).sum() * 365 / len(d)) - 1), 4), "days": int(len(d))}


# ------------------------------------------------------------------ one spec

def run_spec(spec: dict, cut_ns: int) -> dict:
    sid = LV.spec_id(spec)
    models = LV.FAMILY_MODELS[spec["family"]]
    cfgs = [dict(tf=a, h_days=b, k=c, model=d) for a, b, c, d in product(LV.INNER["tf"], LV.INNER["h_days"], LV.INNER["k"], models)]
    n_fits = 6 * len(MODEL_YEARS) * (3 if spec["family"] == "ens" else len(models))
    seed_sets = {s: P3.SEED_SETS[s] for s in ("s1", "s2")}
    prog = Progress(sid, total=len(seed_sets) * (n_fits + len(cfgs) + len(BOOK_YEARS)) + 1)
    prog.step("loading prices 2018 -> today (research + sealed 2026)", force=True)
    w = world(spec["cap"], cut_ns)
    half = P3.HALF_COST if spec["venue"] == "spot_long" else LV.PERP_HALF
    fund = w.fund4 if spec["venue"] != "spot_long" else None
    res = {}
    for ss, seeds in seed_sets.items():
        cache = {}
        runs = []
        for cfg in cfgs:
            pr = preds(w, cfg["tf"], cfg["h_days"], cfg["model"], seeds, spec, cache, prog)
            Wx = book(w, spec, cfg, pr)
            r, Wx = bar_returns(w, Wx, half, fund)
            d, dy, _ = to_daily(w, r)
            runs.append({"cfg": cfg, "Wx": Wx, "d": d})
            prog.step(f"{ss}: simulating configuration {len(runs)}/{len(cfgs)}")
        dy = to_daily(w, np.zeros(len(w.P4["grid"])))[1]
        dates = to_daily(w, np.zeros(len(w.P4["grid"])))[2]
        r_full = np.zeros(len(w.P4["grid"]))
        r_sc = np.zeros(len(w.P4["grid"]))
        years = {}
        for N in BOOK_YEARS:
            past = np.isin(dy, [y for y in MODEL_YEARS if y < N])
            scored = sorted(((P3.boot_sharpe_p5(x["d"][past]), i) for i, x in enumerate(runs)), reverse=True)[:BAG]
            Wb = np.mean([runs[i]["Wx"] for _, i in scored], axis=0)
            rb, _ = bar_returns(w, Wb, half, fund)
            db, _, _ = to_daily(w, rb)
            eq = np.cumprod(1 + db[past])
            dd_past = float((1 - eq / np.maximum.accumulate(eq)).max()) if past.any() else 1.0
            scale = min(1.0, DD_BUDGET / dd_past) if dd_past > 0 else 1.0
            rs, _ = bar_returns(w, Wb * scale, half, fund)
            inN = w.P4["year"] == N
            r_full[inN], r_sc[inN] = rb[inN], rs[inN]
            ds = to_daily(w, r_sc)[0][dy == N]
            df_ = to_daily(w, r_full)[0][dy == N]
            years[N] = {"scaled": stats(ds), "full": stats(df_), "scale": round(scale, 3),
                        "exposure": round(float(np.abs(Wb[inN] * scale).sum(axis=1).mean()), 3),
                        "configs": [runs[i]["cfg"] for _, i in scored]}
            eqc = np.cumprod(1 + to_daily(w, r_sc)[0][np.isin(dy, BOOK_YEARS) & (dy <= N)])
            prog.step(f"{ss}: year {N} {'(forward test)' if N == FORWARD_YEAR else ''} "
                      f"{years[N]['scaled'].get('return', 0):+.1%}", force=True,
                      years={**prog.d.get("years", {}), f"{ss}:{N}": years[N]["scaled"].get("return")},
                      curve=[round(float(x), 4) for x in eqc[::7]])
        dsc, dfu = to_daily(w, r_sc)[0], to_daily(w, r_full)[0]
        keep = np.isin(dy, BOOK_YEARS)
        res[ss] = {"years": years, "dates": [str(x.astype("datetime64[ns]"))[:10] for x in dates[keep]],
                   "d_scaled": dsc[keep], "d_full": dfu[keep],
                   "research": stats(dsc[np.isin(dy, RESEARCH_YEARS)]), "research_full": stats(dfu[np.isin(dy, RESEARCH_YEARS)]),
                   "forward": stats(dsc[dy == FORWARD_YEAR]), "forward_full": stats(dfu[dy == FORWARD_YEAR])}
    worse = min(res, key=lambda s: res[s]["research"]["sharpe"])
    main = res[worse]
    other = res["s2" if worse == "s1" else "s1"]
    dates = main["dates"]
    # benchmarks over the same days: BTC buy and hold; the PIT list equal-weighted, rebalanced daily
    P1 = w.P["1d"]
    c1 = P1["close"]
    r1 = np.zeros_like(c1)
    r1[1:] = c1[1:] / c1[:-1] - 1
    d1 = [str(x.astype("datetime64[ns]"))[:10] for x in (P1["grid"] - 1)]
    bi = {d: i for i, d in enumerate(d1)}
    jb = P1["coins"].index("BTCUSDT")
    btc = np.array([np.nan_to_num(r1[bi[d], jb]) if d in bi else 0.0 for d in dates])
    mem_prev = np.r_[np.zeros((1, c1.shape[1]), dtype=bool), P1["member"][:-1]]
    ew_all = np.nanmean(np.where(mem_prev & np.isfinite(r1), r1, np.nan), axis=1)
    ew = np.array([np.nan_to_num(ew_all[bi[d]]) if d in bi else 0.0 for d in dates])

    def curve(d):
        return np.cumprod(1 + np.asarray(d))
    eq_s, eq_f, eq_o, eq_b, eq_e = curve(main["d_scaled"]), curve(main["d_full"]), curve(other["d_scaled"]), curve(btc), curve(ew)
    step = 3
    pick = sorted(set(range(0, len(dates), step)) | {len(dates) - 1})
    dy_arr = np.array([int(x[:4]) for x in dates])
    bench = {}
    for nm, d in (("btc", btc), ("equal_weight", ew)):
        bench[nm] = {"years": {int(y): stats(d[dy_arr == y]) for y in BOOK_YEARS},
                     "research": stats(d[np.isin(dy_arr, RESEARCH_YEARS)]), "forward": stats(d[dy_arr == FORWARD_YEAR])}
    # BTC's yearly return exactly close 31 Dec -> close 31 Dec (the daily chain above can shift a day at year ends)
    dl = (P1["grid"] - 1).astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970
    for y in BOOK_YEARS:
        e, b0 = c1[dl == y, jb], c1[dl == y - 1, jb]
        if len(e) and len(b0) and y in bench["btc"]["years"]:
            bench["btc"]["years"][y]["return"] = round(float(e[np.isfinite(e)][-1] / b0[np.isfinite(b0)][-1] - 1), 4)
    doc = {"spec": spec, "id": sid, "built": now(), "cut": str(np.datetime64(int(cut_ns), "ns"))[:16],
           "seed_set_shown": worse, "list_sizes": {int(y): len(v) for y, v in sorted(w.lists.items())},
           "years": {int(y): v for y, v in main["years"].items()},
           "other_seed_years": {int(y): {"scaled": v["scaled"]} for y, v in other["years"].items()},
           "research": main["research"], "research_full": main["research_full"],
           "forward": main["forward"], "forward_full": main["forward_full"],
           "other_seed": {"research": other["research"], "forward": other["forward"]},
           "benchmarks": bench,
           "curve": {"dates": [dates[i] for i in pick], "scaled": [round(float(eq_s[i]), 4) for i in pick],
                     "full": [round(float(eq_f[i]), 4) for i in pick], "other_seed": [round(float(eq_o[i]), 4) for i in pick],
                     "btc": [round(float(eq_b[i]), 4) for i in pick], "equal_weight": [round(float(eq_e[i]), 4) for i in pick]},
           "notes": {"forward_from": "2026-01-01", "early_lists": f"2018-2019 lists: USD {EARLY_FLOOR / 1e6:.0f}M floor, "
                     f"{EARLY_DAYS} days of history (training and first selection year only)"}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{sid}.json").write_text(json.dumps(doc, default=str), encoding="utf-8")
    prog.d["done"] = prog.d["total"]
    prog.step("done", n=0, force=True, finished=now())
    print(f"[{now()}] {sid}: research {doc['research']} forward {doc['forward']}", flush=True)
    return doc


def targets() -> list[dict]:
    """The paper candidate first, then the lab's best pooled specs this script can rebuild."""
    out = [json.loads((HERE / "paper_v2" / "selection.json").read_text())["spec"]]
    pool = LV.pooled(LV.ledger())
    for r in pool:
        s = r["spec"]
        if (s["venue"] in ("spot_long", "perp_long") and s["feats"] == "base" and r["reps"] >= 2
                and LV.spec_id(s) not in {LV.spec_id(x) for x in out}):
            out.append(s)
        if len(out) >= 3:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=None)
    a = ap.parse_args()
    cut = np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None), "ns").astype("int64")
    specs = targets()
    if a.spec:
        specs = [s for s in LV.SPECS if LV.spec_id(s) == a.spec]
    index = []
    for s in specs:
        t0 = time.time()
        doc = run_spec(s, cut)
        index.append({"id": doc["id"], "built": doc["built"], "research": doc["research"], "forward": doc["forward"],
                      "minutes": round((time.time() - t0) / 60, 1)})
        (OUT / "index.json").write_text(json.dumps({"at": now(), "specs": index}, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
