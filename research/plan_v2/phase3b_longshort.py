"""Plan v2, phase 3b: market-neutral long/short on the phase 3 signal (operator go, 2026-10-19).

Why: phase 3 found a robust out-of-sample cross-sectional IC (98 of 120 cells t > 2), destroyed in a
long-only book by market direction (2021, 2022, 2025) and cost. Long the best-ranked coins and short
the worst keeps the ranking and drops most of the market.

Same predictions as phase3_select.prepare() (one net-return model, walk-forward, embargo), same honest
execution (decide at t, fill at t+1, 0.225% + ADV impact per side), the phase 4 risk layer:
  legs       long the top K by prediction among the year's PIT members; short the bottom K among
             members that have a USD-M perpetual at that bar (Binance funding history, cache/; CTXC,
             GXS, PEPE and SHIB never had one). Held for H; at expiry kept while still in the top /
             bottom 2K
  sizing     each position 1% daily risk (w = 1% / sigma_60d, at most 1.5 slots of gross/(2K)); the
             short leg is scaled to the long leg's dollars (dollar neutral); clusters (rho > 0.85)
             capped at 40% of gross per side; book volatility (signed, 90-day covariance) <= 2%/day;
             gross <= the `gross` lever
  funding    longs are spot (no funding); shorts are perpetuals and receive the funding rate (pay it
             when negative), accrued per 4h bar; reported separately
Levers (5): timeframe 4h | 1d, horizon 1 | 3 | 7 days, K 2 | 3 | 5, model ridge | gbm, gross 1 | 2 -> 72.
Selection as phase 3/4: nested on 2021..N-1, DD <= 18%, p5 bootstrap Sharpe, argmax / bag 10 / bag 20.

FALSIFIED (fixed before the run) if, on the worse seed set, the bagged nested curve 2022-2025 has a
Sharpe <= 0, or no configuration is eligible in 2 or more of the 4 nested years.

    python research/plan_v2/phase3b_longshort.py
"""

from __future__ import annotations

import json
import time
from itertools import product
from pathlib import Path

import numpy as np

import phase3_select as P3
import phase4_risk as P4R

HERE = Path(__file__).resolve().parent
OUT = HERE / "phase3b_results.json"
LEVERS = {"tf": ("4h", "1d"), "h_days": (1, 3, 7), "k": (2, 3, 5), "model": ("ridge", "gbm"), "gross": (1.0, 2.0)}


def funding_panel(P4: dict) -> tuple[np.ndarray, np.ndarray]:
    """(T4 x S) funding accrued per 4h bar (rate / 2 of the last 8h settlement at or before the
    bar's open) and the shortable mask (a perpetual existed: first <= bar <= last settlement + 8h)."""
    T, S = P4["close"].shape
    fund = np.zeros((T, S))
    can = np.zeros((T, S), dtype=bool)
    opens = P4["grid"] - P3.H4
    for j, s in enumerate(P4["coins"]):
        f = P3.CACHE / f"funding_{s}.json"
        rows = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        if not rows:
            continue
        t = np.array([r["t_ms"] for r in rows], dtype=np.int64) * 10**6
        v = np.array([r["rate"] for r in rows])
        i = np.searchsorted(t, opens, side="right") - 1
        ok = i >= 0
        fund[ok, j] = v[i[ok]] / 2
        can[:, j] = (P4["grid"] >= t[0]) & (P4["grid"] <= t[-1] + 8 * 3600 * 10**9)
    return fund, can


def decide_ls(pred, member, shortable, k: int, hold: int) -> tuple[np.ndarray, np.ndarray]:
    """(T x S) +1 long / -1 short / 0 flags at each bar's close of its own timeframe."""
    T, S = pred.shape
    F = np.zeros((T, S), dtype=np.int8)
    side = np.zeros(S, dtype=np.int8)
    since = np.zeros(S, dtype=int)
    for t in range(T):
        okL = member[t] & np.isfinite(pred[t])
        okS = okL & shortable[t]
        pL = np.where(okL, pred[t], -np.inf)
        pS = np.where(okS, pred[t], np.inf)
        rL = np.empty(S, dtype=int); rL[np.argsort(-pL)] = np.arange(S)
        rS = np.empty(S, dtype=int); rS[np.argsort(pS)] = np.arange(S)
        since[side != 0] += 1
        exp = (side != 0) & (since >= hold)
        dropL = (side == 1) & (~okL | (exp & ~(rL < 2 * k)))
        dropS = (side == -1) & (~okS | (exp & ~(rS < 2 * k)))
        side[dropL | dropS] = 0
        since[exp & (side != 0)] = 0
        if okL.sum() >= 2 * k and okS.sum() >= k:
            freeL = k - int((side == 1).sum())
            for j in np.argsort(-pL)[:k]:
                if freeL <= 0:
                    break
                if side[j] == 0 and okL[j]:
                    side[j], since[j], freeL = 1, 0, freeL - 1
            freeS = k - int((side == -1).sum())
            for j in np.argsort(pS)[:k]:
                if freeS <= 0:
                    break
                if side[j] == 0 and okS[j]:
                    side[j], since[j], freeS = -1, 0, freeS - 1
        F[t] = side
    return F, None


