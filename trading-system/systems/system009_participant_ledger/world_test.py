"""Does the world outside crypto pay for itself? The strict-addition test, one family at a time.

Same discipline as V4: identical architecture, identical seed, identical folds, identical
early-stopping rule. The ONLY difference between the arms is which columns they are given, so
any difference in the score is the columns and nothing else.

    MARKET                what the chart knows
    MARKET+LEDGER         plus who holds what and who has run out of cash
    MARKET+WORLD          plus rates, liquidity, the dollar, risk appetite
    MARKET+LEDGER+WORLD   everything

Four arms rather than two, because the interesting question is not "does macro help" - it is
whether the ledger and the world are saying the SAME thing. If MARKET+WORLD matches
MARKET+LEDGER, then the reconstruction's expensive stock variables are a slow proxy for
liquidity conditions that FRED publishes for free, and that would be worth knowing.

Research years only. The sealed window is never loaded into a fit.
"""

from __future__ import annotations

import json
import sys
import time

import numpy as np

from quantlab_catalog.paths import REPO_ROOT
from system009_participant_ledger import features as F
from system009_participant_ledger import pipeline
from system009_participant_ledger.train import FOLDS, RESEARCH_END_EXCLUSIVE, _fit, _hit_rate

OUT = REPO_ROOT / "research" / "system09"


def arms(ds) -> dict[str, np.ndarray]:
    return {
        "market": ds.market,
        "market+ledger": np.hstack([ds.market, ds.ledger]),
        "market+world": np.hstack([ds.market, ds.world]),
        "market+ledger+world": np.hstack([ds.market, ds.ledger, ds.world]),
    }


def run(horizon: int = 30) -> dict:
    """The horizon study says this system's signal lives in weeks, so the addition test is
    asked at the holding period the signal actually has, not at v1's seven days."""
    ctx, traj = pipeline.reconstruct(end="2026-09-14", sealed=True, quiet=True)
    ds = F.build(traj, ctx.funding(), horizon=horizon)
    variants = arms(ds)
    results: dict[str, list[dict]] = {k: [] for k in variants}
    print(f"  horizon {horizon}d   rows {len(ds):,}   "
          f"market {ds.market.shape[1]}  ledger {ds.ledger.shape[1]}  "
          f"world {ds.world.shape[1]}\n")
    print(f"  {'fold':<7s}" + "".join(f"{k:>22s}" for k in variants))
    for year in FOLDS:
        stop = str(int(year) - 1)
        tr = ds.mask(hi=f"{stop}-01-01")
        st = ds.mask(lo=f"{stop}-01-01", hi=f"{year}-01-01")
        va = ds.mask(lo=f"{year}-01-01", hi=f"{int(year) + 1}-01-01") & \
            ds.mask(hi=RESEARCH_END_EXCLUSIVE)
        if tr.sum() < 2000 or st.sum() < 200 or va.sum() < 200:
            continue
        line = f"  {year:<7s}"
        for name, x in variants.items():
            t0 = time.time()
            model, blob, _, _ = _fit(x[tr], ds.y[tr], x[st], ds.y[st])
            import torch
            model.eval()
            with torch.no_grad():
                from system009_participant_ledger.train import DEVICE
                t = torch.tensor((x[va] - blob["mu"]) / blob["sd"], dtype=torch.float32,
                                 device=DEVICE)
                pred = model(t).cpu().numpy().ravel()
            ic = _spearman(pred, ds.y[va])
            results[name].append({"fold": year, "ic": ic, "hit": _hit_rate(pred, ds.y[va]),
                                  "seconds": time.time() - t0})
            line += f"   IC {ic:+.4f}       "
        print(line)

    summary = {}
    for name, rows in results.items():
        ics = [r["ic"] for r in rows if r["ic"] == r["ic"]]
        summary[name] = {"mean_ic": float(np.mean(ics)) if ics else float("nan"),
                         "min_ic": float(np.min(ics)) if ics else float("nan"),
                         "folds_positive": sum(1 for v in ics if v > 0), "n": len(ics)}
    return {"horizon": horizon, "summary": summary, "folds": results}


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 30:
        return float("nan")
    ra = np.argsort(np.argsort(a[m])).astype(float)
    rb = np.argsort(np.argsort(b[m])).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    den = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / den) if den else float("nan")


def main() -> int:
    print("SYSTEM 09 - DOES THE WORLD PAY FOR ITSELF?")
    print("  strict addition, research years only, identical everything but the columns\n")
    out = run()
    s = out["summary"]
    print()
    for name, r in s.items():
        print(f"  {name:<22s} mean IC {r['mean_ic']:+.4f}   worst fold {r['min_ic']:+.4f}"
              f"   positive {r['folds_positive']}/{r['n']}")
    base, both = s["market+ledger"]["mean_ic"], s["market+ledger+world"]["mean_ic"]
    only = s["market+world"]["mean_ic"]
    print(f"\n  the world adds {both - base:+.4f} mean IC on top of the ledger")
    print(f"  the world ALONE scores {only:+.4f} against the ledger's {base:+.4f}"
          + ("  - they may be measuring the same thing"
             if abs(only - base) < 0.02 else ""))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "world_test.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"  written  {OUT / 'world_test.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
