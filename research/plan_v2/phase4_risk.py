"""Plan v2, phase 4: portfolio risk layer on the phase 3 pipeline (PLAN.md).

Same predictions, books and honest execution as phase3_select.py; only the weights change:
  vol target   each held coin gets 1% of daily risk: w = 1% / sigma_60d (daily), at most 1.5 slots
  budget       the book's daily volatility (90-day covariance) is scaled down to <= 2%
  clusters     coins with 90-day correlation > 0.85 are one group (connected components); a group
               holds at most 40% of the book
  no leverage  weights sum to <= 1; risk weights are refreshed when the held set changes or at the
               day's first bar, so a drifting sigma does not trade every bar
Measured per configuration and seed set, base vs risk:
  tail DD     max DD over 2021-2025 (median and p90 over configurations)
  net         2022-2025 compounded
  nested      the phase 3 selection again (p5 bootstrap Sharpe, DD <= 18%, argmax and bagging)
  stress      at every day's close: BTC -20% and other coins -35% at once, spreads x3 and exits 2% worse,
              added to the drawdown at that close; worst case over the days
Falsified if the risk layer does not cut the tail DD without destroying the net return.

    python research/plan_v2/phase4_risk.py
"""

from __future__ import annotations

import json
import time
from itertools import product
from pathlib import Path

import numpy as np

import phase3_select as P3

HERE = Path(__file__).resolve().parent
OUT = HERE / "phase4_results.json"
POS_RISK, BOOK_RISK, CLUSTER_RHO, CLUSTER_MAX, SLOT_MAX = 0.01, 0.02, 0.85, 0.40, 1.5


def daily_risk(P1: dict) -> tuple[np.ndarray, np.ndarray]:
    """Per day: sigma_60d per coin (T1 x S) and the 90-day covariance (T1 x S x S), from closes
    up to and including that day (causal for a decision at its close)."""
    c = P1["close"]
    r = np.full_like(c, np.nan)
    r[1:] = c[1:] / c[:-1] - 1
    T, S = c.shape
    sig = np.full((T, S), np.nan)
    cov = np.full((T, S, S), np.nan)
    for t in range(60, T):
        w = r[t - 59: t + 1]
        sig[t] = np.nanstd(w, axis=0)
        if t >= 90:
            x = r[t - 89: t + 1]
            ok = np.isfinite(x).sum(axis=0) >= 60
            xx = np.where(np.isfinite(x), x, 0.0)
            m = xx - xx.mean(axis=0)
            cv = m.T @ m / 89
            cv[~ok, :] = np.nan
            cv[:, ~ok] = np.nan
            cov[t] = cv
    return sig, cov


def clusters(cv: np.ndarray, held: np.ndarray) -> list[list[int]]:
    idx = list(np.flatnonzero(held))
    if len(idx) < 2:
        return [idx] if idx else []
    sd = np.sqrt(np.clip(np.diag(cv), 1e-12, None))
    rho = cv / np.outer(sd, sd)
    seen, out = set(), []
    for i in idx:
        if i in seen:
            continue
        comp, stack = [], [i]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u); comp.append(u)
            stack += [v for v in idx if v not in seen and np.isfinite(rho[u, v]) and rho[u, v] > CLUSTER_RHO]
        out.append(comp)
    return out