def size_ls(Fx: np.ndarray, k: int, gross: float, day_of_bar, sig, cov) -> np.ndarray:
    """Risk-sized, dollar-neutral signed weights on the 4h grid from executed flags."""
    T, S = Fx.shape
    out = np.zeros((T, S))
    slot = gross / (2 * k)
    prev, prev_w, prev_d = None, None, -1
    for i in range(T):
        f = Fx[i]
        if not f.any():
            prev, prev_w = f.copy(), np.zeros(S)
            continue
        d = day_of_bar[i]
        if prev is not None and (f == prev).all() and d == prev_d:
            out[i] = prev_w
            continue
        s = sig[d] if d >= 0 else np.full(S, np.nan)
        w = np.zeros(S)
        for j in np.flatnonzero(f):
            sj = s[j] if np.isfinite(s[j]) and s[j] > 0 else 0.05
            w[j] = f[j] * min(P4R.POS_RISK / sj, P4R.SLOT_MAX * slot)
        L, Sh = w[w > 0].sum(), -w[w < 0].sum()
        if L > 0 and Sh > 0:            # dollar neutral: both legs at the smaller one's size
            m = min(L, Sh)
            w[w > 0] *= m / L
            w[w < 0] *= m / Sh
        else:
            w[:] = 0.0
        cv = cov[d] if d >= 0 else None
        nz = w != 0
        if cv is not None and nz.any() and np.isfinite(cv[np.ix_(nz, nz)]).all():
            for sgn in (1, -1):
                held = np.sign(w) == sgn
                for comp in P4R.clusters(cv, held):
                    tot = np.abs(w[comp]).sum()
                    if tot > P4R.CLUSTER_MAX * gross / 2:
                        w[comp] *= P4R.CLUSTER_MAX * gross / 2 / tot
            pv = float(np.sqrt(max(w @ np.nan_to_num(cv) @ w, 0.0)))
            if pv > P4R.BOOK_RISK:
                w *= P4R.BOOK_RISK / pv
        g = np.abs(w).sum()
        if g > gross:
            w *= gross / g
        out[i] = w
        prev, prev_w, prev_d = f.copy(), w, d
    return out


def simulate_ls(Wx: np.ndarray, P4: dict, imp4: np.ndarray, fund: np.ndarray) -> dict:
    sim = P3.simulate(Wx, P4, imp4)
    # funding on the short leg (perpetuals), per 4h bar; add it to the daily series
    gain = (np.where(Wx < 0, -Wx, 0.0) * fund).sum(axis=1)
    day = P4["grid"] // P3.D1
    last = np.r_[day[1:] != day[:-1], True]
    # rebuild daily with funding: compound 4h net returns incl. funding
    c = P4["close"]
    R = np.zeros_like(c)
    R[:-1] = np.nan_to_num(c[1:] / c[:-1] - 1)
    Wa = np.where(np.isfinite(c), Wx, 0.0)
    dW = np.abs(np.diff(np.r_[np.zeros((1, Wa.shape[1])), Wa], axis=0))
    yi = np.clip(P4["year"] - 2020, 0, 6)
    cost = (dW * (P3.HALF_COST + imp4[yi])).sum(axis=1)
    r = (Wa * R).sum(axis=1) - cost + gain
    eod = np.cumprod(1 + r)[last]
    sim["daily"] = np.r_[eod[0] - 1, eod[1:] / eod[:-1] - 1]
    sim["funding_per_year"] = {int(y): round(float(gain[P4["year"] == y].sum()), 4) for y in P3.TEST_YEARS}
    sim["cost_per_year"] = {int(y): round(float(cost[P4["year"] == y].sum()), 4) for y in P3.TEST_YEARS}
    sim["gross_exposure"] = {int(y): round(float(np.abs(Wa[P4["year"] == y]).sum(axis=1).mean()), 3) for y in P3.TEST_YEARS}
    return sim


