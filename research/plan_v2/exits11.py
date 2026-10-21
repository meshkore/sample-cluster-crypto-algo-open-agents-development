"""Exits 11 - one problem at a time (operator 2026-10-21): the EXITS of System 11's book.

Price rules never tested on System 11 (Rocket 11 only had indicator validators):
    stop       sell when the close is X% below the entry price
    trail      sell when the close is X% below the highest close since entry
    take       sell when the close is X% above the entry price
    time       sell after N days held
After a rule fires, the coin is not bought back until the model itself has dropped it once (no churn).

Each family is tested alone, walk-forward: for year N the value is chosen on 2020..N-1 (the law: recency-weighted
mean yearly return + 3 points per positive year), then read on N. Worse of two seed sets. Costs charged.
Book: the System 11 law book (rocket11 base cache), unscaled and at the paper scale x0.45.

    python research/plan_v2/exits11.py      -> exits11/{results.json, REPORT.md}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

import bayes11 as B
import history_v2 as H
import phase3_select as P3
import rocket11 as R

OUT = B.HERE / "exits11"
FAMILIES = {"stop": (0.05, 0.08, 0.10, 0.15, 0.20, 0.25), "trail": (0.05, 0.08, 0.10, 0.15, 0.20, 0.25, 0.30),
            "take": (0.10, 0.20, 0.30, 0.50, 1.0), "time": (3, 7, 14, 30, 60)}
FOLDS = tuple(range(2021, 2027))


def apply_exit(W: np.ndarray, c: np.ndarray, fam: str, x: float) -> np.ndarray:
    out = W.copy()
    T, S = W.shape
    held = np.zeros(S, bool)
    blocked = np.zeros(S, bool)
    ent = np.full(S, np.nan)
    peak = np.full(S, np.nan)
    age = np.zeros(S)
    for i in range(T):
        want = W[i] > 1e-9
        blocked &= want                                   # the model dropped it: may be bought again later
        px = c[i]
        new = want & ~held & ~blocked
        ent[new], peak[new], age[new] = px[new], px[new], 0
        hold = want & ~blocked
        peak = np.where(hold, np.fmax(peak, px), peak)
        age = np.where(hold, age + 1, 0)
        with np.errstate(invalid="ignore"):
            if fam == "stop":
                fire = px < ent * (1 - x)
            elif fam == "trail":
                fire = px < peak * (1 - x)
            elif fam == "take":
                fire = px > ent * (1 + x)
            else:
                fire = age > x * 6
        fire &= hold & np.isfinite(px)
        blocked |= fire
        hold &= ~fire
        out[i] = np.where(hold, W[i], 0.0)
        held = hold
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cut = np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None), "ns").astype("int64")
    w = H.world(R.SPEC["cap"], int(cut))
    z = np.load(R.CACHE / "base.npz")
    T, S = w.P4["close"].shape
    c = w.P4["close"]
    dy = H.to_daily(w, np.zeros(T))[1]
    yrs = H.BOOK_YEARS
    res = {}
    for scale in (1.0, 0.45):
        books = {}
        for ss in ("s1", "s2"):
            Wb = z[f"{ss}_W"].astype(float)
            Wb = np.r_[Wb, np.zeros((T - Wb.shape[0], S))] * scale
            books[ss] = Wb
        daily = lambda W: H.to_daily(w, H.bar_returns(w, W, P3.HALF_COST, None)[0])[0]  # noqa: E731
        base = {ss: daily(books[ss]) for ss in books}
        variants = {("none", 0): base}
        for fam, vals in FAMILIES.items():
            for x in vals:
                variants[(fam, x)] = {ss: daily(apply_exit(books[ss], c, fam, x)) for ss in books}
                print(f"scale {scale} {fam} {x} done", flush=True)
        table = {}
        for (fam, x), dd in variants.items():
            yr = {ss: B.yearly(d, dy, yrs) for ss, d in dd.items()}
            table[f"{fam}:{x}"] = {"years": {y: round(min(yr[ss][y] for ss in yr), 4) for y in yrs},
                                   "dd_2020_25": round(max(B.max_dd(d[np.isin(dy, H.RESEARCH_YEARS)]) for d in dd.values()), 4)}
        wf = {}
        for fam, vals in FAMILIES.items():
            picks = {}
            for N in FOLDS:
                train = tuple(range(2020, N))
                cand = [("none", 0)] + [(fam, x) for x in vals]
                best = max(cand, key=lambda k: min(B.objective_value(variants[k][ss], dy, train)[0] for ss in variants[k]))
                picks[N] = {"pick": f"{best[0]}:{best[1]}", "ret": table[f"{best[0]}:{best[1]}"]["years"][N]}
            wf[fam] = picks
        res[str(scale)] = {"table": table, "walk_forward": wf}
    doc = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "results": res}
    (OUT / "results.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    L = ["# Exits 11 - price exits on the System 11 law book (one family at a time)", "",
         "Walk-forward: each year uses the value chosen on the years before it ('none' allowed). Worse of two seed sets. Costs charged.", ""]
    for scale, r in res.items():
        L += [f"## Book at x{scale}", "", "| exit family | " + " | ".join(str(y) for y in FOLDS) + " | sum |", "|---|" + "---|" * (len(FOLDS) + 1)]
        bt = r["table"]["none:0"]["years"]
        L.append("| none (today) | " + " | ".join(f"{bt[y]:+.1%}" for y in FOLDS) + f" | {sum(bt[y] for y in FOLDS):+.0%} |")
        for fam, picks in r["walk_forward"].items():
            L.append(f"| {fam} | " + " | ".join(f"{picks[y]['ret']:+.1%} <small>{picks[y]['pick'].split(':')[1] if picks[y]['pick'] != 'none:0' else '-'}</small>" for y in FOLDS)
                     + f" | {sum(picks[y]['ret'] for y in FOLDS):+.0%} |")
        L += ["", "Every fixed value (no walk-forward), 2020-2026 per year:", "", "| rule | " + " | ".join(str(y) for y in yrs) + " | DD 2020-25 |",
              "|---|" + "---|" * (len(yrs) + 1)]
        for k, v in r["table"].items():
            L.append(f"| {k} | " + " | ".join(f"{v['years'][y]:+.0%}" for y in yrs) + f" | {v['dd_2020_25']:.0%} |")
        L.append("")
    (OUT / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:20]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
