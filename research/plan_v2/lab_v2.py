"""Plan v2 lab: the endless, honest search for a tradeable version of the cross-sectional signal.

Each EXPERIMENT is one structural hypothesis (a spec), evaluated exactly like phases 3-4:
  spec        cap      14 | 20 | 30            PIT list width (top N by turnover on 31 Dec of N-1)
              venue    spot_long               spot, long only, BTC > MA100 gate, 0.225% + impact per side
                       perp_long               USD-M perpetuals, long only, gate, 0.10% + impact per side, funding paid
                       perp_ls                 perpetuals, long top K / short bottom K, dollar neutral, funding both legs
              target   net                     phase 3: gross forward return minus the coin's round trip
                       xs                      gross forward return minus the members' mean at t (pure ranking; no
                                               cost term, so no cost artefact - ic_check.py)
              feats    base                    the 28 phase 3 columns
                       perp                    + funding (last settlement, 3-day mean, its cross-sectional rank)
  inner       timeframe 4h | 1d x horizon 1 | 3 | 7 d x K x model ridge | gbm = 36 configurations, each fitted
              walk-forward (years < N, label-end embargo) on two seed sets, booked with the phase 4 risk layer
              and honest execution (decide t, fill t+1)
  selection   nested per year 2022-2025 on 2021..N-1: DD <= 18%, score p5 bootstrap Sharpe, bag the top 10
  result      the WORSE seed set's bagged nested curve 2022-2025: Sharpe, its bootstrap P(Sharpe <= 0), max DD
  gate        P(Sharpe <= 0) <= 0.05 / m (m = experiments run so far: Bonferroni over the lab's own search),
              max DD <= 18%, and at most one nested year in cash. A pass is a CANDIDATE for the forward
              shadow book (never capital: plan phase 5 applies)
Queue: the 36 specs of the grid, in order of prior evidence; then forever, the best specs again on fresh
seed sets (replication: a real effect holds on new seeds, a lucky one does not).
Brake: research/plan_v2/lab/STOP. Ledger lab/ledger.jsonl, report lab/REPORT.md, page blob lab/live_status.json.

    python research/plan_v2/lab_v2.py run [--hours 24]
    python research/plan_v2/lab_v2.py report
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

import phase3_select as P3
import phase3b_longshort as P3B
import phase4_risk as P4R

HERE = Path(__file__).resolve().parent
LAB = HERE / "lab"
CACHE = LAB / "cache"
LEDGER = LAB / "ledger.jsonl"
STOP = LAB / "STOP"
STATUS = LAB / "live_status.json"
REPORT = LAB / "REPORT.md"
PERP_HALF = 0.0010
SPECS = [dict(cap=c, venue=v, target=t, feats=f)
         for c, v, t, f in product((30, 20, 14), ("perp_ls", "perp_long", "spot_long"), ("xs", "net"), ("perp", "base"))]
INNER = {"tf": ("4h", "1d"), "h_days": (1, 3, 7), "k": (3, 5, 8), "model": ("ridge", "gbm")}
INNER_LS_K = (2, 3, 5)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def spec_id(spec: dict) -> str:
    return f"cap{spec['cap']}-{spec['venue']}-{spec['target']}-{spec['feats']}"


# ------------------------------------------------------------------ data per universe width

def bars_for(coins: list[str]) -> dict:
    """{tf: {coin: frame}} from a per-coin cache (research bars <= 2025)."""
    from quantlab_catalog.candles import research
    CACHE.mkdir(parents=True, exist_ok=True)
    out = {"4h": {}, "1d": {}}
    for s in coins:
        f = CACHE / f"bars_{s}.pkl"
        if not f.exists():
            bars = research([s]).get(s) or []
            if not bars:
                continue
            df = pd.DataFrame({"ns": [np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64") for b in bars],
                               "open": [b.open for b in bars], "high": [b.high for b in bars], "low": [b.low for b in bars],
                               "close": [b.close for b in bars], "usd": [b.volume * b.close for b in bars],
                               "tk": [(b.taker_buy_volume or 0.0) * b.close for b in bars]})
            fr = {}
            for tf, step in (("4h", P3.H4), ("1d", P3.D1)):
                g = df.groupby(df["ns"] // step * step + step)
                r = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                                  "close": g["close"].last(), "usd": g["usd"].sum(), "tk": g["tk"].sum()})
                r["taker"] = r["tk"] / r["usd"].replace(0, np.nan)
                fr[tf] = r.drop(columns="tk")
            pd.to_pickle(fr, f)
        fr = pd.read_pickle(f)
        for tf in out:
            out[tf][s] = fr[tf]
    return out


def funding_cols(P: dict, tf: str) -> np.ndarray:
    """(T x S x 3): last settled funding before the bar's close, its 3-day (9-settlement) mean, and the
    cross-sectional rank of that mean among the bar's members. NaN where a coin had no perpetual."""
    T, S = P["close"].shape
    out = np.full((T, S, 3), np.nan)
    for j, s in enumerate(P["coins"]):
        f = P3.CACHE / f"funding_{s}.json"
        rows = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        if not rows:
            continue
        t = np.array([r["t_ms"] for r in rows], dtype=np.int64) * 10**6
        v = np.array([r["rate"] for r in rows])
        m3 = pd.Series(v).rolling(9, min_periods=3).mean().values
        i = np.searchsorted(t, P["grid"], side="left") - 1
        ok = (i >= 0) & (P["grid"] <= t[-1] + 8 * 3600 * 10**9)
        out[ok, j, 0] = v[i[ok]]
        out[ok, j, 1] = m3[i[ok]]
    x = np.where(P["member"], out[:, :, 1], np.nan)
    out[:, :, 2] = pd.DataFrame(x).rank(axis=1, pct=True).values
    return out