def main() -> int:
    t0 = time.time()
    st = P3.prepare()
    P, P4, imp, preds = st["P"], st["P4"], st["imp"], st["preds"]
    sig, cov = P4R.daily_risk(P["1d"])
    day_of_bar = np.searchsorted(P["1d"]["grid"], P4["grid"], side="right") - 1
    fund, can4 = funding_panel(P4)
    can = {"4h": can4, "1d": can4[np.clip(np.searchsorted(P4["grid"], P["1d"]["grid"]), 0, len(P4["grid"]) - 1)]}
    print(f"[{time.time() - t0:.0f}s] funding and risk inputs ready", flush=True)
    cfgs = [dict(zip(LEVERS, v)) for v in product(*LEVERS.values())]
    runs = {}
    for ss in P3.SEED_SETS:
        flags = {}
        for cfg in cfgs:
            tf = cfg["tf"]
            fk = (tf, cfg["h_days"], cfg["model"], cfg["k"])
            if fk not in flags:
                F, _ = decide_ls(preds[(tf, cfg["h_days"], cfg["model"], ss)], P[tf]["member"], can[tf],
                                 cfg["k"], cfg["h_days"] * P3.BARS_PER_DAY[tf])
                flags[fk] = P3.to_exec_4h(F.astype(float), P[tf]["grid"], P4["grid"]).astype(np.int8)
            Wx = size_ls(flags[fk], cfg["k"], cfg["gross"], day_of_bar, sig, cov)
            sim = simulate_ls(Wx, P4, imp["4h"], fund)
            ys = P3.year_stats({**sim, "gross_daily": sim["daily"]}, P3.TEST_YEARS)
            for y in ys:
                ys[y].pop("gross", None)
                ys[y]["funding"] = sim["funding_per_year"][y]
                ys[y]["cost"] = sim["cost_per_year"][y]
                ys[y]["gross_exposure"] = sim["gross_exposure"][y]
            runs[(ss, json.dumps(cfg, sort_keys=True))] = {"Wx": Wx, "sim": sim, "years": ys}
        print(f"[{time.time() - t0:.0f}s] {ss}: {len(cfgs)} long/short configurations", flush=True)
    res = {"levers": LEVERS, "summary": {}, "nested": {}}
    for ss in P3.SEED_SETS:
        rows = [runs[(ss, json.dumps(c, sort_keys=True))] for c in cfgs]
        tail = [max(r["years"][y]["max_dd"] for y in P3.TEST_YEARS) for r in rows]
        net = [float(np.prod([1 + r["years"][y]["return"] for y in P3.NESTED_YEARS]) - 1) for r in rows]
        res["summary"][ss] = {"tail_dd_median": round(float(np.median(tail)), 4), "tail_dd_min": round(float(min(tail)), 4),
                              "net_22_25_median": round(float(np.median(net)), 4), "net_22_25_p90": round(float(np.percentile(net, 90)), 4),
                              "eligible_dd18_all_years": int(sum(t <= P3.DD_MAX for t in tail)),
                              "positive_every_year_22_25": int(sum(min(r["years"][y]["return"] for y in P3.NESTED_YEARS) > 0 for r in rows)),
                              "median_by_year": {y: round(float(np.median([r["years"][y]["return"] for r in rows])), 4) for y in P3.TEST_YEARS}}
        curves = {"argmax": [], **{f"bag{k}": [] for k in P3.BAG_K}}
        picks = {}
        for N in P3.NESTED_YEARS:
            past = tuple(y for y in P3.TEST_YEARS if y < N)
            scored = []
            for c in cfgs:
                r = runs[(ss, json.dumps(c, sort_keys=True))]
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
                Wb = np.mean([runs[(ss, k)]["Wx"] for _, k in scored[:kk]], axis=0)
                sim = simulate_ls(Wb, P4, imp["4h"], fund)
                curves[name].append(sim["daily"][sim["dyear"] == N])
                picks[N].setdefault("year", {})[name] = {**P3.year_stats({**sim, "gross_daily": sim["daily"]}, (N,)).get(N, {}),
                                                        "funding": sim["funding_per_year"][N]}
        res["nested"][ss] = {"picks": picks, "curves": {k: P3.ci(np.concatenate(v)) for k, v in curves.items()}}
    diffs = [abs(runs[("s1", json.dumps(c, sort_keys=True))]["years"][y]["return"]
                 - runs[("s2", json.dumps(c, sort_keys=True))]["years"][y]["return"]) for c in cfgs for y in P3.TEST_YEARS]
    res["seed_noise_points"] = {"median": round(float(np.median(diffs)) * 100, 2), "p90": round(float(np.percentile(diffs, 90)) * 100, 2)}
    worse = min(res["nested"], key=lambda s: res["nested"][s]["curves"]["bag10"]["sharpe"])
    empty = sum(res["nested"][worse]["picks"][N]["eligible"] == 0 for N in P3.NESTED_YEARS)
    res["verdict"] = {"worse_seed_set": worse, "bag10_sharpe": res["nested"][worse]["curves"]["bag10"]["sharpe"],
                      "years_without_eligible": empty,
                      "falsified": bool(res["nested"][worse]["curves"]["bag10"]["sharpe"] <= 0 or empty >= 2)}
    res["all_configs"] = {f"{ss} {k}": v["years"] for (ss, k), v in runs.items()}
    res["minutes"] = round((time.time() - t0) / 60, 1)
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("summary", "seed_noise_points", "verdict")}, indent=1))
    for ss, v in res["nested"].items():
        print(ss, json.dumps(v["curves"]))
        for N, p in v["picks"].items():
            print("  ", N, p["eligible"], p.get("year", {}).get("bag10"), p["top"][:1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
