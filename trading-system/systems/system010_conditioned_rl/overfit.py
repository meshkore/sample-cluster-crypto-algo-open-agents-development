"""How much of the champion is selection luck (audit 2026-10-15, item 2.2).

The models are walk-forward; the configuration was not: the champion is the maximum of
thousands of trials scored on all of 2022-2025. Three measures, from the trial ledger alone
(no model fits):

  nested   for N in 2023..2025 the selection law picks a configuration on years < N only,
           then year N is read. Chained, that "chosen-on-the-past" curve is the system's
           expected performance; the max-over-trials champion is a diagnostic.
  PBO      Probability of Backtest Overfitting by CSCV (Bailey, Borwein, Lopez de Prado,
           Zhu 2017) over the eligible trials: monthly Sharpe when rows carry `monthly`
           (search.evaluate adds it from 2026-10-15), else the law on yearly results -
           coarse, 4 years give 6 splits.
  DSR      Deflated Sharpe of the champion (Bailey & Lopez de Prado 2014) given the trials.

Writes research/system10/rnd/overfit.json; search.py refuses a release while PBO > 0.5.
    python -m system010_conditioned_rl.overfit [--quiet]
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist

import numpy as np

OUT = Path(__file__).resolve().parents[3] / "research" / "system10" / "rnd" / "overfit.json"
YEARS = (2022, 2023, 2024, 2025)
NESTED_YEARS = (2023, 2024, 2025)
PBO_MAX = 0.5
# search.law's constants, repeated so the maths imports no model code (tests check equality)
LAW_FLOOR, LAW_CAP, LAW_DD = (0.5, 0.3, 0.2), 0.50, 0.25
DD_CAP, MIN_TRADES, DAY_SHARE_MIN, GAP_MAX = 0.25, 50, 0.70, 40
MIN_MONTHLY_ROWS = 50
EULER = 0.5772156649015329


# ------------------------------------------------------------------ the law, vectorised

def law_vec(R: np.ndarray, D: np.ndarray) -> np.ndarray:
    """search.law for many rows at once. R, D: (rows, years), years in chronological order."""
    k = R.shape[1]
    w = np.array(LAW_FLOOR[:max(1, k - 1)])
    floor = np.sort(R, axis=1)[:, :len(w)] @ w / w.sum()
    rw = np.arange(1, k + 1, dtype=float)
    recent = np.minimum(R, LAW_CAP) @ rw / rw.sum()
    return np.round(0.5 * floor + 0.5 * recent - LAW_DD * D.max(axis=1), 4)


# ------------------------------------------------------------------ nested selection

def _yr(r: dict, seeds: str) -> dict:
    src = r if seeds == "main" else (r.get("confirm") or {})
    return {int(k): v for k, v in (src.get("years") or {}).items()}


def past_view(rows: list[dict], N: int, seeds: str = "main") -> list[dict]:
    """What a chooser standing at 1 January N could see: years < N only. Nothing of N or
    later is copied, so a choice made from this view cannot read N."""
    out = []
    for r in rows:
        y = _yr(r, "confirm" if seeds == "confirm" else "main")
        past = {k: v for k, v in y.items() if k < N}
        if len(past) != len([k for k in YEARS if k < N]):
            continue
        av = {int(k): v for k, v in ((r.get("availability") or {}).get("per_year") or {}).items() if int(k) < N}
        view = {"id": r["id"], "cfg": r["cfg"], "years": past, "availability": av}
        if seeds == "both":
            view["confirm_years"] = {k: v for k, v in _yr(r, "confirm").items() if k < N}
        out.append(view)
    return out


def eligible_past(v: dict, guarded=None) -> bool:
    """The search's eligibility, judged on the past years only."""
    if guarded is not None and not guarded(v["cfg"]):
        return False
    if float(v["cfg"].get("size_down", 1.0)) <= 0:
        return False
    sets = [v["years"]] + ([v["confirm_years"]] if "confirm_years" in v else [])
    for ys in sets:
        if any(float(x["max_dd"]) > DD_CAP or int(x["trades"]) < MIN_TRADES for x in ys.values()):
            return False
    return all(a["day_share"] >= DAY_SHARE_MIN and a["longest_gap_days"] <= GAP_MAX
               for a in v["availability"].values())


def choose(view: list[dict], guarded=None, pool_out: list | None = None) -> str | None:
    """The selection law on a past-only view: the id with the best (score, worst q)."""
    pool = [v for v in view if eligible_past(v, guarded)]
    if pool_out is not None:
        pool_out += [v["id"] for v in pool]
    if not pool:
        return None

    def score(ys):
        ks = sorted(ys)
        R = np.array([[float(ys[k]["return"]) for k in ks]])
        D = np.array([[float(ys[k]["max_dd"]) for k in ks]])
        return float(law_vec(R, D)[0])

    def key(v):
        s = score(v["years"])
        if "confirm_years" in v:
            s = min(s, score(v["confirm_years"]))
        return (s, min(float(x["q"]) for x in v["years"].values()))
    return max(pool, key=key)["id"]