class World:
    """Panels, features, costs, gates and risk inputs for one universe width."""

    def __init__(self, cap: int):
        from system010_conditioned_rl import pit
        self.cap = cap
        self.lists = {int(y): list(v) for y, v in pit.union_lists(cap, pit.UNION_YEARS).items()}
        coins = sorted({s for v in self.lists.values() for s in v})
        bars = bars_for(coins)
        self.P = {tf: P3.panel(bars, tf, self.lists) for tf in ("4h", "1d")}
        self.P4 = self.P["4h"]
        self.imp = {tf: P3.impact(self.P[tf], tf) for tf in self.P}
        self.X = {tf: P3.features(self.P[tf], tf)[0] for tf in self.P}
        self.Xf = {tf: funding_cols(self.P[tf], tf) for tf in self.P}
        self.gate = {}
        for tf in self.P:
            n = P3.BARS_PER_DAY[tf]
            btc = pd.Series(self.P[tf]["close"][:, self.P[tf]["coins"].index("BTCUSDT")])
            self.gate[tf] = (btc > btc.rolling(100 * n, min_periods=100 * n).mean()).values
        self.sig, self.cov = P4R.daily_risk(self.P["1d"])
        self.day_of_bar = np.searchsorted(self.P["1d"]["grid"], self.P4["grid"], side="right") - 1
        self.fund4, can4 = P3B.funding_panel(self.P4)
        idx1 = np.clip(np.searchsorted(self.P4["grid"], self.P["1d"]["grid"]), 0, len(self.P4["grid"]) - 1)
        self.perp = {"4h": can4, "1d": can4[idx1]}
        self._preds: dict = {}

    def target(self, tf: str, h: int, kind: str):
        P = self.P[tf]
        y, end = P3.target(P, tf, h, self.imp[tf])
        if kind == "xs":
            n = P3.BARS_PER_DAY[tf]
            c = P["close"]
            H = h * n
            g = np.full_like(c, np.nan)
            g[: len(c) - 1 - H] = c[1 + H:] / c[1: len(c) - H] - 1
            g = np.where(P["member"], g, np.nan)
            with np.errstate(invalid="ignore"):
                y = np.clip(g - np.nanmean(g, axis=1, keepdims=True), -0.5, 0.5)
        return y, end

    def preds(self, tf, h, model, seeds, target, feats):
        key = (tf, h, model, tuple(seeds), target, feats)
        if key not in self._preds:
            X = self.X[tf] if feats == "base" else np.concatenate([self.X[tf], self.Xf[tf]], axis=2)
            y, end = self.target(tf, h, target)
            pr = np.full_like(self.P[tf]["close"], np.nan)
            for N in P3.TEST_YEARS:
                pr[self.P[tf]["year"] == N] = P3.fit_predict(X, y, end, self.P[tf], model, seeds, N)
            if len(self._preds) > 48:
                self._preds.pop(next(iter(self._preds)))
            self._preds[key] = pr
        return self._preds[key]


# ------------------------------------------------------------------ books

