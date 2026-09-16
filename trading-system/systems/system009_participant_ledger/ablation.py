"""WHAT IS EACH PIECE WORTH? One arm per block, and a year nobody selects on.

Every previous measurement in this system priced a bundle. This one prices the parts, because
the operator is now paying for four separate ideas - a relative target, the cycle state, the
world by region, and participant tiers - and "the bundle went up" is not an answer to "which
of them should survive".

THE TARGET IS THE FIRST ARM, and it is not a feature.
`absolute` is the raw forward return, whose mean across 2017-2025 is large and positive. A
model with weak inputs minimises its loss by predicting that drift, which is exactly what
happened: a rise forecast on 250 days out of 250. `relative` subtracts the universe's own mean
that day, so the drift cancels and a constant forecast scores zero. Any information
coefficient measured on the absolute target is contaminated; the two are reported side by side
here so the size of the contamination is visible rather than argued about.

THE HELD-BACK YEAR
Folds 2021-2024 choose; 2025 is scored and never selected on. The sealed 2026 window is not
loaded, not read and not mentioned in the output. That is what makes a comparison between
these arms meaningful at all - without it, more features always look better.
"""

from __future__ import annotations

import json
import sys
import time

import numpy as np

from quantlab_catalog.paths import REPO_ROOT
from system009_participant_ledger import features as F
from system009_participant_ledger import pipeline
from system009_participant_ledger.train import DEVICE, _fit

OUT = REPO_ROOT / "research" / "system09"
HORIZON = 30
PICK = ("2021", "2022", "2023", "2024")
CHECK = "2025"


def _predict(model, blob, x):
    import torch
    model.eval()
    with torch.no_grad():
        t = torch.tensor((x - blob["mu"]) / blob["sd"], dtype=torch.float32, device=DEVICE)
        return model(t).cpu().numpy().ravel()


def _ic(a, b) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 30:
        return float("nan")
    ra = np.argsort(np.argsort(a[m])).astype(float)
    rb = np.argsort(np.argsort(b[m])).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    den = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / den) if den else float("nan")


def arms(ds) -> dict[str, np.ndarray]:
    """The market block is split so the cycle-state columns can be priced on their own."""
    base = ds.market[:, :7]
    cycle = ds.market[:, 7:]
    return {
        "chart only": base,
        "chart+cycle": np.hstack([base, cycle]),
        "chart+cycle+ledger": np.hstack([base, cycle, ds.ledger]),
        "chart+cycle+world": np.hstack([base, cycle, ds.world]),
        "everything": np.hstack([base, cycle, ds.ledger, ds.world]),
    }


def evaluate(ds, name: str, x: np.ndarray) -> dict:
    per_year, preds = {}, np.full(len(ds), np.nan)
    for year in (*PICK, CHECK):
        stop = str(int(year) - 1)
        tr = ds.mask(hi=f"{stop}-01-01")
        st = ds.mask(lo=f"{stop}-01-01", hi=f"{year}-01-01")
        va = ds.mask(lo=f"{year}-01-01", hi=f"{int(year) + 1}-01-01")
        if tr.sum() < 2000 or st.sum() < 200 or va.sum() < 200:
            continue
        model, blob, _, _ = _fit(x[tr], ds.y[tr], x[st], ds.y[st])
        pred = _predict(model, blob, x[va])
        preds[va] = pred
        per_year[year] = {"ic": _ic(pred, ds.y[va]),
                          "hit": float(((pred > 0) == (ds.y[va] > 0)).mean()),
                          "spread": float(np.std(pred))}
    pick = [per_year[y]["ic"] for y in PICK if y in per_year]
    return {"arm": name, "per_year": per_year,
            "pick_mean_ic": float(np.mean(pick)) if pick else float("nan"),
            "pick_worst_ic": float(np.min(pick)) if pick else float("nan"),
            "check_ic": per_year.get(CHECK, {}).get("ic", float("nan")),
            "check_hit": per_year.get(CHECK, {}).get("hit", float("nan")),
            "pred_spread": float(np.nanstd(preds))}


def main() -> int:
    print("SYSTEM 09 - ABLATION: what each block is worth, and what the target was hiding")
    print(f"  horizon {HORIZON}d   selection {PICK[0]}-{PICK[-1]}   held back {CHECK}   "
          "2026 not loaded\n")
    ctx, traj = pipeline.reconstruct(end="2025-12-31", sealed=False, quiet=True, cache=True)
    funding = ctx.funding()

    results = []
    for target in ("absolute", "relative"):
        ds = F.build(traj, funding, horizon=HORIZON, target=target)
        drift = float(np.mean(ds.y_abs))
        print(f"  TARGET '{target}'   rows {len(ds):,}   mean label "
              f"{float(np.mean(ds.y)):+.4f}   (the era's drift is {drift:+.4f})")
        print(f"    {'arm':<22s}{'pick mean':>11s}{'pick worst':>12s}"
              f"{'held-back ' + CHECK:>16s}{'hit':>8s}")
        for name, x in arms(ds).items():
            t0 = time.time()
            r = evaluate(ds, name, x)
            r["target"] = target
            results.append(r)
            print(f"    {name:<22s}{r['pick_mean_ic']:>+11.4f}{r['pick_worst_ic']:>+12.4f}"
                  f"{r['check_ic']:>+16.4f}{r['check_hit']:>8.3f}"
                  f"   {time.time() - t0:4.0f}s")
        print()

    best = max((r for r in results if r["target"] == "relative"),
               key=lambda r: (r["check_ic"] if r["check_ic"] == r["check_ic"] else -9))
    print(f"  BEST on the held-back year, relative target: {best['arm']}"
          f"   IC {best['check_ic']:+.4f}   hit {best['check_hit']:.3f}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ablation_report.json").write_text(
        json.dumps({"horizon": HORIZON, "pick": list(PICK), "check": CHECK,
                    "results": results, "best_relative": best}, indent=1), encoding="utf-8")
    print(f"  written  {OUT / 'ablation_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