def curve(rets: dict) -> dict:
    """Chained yearly results: {year: (return, max_dd)} -> CAGR, worst year, max yearly DD."""
    if not rets:
        return {}
    ys = sorted(rets)
    r = [rets[y][0] for y in ys]
    total = float(np.prod([1 + x for x in r]))
    return {"years": {str(y): round(rets[y][0], 4) for y in ys},
            "cagr": round(total ** (1 / len(r)) - 1, 4), "worst_year": round(min(r), 4),
            "max_dd": round(max(rets[y][1] for y in ys), 4), "total": round(total - 1, 4)}


def nested(rows: list[dict], guarded=None, seeds: str = "main") -> dict:
    """seeds="main": choose and read on the main seed set (the chosen config's confirm-set
    reading is added when it exists). seeds="both": only rows run on both seed sets, chosen on
    the weaker of the two (as the search ranks), read on the confirm set."""
    by_id = {r["id"]: r for r in rows}           # the last row of an id wins
    rows = list(by_id.values())
    picks, chain = {}, {}
    for N in NESTED_YEARS:
        cands: list = []
        pid = choose(past_view(rows, N, seeds), guarded, cands)
        if pid is None:
            continue
        r = by_id[pid]
        main, conf = _yr(r, "main").get(N), _yr(r, "confirm").get(N)
        read = conf if seeds == "both" else main
        if read is None:
            continue
        side = "confirm" if seeds == "both" else "main"
        pool = [float(_yr(by_id[i], side)[N]["return"]) for i in cands if N in _yr(by_id[i], side)]
        pct = float(np.mean(np.array(pool) < float(read["return"]))) if pool else None
        picks[str(N)] = {"id": pid, "return": read["return"], "max_dd": read["max_dd"],
                         "confirm_return": conf["return"] if (conf and seeds == "main") else None,
                         "candidates": len(cands),
                         "pct_rank_in_year": round(pct, 3) if pct is not None else None}
        chain[N] = (float(read["return"]), float(read["max_dd"]))
    return {"seeds": seeds, "picks": picks, "curve": curve(chain)}


# ------------------------------------------------------------------ PBO by CSCV

def cscv_pbo(M: np.ndarray, S: int, metric=None, max_combos: int = 20_000, seed: int = 0) -> dict:
    """Bailey et al. 2017. M: (periods, trials). The periods are cut into S blocks; for each
    way of taking S/2 blocks in-sample, the in-sample best trial's relative rank w out of
    sample gives a logit log(w / (1 - w)); PBO = share of logits <= 0.
    metric(idx) -> per-trial performance on period rows idx; default the Sharpe ratio."""
    T, N = M.shape
    blocks = np.array_split(np.arange(T), S)
    combos = list(itertools.combinations(range(S), S // 2))
    if len(combos) > max_combos:
        rng = np.random.default_rng(seed)
        combos = [combos[i] for i in rng.choice(len(combos), max_combos, replace=False)]
    if metric is None:
        bs = np.array([M[b].sum(axis=0) for b in blocks])
        bq = np.array([(M[b] ** 2).sum(axis=0) for b in blocks])
        bn = np.array([len(b) for b in blocks], dtype=float)

        def perf(sel):
            n, s, q = bn[sel].sum(), bs[sel].sum(axis=0), bq[sel].sum(axis=0)
            mu = s / n
            sd = np.sqrt(np.maximum(q / n - mu ** 2, 0) * n / max(n - 1, 1))
            return mu / np.where(sd > 0, sd, np.inf)
    else:
        def perf(sel):
            return metric(np.concatenate([blocks[i] for i in sel]))
    logits = []
    for c in combos:
        cs = list(c)
        os_ = [i for i in range(S) if i not in c]
        ins, oos = perf(cs), perf(os_)
        best = int(np.argmax(ins))
        v = oos[best]
        rank = np.sum(oos < v) + 0.5 * (np.sum(oos == v) - 1) + 1     # 1..N, ties averaged
        w = rank / (N + 1)
        logits.append(math.log(w / (1 - w)))
    lg = np.array(logits)
    return {"pbo": round(float(np.mean(lg <= 0)), 4), "splits": len(lg), "blocks": S,
            "trials": N, "periods": T, "median_logit": round(float(np.median(lg)), 4)}


# ------------------------------------------------------------------ Deflated Sharpe

def deflated_sharpe(returns, sr_trials, n_trials: int) -> dict:
    """Bailey & Lopez de Prado 2014: P(true Sharpe > the best of n_trials pure-noise Sharpes).
    Per-period Sharpe; skew and kurtosis from the returns when there are >= 12, else normal."""
    r = np.asarray(returns, dtype=float)
    T = len(r)
    sd = r.std(ddof=1)
    sr = float(r.mean() / sd) if sd > 0 else 0.0
    var = float(np.var(np.asarray(sr_trials, dtype=float), ddof=1))
    nd = NormalDist()
    n = max(int(n_trials), 2)
    sr0 = math.sqrt(var) * ((1 - EULER) * nd.inv_cdf(1 - 1 / n) + EULER * nd.inv_cdf(1 - 1 / (n * math.e)))
    if T >= 12 and sd > 0:
        z = (r - r.mean()) / r.std()
        skew, kurt = float((z ** 3).mean()), float((z ** 4).mean())
    else:
        skew, kurt = 0.0, 3.0
    den = math.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr ** 2, 1e-12))
    dsr = nd.cdf((sr - sr0) * math.sqrt(max(T - 1, 1)) / den)
    psr = nd.cdf(sr * math.sqrt(max(T - 1, 1)) / den)
    return {"dsr": round(dsr, 4), "psr0": round(psr, 4), "sharpe": round(sr, 4), "sr0": round(sr0, 4),
            "periods": T, "trials": n, "var_sr_trials": round(var, 4)}