def simulate(W: np.ndarray, P4: dict, imp4: np.ndarray, half: float, fund: np.ndarray | None) -> dict:
    c = P4["close"]
    R = np.zeros_like(c)
    R[:-1] = np.nan_to_num(c[1:] / c[:-1] - 1)
    W = np.where(np.isfinite(c), W, 0.0)
    dW = np.abs(np.diff(np.r_[np.zeros((1, W.shape[1])), W], axis=0))
    yi = np.clip(P4["year"] - 2020, 0, 6)
    cost = (dW * (half + imp4[yi])).sum(axis=1)
    gross = (W * R).sum(axis=1)
    fpl = -(W * fund).sum(axis=1) if fund is not None else np.zeros(len(c))
    r = gross - cost + fpl
    day = P4["grid"] // P3.D1
    last = np.r_[day[1:] != day[:-1], True]

    def daily(x):
        e = np.cumprod(1 + x)[last]
        return np.r_[e[0] - 1, e[1:] / e[:-1] - 1]
    yr = P4["year"]
    return {"daily": daily(r), "gross_daily": daily(gross), "dyear": P3.year_of(P4["grid"][last]),
            "turnover_per_year": {int(y): round(float(dW[yr == y].sum()), 1) for y in P3.TEST_YEARS},
            "exposure_per_year": {int(y): round(float(np.abs(W[yr == y]).sum(axis=1).mean()), 3) for y in P3.TEST_YEARS},
            "funding_per_year": {int(y): round(float(fpl[yr == y].sum()), 4) for y in P3.TEST_YEARS}}


def book(w: World, spec: dict, cfg: dict, pred: np.ndarray) -> np.ndarray:
    """Executed, risk-sized 4h weights for one configuration."""
    tf = cfg["tf"]
    P = w.P[tf]
    hold = cfg["h_days"] * P3.BARS_PER_DAY[tf]
    if spec["venue"] == "perp_ls":
        F, _ = P3B.decide_ls(pred, P["member"], w.perp[tf], cfg["k"], hold)
        Fx = P3.to_exec_4h(F.astype(float), P["grid"], w.P4["grid"]).astype(np.int8)
        return P3B.size_ls(Fx, cfg["k"], 1.0, w.day_of_bar, w.sig, w.cov)
    member = P["member"] & (w.perp[tf] if spec["venue"] == "perp_long" else True)
    pr = pred if spec["target"] == "net" else np.where(np.isfinite(pred), pred + 1.0, np.nan)  # xs: rank only, no >0 bar
    W = P3.decide(pr, member, cfg["k"], w.gate[tf], hold=hold)
    Wx = P3.to_exec_4h(W, P["grid"], w.P4["grid"])
    return P4R.risk_weights(Wx, w.P4, w.day_of_bar, w.sig, w.cov)


# ------------------------------------------------------------------ one experiment

def p_sharpe_le0(d: np.ndarray, draws: int = 5000, seed: int = 5) -> float:
    n = len(d)
    if n < 60 or d.std() == 0:
        return 1.0
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / P3.BLOCK))
    idx = (rng.integers(0, n, (draws, nb))[:, :, None] + np.arange(P3.BLOCK)).reshape(draws, -1)[:, :n] % n
    s = d[idx]
    return float(((s.mean(1) / (s.std(1, ddof=1) + 1e-12)) <= 0).mean())


