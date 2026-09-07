"""A115: walk every threshold finely, ONE at a time, and print the actual curve.

Operator, 2026-09-07: "focus on the Bayesian calculations. I do not accept that there
is no winner when you try different parameters. Going from 0.75 to 0.72, or to 0.78,
HAS to produce a change - positive or negative - it cannot be that the initial values
we happened to use are the best in the world."

The objection is fair and the honest answer is a measurement, not an argument. Two
distinct claims got conflated in my earlier report and this run separates them:

  1. "Moving a threshold changes nothing."  FALSE, and the 1,668-trial study never
     said it. Every trial produced a different book.
  2. "No move IMPROVES the years it was not fitted on."  That is what was measured,
     and it is a much narrower claim.

What the joint search could NOT show is the SHAPE around the incumbent, because 33
levers moved at once and no single lever's response can be read out of that cloud. So
this walks each lever across a fine grid with everything else pinned at the champion's
value, and prints the curve - the derivative the operator has been asking to see.

Cheap because thresholds do not train: the net is fixed, so each grid point is a
backtest and nothing more. The fit/holdout split is the honest one HERE (unlike for
nets, which train inside their own split - the A103 lesson): a threshold never saw a
bar, so 2024-2025 are genuinely out of sample for it.

Printed per grid point: the fit score (2018-2023), the held-out score (2024-2025), and
the worst drawdown. If a curve is flat the flatness is now visible; if it has a peak
somewhere other than the incumbent, that is a candidate and this run found it.

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a115_sensitivity.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path("research/system06")

# The levers the operator named or that the champion actually uses, each with a grid
# FINE enough to answer his question (0.72 / 0.75 / 0.78 are all on it) and WIDE enough
# to show whether the incumbent sits on a peak, a plateau or a cliff edge.
GRIDS: dict[str, list[float]] = {
    "enter":            [round(0.60 + 0.01 * i, 2) for i in range(31)],   # 0.60..0.90
    "exit_":            [round(0.10 + 0.01 * i, 2) for i in range(26)],   # 0.10..0.35
    "trail_stop":       [round(0.06 + 0.01 * i, 2) for i in range(25)],   # 0.06..0.30
    "stop_loss":        [round(0.03 + 0.01 * i, 2) for i in range(18)],   # 0.03..0.20
    "position_fraction": [round(0.05 + 0.01 * i, 2) for i in range(21)],  # 0.05..0.25
    "breadth_gate":     [round(0.00 + 0.02 * i, 2) for i in range(21)],   # 0.00..0.40
    "regime_deploy":    [round(0.00 + 0.05 * i, 2) for i in range(21)],   # 0.00..1.00
    "meta_margin":      [round(0.000 + 0.002 * i, 3) for i in range(16)], # 0.000..0.030
}


def _nopt():
    spec = importlib.util.spec_from_file_location(
        "nopt", ROOT / "tools" / "numerical_optimization.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    only = sys.argv[1:] or None
    nopt = _nopt()
    ev = nopt.Evaluator(nopt.FIT_YEARS, nopt.HOLDOUT_YEARS, with_enter=True)
    anchor = nopt._champion_point_full(ev.risk, ev.band, list(nopt.SPACE))

    t0 = time.time()
    base = ev.score(dict(anchor))
    print(f"champion baseline: fit {base['fit']:+.4f}  held-out {base['holdout']:+.4f}  "
          f"maxDD {(base['fit_worst_drawdown'] or 0):.1%}   "
          f"({time.time() - t0:.0f}s per evaluation)\n", flush=True)

    out: dict[str, dict] = {}
    for lever, grid in GRIDS.items():
        if only and lever not in only:
            continue
        if lever not in anchor:
            print(f"-- {lever}: not in the champion point, skipped", flush=True)
            continue
        here = float(anchor[lever])
        print("=" * 72)
        print(f"{lever}   champion value {here}   {len(grid)} points")
        print("=" * 72, flush=True)
        rows = []
        for v in grid:
            point = dict(anchor)
            point[lever] = type(here)(v) if not isinstance(here, bool) else v
            r = ev.score(point)
            mark = "  <-- champion" if abs(v - here) < 1e-9 else ""
            flag = "  INERT" if r["inert"] else ""
            print(f"  {lever:18} {v:>7}   fit {r['fit']:+.4f}   held-out {r['holdout']:+.4f}"
                  f"   maxDD {(r['fit_worst_drawdown'] or 0):5.1%}   trades {r['trades']:>5}"
                  f"{mark}{flag}", flush=True)
            rows.append({"value": v, "fit": r["fit"], "holdout": r["holdout"],
                         "worst_drawdown": r["fit_worst_drawdown"],
                         "trades": r["trades"], "inert": bool(r["inert"])})
        live = [x for x in rows if not x["inert"]]
        if live:
            bf = max(live, key=lambda x: x["fit"])
            bh = max(live, key=lambda x: x["holdout"])
            span_f = max(x["fit"] for x in live) - min(x["fit"] for x in live)
            span_h = max(x["holdout"] for x in live) - min(x["holdout"] for x in live)
            print(f"\n  best on FIT      {bf['value']} ({bf['fit']:+.4f})   "
                  f"champion {here}   range across the grid {span_f:.4f}")
            print(f"  best on HELD-OUT {bh['value']} ({bh['holdout']:+.4f})   "
                  f"range {span_h:.4f}", flush=True)
            out[lever] = {"champion": here, "rows": rows,
                          "best_fit": bf, "best_holdout": bh,
                          "fit_range": span_f, "holdout_range": span_h}
        else:
            out[lever] = {"champion": here, "rows": rows, "note": "every point inert"}

    dest = ROOT / "rnd" / f"a115_sensitivity_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    dest.write_text(json.dumps({
        "id": "A115", "at": datetime.now(timezone.utc).isoformat(),
        "baseline": {"fit": base["fit"], "holdout": base["holdout"]},
        "fit_years": list(nopt.FIT_YEARS), "holdout_years": list(nopt.HOLDOUT_YEARS),
        "method": "one lever at a time, everything else pinned at the champion; the net "
                  "is fixed, so a grid point is a backtest and nothing more",
        "levers": out,
        "minutes": round((time.time() - t0) / 60, 1),
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {dest}   ({(time.time() - t0) / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