# ------------------------------------------------------------------ the ledger

def _monthly(r: dict) -> list | None:
    out = []
    for y in YEARS:
        m = _yr(r, "main").get(y, {}).get("monthly")
        if not m or len(m) != 12:
            return None
        out += m
    return out


def measure(done: list[dict], champ: dict | None, guarded=None, operates=None) -> dict:
    """Everything from ledger rows (as search.ledger() returns them)."""
    by_id = {r["id"]: r for r in done}
    el = [r for r in by_id.values() if r["eligible"] and (operates is None or operates(r))
          and all(y in _yr(r, "main") for y in YEARS)]
    R = np.array([[float(_yr(r, "main")[y]["return"]) for y in YEARS] for r in el])
    D = np.array([[float(_yr(r, "main")[y]["max_dd"]) for y in YEARS] for r in el])
    out = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "trials": len(done),
           "eligible_distinct": len(el)}
    out["nested"] = nested(done, guarded, "main")
    out["nested_confirm"] = nested([r for r in done if _yr(r, "confirm")], guarded, "both")
    if champ:
        cy, cc = _yr(champ, "main"), _yr(champ, "confirm")
        pick = lambda ys, keep: {y: (float(ys[y]["return"]), float(ys[y]["max_dd"])) for y in keep if y in ys}  # noqa: E731
        out["champion"] = {"id": champ["id"], "score": champ.get("score"),
                           "curve": curve(pick(cy, NESTED_YEARS)), "curve_2022_2025": curve(pick(cy, YEARS)),
                           "confirm_curve": curve(pick(cc, NESTED_YEARS))}
    # PBO: monthly Sharpe when enough rows carry it, else the law on years (coarse)
    if len(el) >= 10:
        yearly = cscv_pbo(R.T, 4, metric=lambda idx: law_vec(R[:, np.sort(idx)], D[:, np.sort(idx)]))
        out["pbo_yearly"] = {**yearly, "basis": "yearly law score, 4 years -> 6 splits (coarse)"}
        out["pbo"], out["pbo_basis"] = yearly["pbo"], "yearly"
    mrows = [(r, m) for r in el if (m := _monthly(r))]
    if len(mrows) >= MIN_MONTHLY_ROWS:
        Mm = np.array([m for _, m in mrows]).T
        monthly = cscv_pbo(Mm, 16)
        out["pbo_monthly"] = {**monthly, "basis": "monthly Sharpe, 16 blocks"}
        out["pbo"], out["pbo_basis"] = monthly["pbo"], "monthly"
    # DSR of the champion: monthly when it and the pool carry months, else annual (coarse)
    if champ and len(el) >= 10:
        cm = _monthly(champ)
        if cm and len(mrows) >= MIN_MONTHLY_ROWS:
            Mm = np.array([m for _, m in mrows])
            srs = Mm.mean(axis=1) / np.maximum(Mm.std(axis=1, ddof=1), 1e-12)
            out["dsr"] = {**deflated_sharpe(cm, srs, len(mrows)), "basis": "monthly"}
        else:
            srs = R.mean(axis=1) / np.maximum(R.std(axis=1, ddof=1), 1e-12)
            cr = [float(_yr(champ, "main")[y]["return"]) for y in YEARS]
            out["dsr"] = {**deflated_sharpe(cr, srs, len(el)), "basis": "annual, 4 years (coarse)"}
    out["gate"] = {"pbo_max": PBO_MAX, "refuses": bool(out.get("pbo") is not None and out["pbo"] > PBO_MAX)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="S10 overfitting measures from the trial ledger")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    from . import search as S
    done = S.ledger()
    champ = S.champion(done)
    doc = measure(done, champ, S.guarded, S.operates)
    if champ:
        doc["champion"]["release"] = next((r["n"] for r in reversed(S.releases()) if r["id"] == champ["id"]), None)
    path = Path(args.out)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    if not args.quiet:
        print(json.dumps(doc, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
