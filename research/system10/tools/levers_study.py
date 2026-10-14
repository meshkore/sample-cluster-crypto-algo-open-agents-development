"""Book levers on the pinned release, year by year (2026-10-14).

Reuses health_study's cached inputs (rnd/health_inputs.npz: release 31's walk-forward
signals per year). Each lever is booked on release 31's cfg +- the lever over 2020-2025;
values are chosen on <= 2025 only; `forward` reads 2026 once for the chosen settings.

    R=$(pwd -W); PYTHONPATH="$R/trading-system;$R/trading-system/systems;$R/research/system10/tools" \
        python research/system10/tools/levers_study.py study
    ... levers_study.py forward --settings <name> ...
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
for sub in ("trading-system", "trading-system/systems", "research/system10/tools"):
    if str(REPO / sub) not in sys.path:
        sys.path.insert(0, str(REPO / sub))

import health_study as HS  # noqa: E402

OUT = REPO / "research/system10/rnd/levers_study.json"
YEARS = (2020, 2021, 2022, 2023, 2024, 2025)
JUDGED = (2022, 2023, 2024, 2025)          # the search's own test years
_CTX: dict = {}


def _ctx():
    if not _CTX:
        per, meta = HS.load_inputs()
        _CTX.update(per=per, meta=meta)
    return _CTX


def book(N: int, extra: dict | None) -> dict:
    import conditions as C
    from system010_conditioned_rl import search as S
    c = _ctx()
    per, meta = c["per"], c["meta"]
    cfg = {**meta["cfg"], **(extra or {})}
    pN = {s: {"ns": d["ns"], "close": d["close"], "prob": d["prob"], "year": d["year"]} for s, d in per.items()}
    pick = lambda f: {s: d[f"{f}{N}"] for s, d in per.items()}  # noqa: E731
    size = {s: d["size"] for s, d in per.items()} if cfg.get("size_down", 1.0) < 1.0 else None
    old = C.HORIZON
    C.HORIZON = cfg["horizon"]
    try:
        r = C.book_year(pN, pick("enter"), N, meta["band"], meta["risk"], keep=pick("keep"), size=size,
                        keep_min_hold=meta["exit_min_hold"], strength=pick("strength"), **S.mm_kwargs(cfg))
    finally:
        C.HORIZON = old
    return {k: r[k] for k in ("return", "max_dd", "trades", "win_rate")}


def settings() -> dict:
    out: dict = {"baseline": {}}
    for n in (1, 2, 3):
        for rho in (0.6, 0.7, 0.8, 0.9):
            out[f"corr {n}@{rho:g}"] = {"corr_cap": n, "corr_rho": rho}
    for days in (10, 20, 30, 60):
        for cut in (0.5, 0.75):
            out[f"eq {days}d x{cut:g}"] = {"eq_filter": days, "eq_cut": cut}
    for e in (0.004, 0.005, 0.0075, 0.01, 0.015):
        out[f"edge {e:g}"] = {"min_edge": e}
    for tp in (0.03, 0.05, 0.08, 0.12, 0.2):
        out[f"tp {tp:g}"] = {"take_profit": tp}
    for be in (0.02, 0.03, 0.05, 0.08):
        out[f"be {be:g}"] = {"breakeven": be}
    for k in (3, 5, 7):
        for days in (30, 60):
            for mode, (mi, mo) in (("only", (1.0, 0.0)), ("boost", (1.5, 1.0)), ("tilt", (1.25, 0.5))):
                out[f"mom {mode} {k}/{days}d"] = {"mom_rank": k, "mom_days": days, "mom_in": mi, "mom_out": mo}
    # Round 2: is the boost momentum, or just more exposure? (all coins x the same boost)
    for mi in (1.25, 1.5, 2.0):
        out[f"all x{mi:g}"] = {"mom_rank": 99, "mom_in": mi, "mom_out": 1.0}
        for k in (3, 5):
            for days in (60, 90):
                out[f"mom x{mi:g} {k}/{days}d"] = {"mom_rank": k, "mom_days": days, "mom_in": mi, "mom_out": 1.0}
    return out


def summarise(rows: dict, years) -> dict:
    rets = [rows[y]["return"] for y in years]
    dd = max(rows[y]["max_dd"] for y in years)
    cagr = float(np.prod([1 + r for r in rets]) ** (1 / len(rets)) - 1)
    tr = sum(rows[y]["trades"] for y in years)
    wr = sum((rows[y]["win_rate"] or 0) * rows[y]["trades"] for y in years) / max(tr, 1)
    return {"cagr": round(cagr, 4), "worst_year": round(min(rets), 4), "max_dd": round(dd, 4),
            "score": round(min(rets) + 0.1 * cagr, 4), "win_rate": round(wr, 4), "trades": tr,
            "q": round(float(np.sign(cagr) * cagr * cagr / max(dd, 0.02)), 4), "dd_ok": bool(dd <= 0.25)}


def run(sets: dict, years=YEARS) -> dict:
    res: dict = {}
    t0 = time.time()
    for i, (k, v) in enumerate(sets.items(), 1):
        res[k] = {N: book(N, v) for N in years}
        s = summarise(res[k], JUDGED)
        print(f"[{(time.time() - t0) / 60:5.1f}m {i}/{len(sets)}] {k:<16}"
              + "".join(f" {res[k][y]['return']:+6.1%}/{res[k][y]['max_dd']:4.1%}/{res[k][y]['win_rate'] or 0:.2f}"
                        for y in years)
              + f" | 22-25 score {s['score']:+.4f} cagr {s['cagr']:+.1%} dd {s['max_dd']:.1%} wr {s['win_rate']:.3f}",
              flush=True)
    return res


def study(only: list[str]) -> None:
    sets = settings()
    if only:
        sets = {k: v for k, v in sets.items() if k == "baseline" or any(k.startswith(p) for p in only)}
    old = json.loads(OUT.read_text()) if OUT.is_file() else {"per_year": {}, "settings": {}}
    res = run(sets)
    old["per_year"].update({k: {str(y): r for y, r in v.items()} for k, v in res.items()})
    old["settings"].update(sets)
    per_year = {k: {int(y): r for y, r in v.items()} for k, v in old["per_year"].items()}
    summ = {k: {"judged": summarise(v, JUDGED), "all": summarise(v, YEARS)} for k, v in per_year.items()}
    ok = {k: s["judged"] for k, s in summ.items() if s["judged"]["dd_ok"]}
    old["summary"] = summ
    old["optimal"] = max(ok, key=lambda k: (ok[k]["score"], ok[k]["q"]))
    old["max_profit"] = max(ok, key=lambda k: ok[k]["cagr"])
    OUT.write_text(json.dumps(old, indent=1, default=str), encoding="utf-8")
    print(f"\noptimal (score 22-25, DD<=25%): {old['optimal']}  max profit: {old['max_profit']}")


def combos(names: list[str]) -> None:
    """Book combinations given as name+name (each from settings())."""
    base = settings()
    sets = {"baseline": {}}
    for n in names:
        d: dict = {}
        for part in n.split("+"):
            d.update(base[part])
        sets[n] = d
    old = json.loads(OUT.read_text()) if OUT.is_file() else {"per_year": {}, "settings": {}}
    res = run(sets)
    old["per_year"].update({k: {str(y): r for y, r in v.items()} for k, v in res.items()})
    old["settings"].update(sets)
    OUT.write_text(json.dumps(old, indent=1, default=str), encoding="utf-8")


def forward(names: list[str]) -> None:
    """The one 2026 read, for settings already chosen on <= 2025."""
    base = settings()
    for n in ["baseline"] + names:
        d: dict = {}
        for part in n.split("+"):
            d.update(base.get(part, {}))
        r = book(2026, d)
        print(f"2026 {n:<28} {r['return']:+.2%}  dd {r['max_dd']:.1%}  trades {r['trades']}  "
              f"win {r['win_rate'] or 0:.3f}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stage", choices=("study", "combos", "forward"))
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--settings", nargs="*", default=[])
    a = ap.parse_args()
    if a.stage == "study":
        study(a.only)
    elif a.stage == "combos":
        combos(a.settings)
    else:
        forward(a.settings)