def experiment(w: World, spec: dict, seed_sets: dict) -> dict:
    t0 = time.time()
    ks = INNER_LS_K if spec["venue"] == "perp_ls" else INNER["k"]
    cfgs = [dict(tf=a, h_days=b, k=c, model=d) for a, b, c, d in product(INNER["tf"], INNER["h_days"], ks, INNER["model"])]
    half = P3.HALF_COST if spec["venue"] == "spot_long" else PERP_HALF
    fund = w.fund4 if spec["venue"] != "spot_long" else None
    out = {"spec": spec, "id": spec_id(spec), "seed_sets": {k: list(v) for k, v in seed_sets.items()}, "per_seed": {}}
    ic_cells = []
    for ss, seeds in seed_sets.items():
        runs = {}
        for cfg in cfgs:
            pr = w.preds(cfg["tf"], cfg["h_days"], cfg["model"], seeds, spec["target"], spec["feats"])
            Wx = book(w, spec, cfg, pr)
            sim = simulate(Wx, w.P4, w.imp["4h"], half, fund)
            runs[json.dumps(cfg, sort_keys=True)] = {"Wx": Wx, "sim": sim, "years": P3.year_stats(sim, P3.TEST_YEARS)}
        for tf, h, model in product(INNER["tf"], INNER["h_days"], INNER["model"]):   # gross IC diagnostic
            P = w.P[tf]
            pr = w.preds(tf, h, model, seeds, spec["target"], spec["feats"])
            n = P3.BARS_PER_DAY[tf]
            c = P["close"]
            g = np.full_like(c, np.nan)
            g[: len(c) - 1 - h * n] = c[1 + h * n:] / c[1: len(c) - h * n] - 1
            rows = np.flatnonzero(np.isin(P["year"], P3.NESTED_YEARS))[::n]
            vals = [pd.Series(pr[t][ok]).corr(pd.Series(g[t][ok]), method="spearman")
                    for t in rows for ok in [np.isfinite(pr[t]) & np.isfinite(g[t]) & P["member"][t]] if ok.sum() >= 5]
            ic_cells.append(float(np.nanmean(vals)) if vals else np.nan)
        curve, picks = [], {}
        for N in P3.NESTED_YEARS:
            past = tuple(y for y in P3.TEST_YEARS if y < N)
            scored = []
            for k, r in runs.items():
                if max(r["years"][y]["max_dd"] for y in past) > P3.DD_MAX:
                    continue
                d = r["sim"]["daily"][np.isin(r["sim"]["dyear"], past)]
                scored.append((P3.boot_sharpe_p5(d), k))
            scored.sort(reverse=True)
            ndays = int(np.unique(w.P4["grid"][w.P4["year"] == N] // P3.D1).size)
            if not scored:
                curve.append(np.zeros(ndays))
                picks[N] = {"eligible": 0}
                continue
            Wb = np.mean([runs[k]["Wx"] for _, k in scored[:10]], axis=0)
            sim = simulate(Wb, w.P4, w.imp["4h"], half, fund)
            curve.append(sim["daily"][sim["dyear"] == N])
            picks[N] = {"eligible": len(scored), **P3.year_stats(sim, (N,)).get(N, {}), "funding": sim["funding_per_year"][N]}
        d = np.concatenate(curve)
        out["per_seed"][ss] = {"curve": P3.ci(d), "p_sharpe_le0": round(p_sharpe_le0(d), 4), "picks": picks,
                               "cash_years": sum(p["eligible"] == 0 for p in picks.values()),
                               "median_config_net_22_25": round(float(np.median(
                                   [np.prod([1 + r["years"][y]["return"] for y in P3.NESTED_YEARS]) - 1 for r in runs.values()])), 4),
                               "best_config_net_22_25": round(float(max(
                                   np.prod([1 + r["years"][y]["return"] for y in P3.NESTED_YEARS]) - 1 for r in runs.values())), 4)}
    worse = min(out["per_seed"], key=lambda s: out["per_seed"][s]["curve"]["sharpe"])
    out["worse_seed_set"] = worse
    out["result"] = {k: out["per_seed"][worse]["curve"][k] for k in ("sharpe", "ann_return", "max_dd", "total")}
    out["result"].update(p_sharpe_le0=out["per_seed"][worse]["p_sharpe_le0"], cash_years=out["per_seed"][worse]["cash_years"])
    out["gross_ic_median"] = round(float(np.nanmedian(ic_cells)), 4)
    out["minutes"] = round((time.time() - t0) / 60, 1)
    out["at"] = now()
    return out


def gate(row: dict, m: int) -> dict:
    r = row["result"]
    need = 0.05 / max(1, m)
    why = []
    if r["p_sharpe_le0"] > need:
        why.append(f"P(Sharpe<=0) {r['p_sharpe_le0']} > {need:.4f} (0.05/{m})")
    if r["max_dd"] > P3.DD_MAX:
        why.append(f"max DD {r['max_dd']:.0%} > 18%")
    if r["cash_years"] > 1:
        why.append(f"{r['cash_years']} nested years in cash")
    return {"passes": not why, "why": why, "threshold": round(need, 5)}


# ------------------------------------------------------------------ ledger, report, page blob

def ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(x) for x in LEDGER.read_text(encoding="utf-8").splitlines() if x.strip()]


def next_job(done: list[dict]):
    seen = {(r["id"], tuple(sorted(r["seed_sets"]))) for r in done}
    base = {"s1": P3.SEED_SETS["s1"], "s2": P3.SEED_SETS["s2"]}
    for spec in SPECS:
        if (spec_id(spec), ("s1", "s2")) not in seen:
            return spec, base
    # replication: the best specs by worse-seed Sharpe, on the next fresh pair of seed sets
    best = sorted({r["id"]: r for r in done if tuple(sorted(r["seed_sets"])) == ("s1", "s2")}.values(),
                  key=lambda r: -r["result"]["sharpe"])[:6]
    for k in range(3, 200, 2):
        sets = {f"s{k}": tuple(range(k * 10 + 1, k * 10 + 5)), f"s{k + 1}": tuple(range((k + 1) * 10 + 1, (k + 1) * 10 + 5))}
        for r in best:
            if (r["id"], tuple(sorted(sets))) not in seen:
                return r["spec"], sets
    return None, None


def report(done: list[dict]) -> None:
    m = len(done)
    rows = sorted(done, key=lambda r: -r["result"]["sharpe"])
    passes = [r for r in done if r.get("gate", {}).get("passes")]
    L = ["# Plan v2 lab: report (auto-generated)", "",
         f"Updated {now()}. {m} experiments run ({len({r['id'] for r in done})} distinct specs). "
         f"Gate: worse seed set's bagged nested curve 2022-2025 with P(Sharpe<=0) <= 0.05/m, DD <= 18%, at most one "
         f"year in cash. **Candidates passing: {len(passes)}.**", "",
         "| spec | seed sets | Sharpe (worse) | P(Sharpe<=0) | ann. return | max DD | cash years | gross IC | best / median config net 22-25 | gate |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        ps = r["per_seed"][r["worse_seed_set"]]
        g = r.get("gate", {})
        L.append(f"| {r['id']} | {'+'.join(sorted(r['seed_sets']))} | {r['result']['sharpe']:+.2f} | {r['result']['p_sharpe_le0']:.3f} | "
                 f"{r['result']['ann_return']:+.1%} | {r['result']['max_dd']:.0%} | {r['result']['cash_years']} | "
                 f"{r.get('gross_ic_median')} | {ps['best_config_net_22_25']:+.0%} / {ps['median_config_net_22_25']:+.0%} | "
                 f"{'PASS' if g.get('passes') else 'no'} |")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    best = rows[0] if rows else None
    STATUS.write_text(json.dumps({
        "at": now(), "experiments": m, "distinct_specs": len({r["id"] for r in done}), "grid": len(SPECS),
        "candidates": [r["id"] for r in passes],
        "best": {"id": best["id"], **best["result"], "gate": best.get("gate")} if best else None,
        "latest": [{"id": r["id"], "seeds": "+".join(sorted(r["seed_sets"])), "at": r["at"], **r["result"],
                    "passes": r.get("gate", {}).get("passes", False)} for r in done[-8:]][::-1],
        "running": (LAB / "run.pid").exists()}, indent=1), encoding="utf-8")


def run(hours: float) -> int:
    LAB.mkdir(parents=True, exist_ok=True)
    (LAB / "run.pid").write_text(str(os.getpid()))
    started = time.time()
    worlds: dict = {}
    try:
        while time.time() - started < hours * 3600 and not STOP.exists():
            done = ledger()
            spec, sets = next_job(done)
            if spec is None:
                break
            if spec["cap"] not in worlds:
                worlds.clear()                      # one universe in memory at a time
                print(f"[{now()}] loading the top-{spec['cap']} PIT world", flush=True)
                worlds[spec["cap"]] = World(spec["cap"])
            row = experiment(worlds[spec["cap"]], spec, sets)
            row["gate"] = gate(row, len(done) + 1)
            with LEDGER.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
            report(ledger())
            print(f"[{now()}] {row['id']} {'+'.join(sorted(sets))}: Sharpe {row['result']['sharpe']:+.2f} "
                  f"P<=0 {row['result']['p_sharpe_le0']:.3f} DD {row['result']['max_dd']:.0%} cash {row['result']['cash_years']} "
                  f"IC {row['gross_ic_median']} {'PASS' if row['gate']['passes'] else 'no'} [{row['minutes']}m]", flush=True)
    finally:
        (LAB / "run.pid").unlink(missing_ok=True)
        report(ledger())
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("run", "report"))
    ap.add_argument("--hours", type=float, default=24)
    a = ap.parse_args()
    if a.stage == "report":
        report(ledger())
        return 0
    return run(a.hours)


if __name__ == "__main__":
    raise SystemExit(main())