def risk_weights(Wx: np.ndarray, P4: dict, day_of_bar: np.ndarray, sig: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """The phase 3 executed weights (1/K per held coin) re-sized by the risk rules."""
    T, S = Wx.shape
    out = np.zeros_like(Wx)
    prev_set, prev_w, prev_day = None, None, -1
    for i in range(T):
        held = Wx[i] > 0
        if not held.any():
            prev_set, prev_w = held, np.zeros(S)
            continue
        d = day_of_bar[i]
        if prev_set is not None and (held == prev_set).all() and d == prev_day:
            out[i] = prev_w
            continue
        k_slot = float(Wx[i][held][0])          # 1/K
        s = sig[d] if d >= 0 else np.full(S, np.nan)
        w = np.zeros(S)
        for j in np.flatnonzero(held):
            sj = s[j] if np.isfinite(s[j]) and s[j] > 0 else 0.05
            w[j] = min(POS_RISK / sj, SLOT_MAX * k_slot)
        cv = cov[d] if d >= 0 else None
        if cv is not None and np.isfinite(cv[np.ix_(held, held)]).all():
            for comp in clusters(cv, held):
                tot = w[comp].sum()
                if tot > CLUSTER_MAX:
                    w[comp] *= CLUSTER_MAX / tot
            pv = float(np.sqrt(max(w @ np.nan_to_num(cv) @ w, 0.0)))
            if pv > BOOK_RISK:
                w *= BOOK_RISK / pv
        if w.sum() > 1:
            w /= w.sum()
        out[i] = w
        prev_set, prev_w, prev_day = held, w, d
    return out


def stress(sim: dict, W_day: np.ndarray, btc_j: int, imp_day: np.ndarray) -> dict:
    """Worst of (drawdown at a day's close + the shock's loss on that day's weights)."""
    eq = np.cumprod(1 + sim["daily"])
    dd = 1 - eq / np.maximum.accumulate(eq)
    shock = np.full(W_day.shape[1], -0.35)
    shock[btc_j] = -0.20
    expo = W_day.sum(axis=1)
    loss = -(W_day @ shock) + (W_day * (3 * P3.HALF_COST + 3 * imp_day)).sum(axis=1) + 0.02 * expo
    n = min(len(dd), len(loss))
    comb = 1 - (1 - dd[:n]) * (1 - loss[:n])
    return {"worst_stress_dd": round(float(comb.max()), 4), "worst_shock_loss": round(float(loss.max()), 4),
            "mean_exposure": round(float(expo.mean()), 3)}


def main() -> int:
    t0 = time.time()
    st = P3.prepare()
    P, P4, imp, gate, preds = st["P"], st["P4"], st["imp"], st["gate"], st["preds"]
    P1 = P["1d"]
    sig, cov = daily_risk(P1)
    # the day whose close is the last one at or before each 4h bar (decisions read that day's risk)
    day_of_bar = np.searchsorted(P1["grid"], P4["grid"], side="right") - 1
    last = np.r_[(P4["grid"] // P3.D1)[1:] != (P4["grid"] // P3.D1)[:-1], True]
    yi4 = np.clip(P4["year"] - 2020, 0, 6)
    btc_j = P4["coins"].index("BTCUSDT")
    print(f"[{time.time() - t0:.0f}s] risk inputs ready", flush=True)
    cfgs = [dict(zip(P3.LEVERS, v)) for v in product(*P3.LEVERS.values())]
    runs = {}
    for ss in P3.SEED_SETS:
        for cfg in cfgs:
            tf = cfg["tf"]
            W = P3.decide(preds[(tf, cfg["h_days"], cfg["model"], ss)], P[tf]["member"], cfg["k"],
                          gate[tf] if cfg["gate"] else None, hold=cfg["h_days"] * P3.BARS_PER_DAY[tf])
            Wx = P3.to_exec_4h(W, P[tf]["grid"], P4["grid"])
            for mode, w in (("base", Wx), ("risk", risk_weights(Wx, P4, day_of_bar, sig, cov))):
                sim = P3.simulate(w, P4, imp["4h"])
                runs[(ss, json.dumps(cfg, sort_keys=True), mode)] = {
                    "Wx": w, "sim": sim, "years": P3.year_stats(sim, P3.TEST_YEARS),
                    "stress": stress(sim, w[last], btc_j, imp["4h"][yi4[last]])}
        print(f"[{time.time() - t0:.0f}s] {ss}: 72 configurations x base/risk", flush=True)
    res = {"params": {"pos_risk": POS_RISK, "book_risk": BOOK_RISK, "cluster_rho": CLUSTER_RHO,
                      "cluster_max": CLUSTER_MAX, "slot_max": SLOT_MAX}, "summary": {}, "nested": {}}
    for ss in P3.SEED_SETS:
        for mode in ("base", "risk"):
            rows = [runs[(ss, json.dumps(c, sort_keys=True), mode)] for c in cfgs]
            tail = [max(r["years"][y]["max_dd"] for y in P3.TEST_YEARS) for r in rows]
            net = [float(np.prod([1 + r["years"][y]["return"] for y in P3.NESTED_YEARS]) - 1) for r in rows]
            sdd = [r["stress"]["worst_stress_dd"] for r in rows]
            res["summary"][f"{ss} {mode}"] = {
                "tail_dd_median": round(float(np.median(tail)), 4), "tail_dd_p90": round(float(np.percentile(tail, 90)), 4),
                "tail_dd_min": round(float(np.min(tail)), 4),
                "net_22_25_median": round(float(np.median(net)), 4), "net_22_25_p90": round(float(np.percentile(net, 90)), 4),
                "stress_dd_median": round(float(np.median(sdd)), 4), "stress_dd_p90": round(float(np.percentile(sdd, 90)), 4),
                "eligible_dd18_all_years": int(sum(t <= P3.DD_MAX for t in tail)),
                "positive_every_year_22_25": int(sum(min(r["years"][y]["return"] for y in P3.NESTED_YEARS) > 0 for r in rows))}
            # nested selection, as phase 3
            curves = {"argmax": [], **{f"bag{k}": [] for k in P3.BAG_K}}
            picks = {}
            for N in P3.NESTED_YEARS:
                past = tuple(y for y in P3.TEST_YEARS if y < N)
                scored = []
                for c in cfgs:
                    r = runs[(ss, json.dumps(c, sort_keys=True), mode)]
                    if max(r["years"][y]["max_dd"] for y in past) > P3.DD_MAX:
                        continue
                    d = r["sim"]["daily"][np.isin(r["sim"]["dyear"], past)]
                    scored.append((P3.boot_sharpe_p5(d), json.dumps(c, sort_keys=True)))
                scored.sort(reverse=True)
                picks[N] = {"eligible": len(scored), "top": [(round(s, 3), k) for s, k in scored[:3]]}
                ndays = int(np.unique(P4["grid"][P4["year"] == N] // P3.D1).size)
                for name, kk in (("argmax", 1), *((f"bag{k}", k) for k in P3.BAG_K)):
                    if not scored:
                        curves[name].append(np.zeros(ndays))
                        continue
                    Wb = np.mean([runs[(ss, k, mode)]["Wx"] for _, k in scored[:kk]], axis=0)
                    sim = P3.simulate(Wb, P4, imp["4h"])
                    curves[name].append(sim["daily"][sim["dyear"] == N])
                    picks[N].setdefault("year", {})[name] = P3.year_stats(sim, (N,)).get(N)
            res["nested"][f"{ss} {mode}"] = {"picks": picks, "curves": {k: P3.ci(np.concatenate(v)) for k, v in curves.items()}}
    diffs = [abs(runs[("s1", json.dumps(c, sort_keys=True), "risk")]["years"][y]["return"]
                 - runs[("s2", json.dumps(c, sort_keys=True), "risk")]["years"][y]["return"])
             for c in cfgs for y in P3.TEST_YEARS]
    res["seed_noise_risk_points"] = {"median": round(float(np.median(diffs)) * 100, 2), "p90": round(float(np.percentile(diffs, 90)) * 100, 2)}
    res["all_configs"] = {f"{ss} {mode} {k}": {"years": v["years"], "stress": v["stress"]} for (ss, k, mode), v in runs.items()}
    res["minutes"] = round((time.time() - t0) / 60, 1)
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("summary", "seed_noise_risk_points")}, indent=1))
    for k, v in res["nested"].items():
        print(k, json.dumps(v["curves"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
