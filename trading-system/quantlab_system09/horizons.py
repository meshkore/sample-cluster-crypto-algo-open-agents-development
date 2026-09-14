"""WHICH HOLDING PERIOD IS THIS MODEL ACTUALLY GOOD AT?

The operator's observation, and it is the right one: a reconstruction of who holds what and
who has run out of cash is a statement about pressure that builds over weeks, not about the
next few hours. Asking it for a seven-day return because seven was the first number anyone
wrote down is not a design decision, it is an accident that survived.

So this module sweeps the horizon - one day to a quarter - and reports, for each, the model's
rank correlation and directional accuracy in walk-forward folds. Everything here is measured
on the RESEARCH YEARS ONLY. The sealed window is not touched, is not loaded, and cannot be:
`mask(hi=RESEARCH_END)` is applied before a single row reaches a fit.

That discipline is the entire point of the module. Choosing a holding period by trying each
one on 2026 would produce a number that means nothing, and this laboratory has paid for that
lesson four times already - see `docs/RESULTS.md`, where a single window has now been read
four times and the readings disagree by thirty-four points.

Run it, read the table, and let it decide the shape of the trading policy:

    python -m quantlab_system09.horizons
"""

from __future__ import annotations

import json
import sys
import time

import numpy as np

from quantlab_catalog.paths import indicator_dir
from quantlab_system09 import features as F
from quantlab_system09 import pipeline
from quantlab_system09.train import FOLDS, RESEARCH_END_EXCLUSIVE, _fit, _hit_rate

#: One day to a quarter. The short end is where a venue's tape lives and where the cost of
#: 0.30% a round trip eats everything; the long end is where a stock - who is underwater, who
#: has no cash left - has time to actually express itself in a price.
HORIZONS = (1, 3, 7, 14, 30, 60, 90)

OUT = indicator_dir("system09")


def study(horizons=HORIZONS) -> list[dict]:
    ctx, traj = pipeline.reconstruct(end="2026-09-14", sealed=True, quiet=True)
    funding = ctx.funding()
    rows = []
    print(f"  {'horizon':>8s} {'rows':>8s}   {'mean IC':>9s} {'mean hit':>9s} "
          f"{'folds +':>8s}   {'IC per fold'}")
    for h in horizons:
        t0 = time.time()
        ds = F.build(traj, funding, horizon=h)
        research = ds.mask(hi=RESEARCH_END_EXCLUSIVE)
        x = np.hstack([ds.market, ds.ledger, ds.world])
        ics, hits = [], []
        for year in FOLDS:
            tr = ds.mask(hi=f"{year}-01-01")
            va = ds.mask(lo=f"{year}-01-01", hi=f"{int(year) + 1}-01-01") & research
            if tr.sum() < 2000 or va.sum() < 200:
                continue
            _, _, ic, pred = _fit(x[tr], ds.y[tr], x[va], ds.y[va])
            ics.append(ic)
            hits.append(_hit_rate(pred, ds.y[va]))
        if not ics:
            continue
        row = {"horizon": h, "rows": int(research.sum()),
               "mean_ic": float(np.mean(ics)), "mean_hit": float(np.mean(hits)),
               "min_ic": float(np.min(ics)), "max_ic": float(np.max(ics)),
               "folds_positive": int(sum(1 for v in ics if v > 0)), "n_folds": len(ics),
               "ic_per_fold": [float(v) for v in ics], "seconds": time.time() - t0}
        rows.append(row)
        print(f"  {h:>6d}d  {row['rows']:>8,d}   {row['mean_ic']:>+9.4f} "
              f"{row['mean_hit']:>9.4f} {row['folds_positive']:>5d}/{row['n_folds']:<3d}  "
              + " ".join(f"{v:+.3f}" for v in ics))
    return rows


def verdict(rows: list[dict]) -> dict:
    """Pick by the WORST fold, not by the mean.

    A horizon whose mean is high because one fold was extraordinary is a horizon that will
    disappoint out of sample, and this laboratory has the receipts: the 7-day model carried a
    mean IC of +0.14 into a sealed window that returned +0.00. The candidate that earns a
    trading policy is the one whose worst year is still positive.
    """
    if not rows:
        return {}
    safe = [r for r in rows if r["min_ic"] > 0]
    pick = max(safe or rows, key=lambda r: (r["min_ic"], r["mean_ic"]))
    return {"horizon": pick["horizon"], "mean_ic": pick["mean_ic"],
            "min_ic": pick["min_ic"], "mean_hit": pick["mean_hit"],
            "every_fold_positive": bool(safe), "chosen_on": "worst fold, research years only"}


def main() -> int:
    print("SYSTEM 09 - HORIZON STUDY: what holding period is this model good at?")
    print("  research years only - the sealed window is never loaded into a fit\n")
    rows = study()
    v = verdict(rows)
    if not v:
        print("\n  no horizon produced a usable fold")
        return 1
    print(f"\n  CHOSEN HORIZON {v['horizon']} days"
          f"   mean IC {v['mean_ic']:+.4f}   worst fold {v['min_ic']:+.4f}"
          f"   directional {v['mean_hit']:.4f}")
    if not v["every_fold_positive"]:
        print("  WARNING: no horizon was positive in every research fold. The signal this "
              "system carries is not stable across years at ANY holding period, and a "
              "trading policy built on it is a bet on the average year.")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "horizon_study.json").write_text(
        json.dumps({"horizons": rows, "verdict": v}, indent=1), encoding="utf-8")
    print(f"  written  {OUT / 'horizon_study.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
