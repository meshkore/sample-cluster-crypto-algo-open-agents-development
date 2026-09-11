"""R03: the mirror bucket R02 surfaced - and this is POST-HOC, which changes what it means.

R02 pre-registered H1-R (absorbed flow is informative) and killed it: the impact residual
adds +0.08 bps at 60m to what flow alone gives, on 74,181 clustered events. That verdict
stands and nothing here revises it.

What R02's 2D table then showed, which nobody predicted:

     flow dec       R q1       R q2       R q3       R q4       R q5
           10        0.4       -1.9       -1.2       -2.8       -5.9
            9        0.4       -1.5       -1.5       -2.7       -3.0
            8        0.2        0.0       -1.4       -1.4       -2.6

Monotone in the residual, and steepening with the flow decile. It is the MIRROR of the
hypothesis we came to test. Not "flow absorbed by hidden liquidity is informative", but
"flow that moves price MORE than that flow normally moves it gives the move back".
Over-extension, not absorption.

WHY THIS FILE IS SEPARATE FROM R02, AND WHY THAT MATTERS

I found this by reading a table I generated to answer a different question. That is the
single most reliable way this laboratory has fooled itself - it is how the deep-field net,
the 5-seed ensemble, recency weighting and the reference-market features all won their way
to a sealed reading and lost it. A pattern found in a table is a HYPOTHESIS, not a result,
and it has not passed anything. Folding it into R02 would let it inherit R02's
pre-registration, which it did not earn. Hence a second file that says so in its name.

WHAT THIS CAN AND CANNOT DO

It cannot confirm the effect - no post-hoc test can, and the honest resolution is an
out-of-sample reading nobody has spent yet. What it CAN do is kill it cheaply, and that
is the only reason to run it now. Three ways it dies, all registered before the numbers:

  1. MAGNITUDE. If |D - B| at 60m is under 5 bps it is not worth another hour. The round
     trip is 30 bps. R02's table suggests about 6, so this is a genuinely live test and
     not one I have rigged to pass.

  2. CONSISTENCY. The operator's own law for this laboratory is profit in EVERY calendar
     year. If the gradient is a 2021 artefact - one manic year supplying the whole effect
     - it is not a market structure, it is a memory of a bull market. Registered here: it
     must hold the same SIGN in at least 7 of the 9 years. A structural feature of how
     price responds to aggression should not care which year it is.

  3. MONOTONICITY. The gradient must be monotone in the residual, not a single extreme
     quintile doing all the work. A structure that only exists in the tail is
     indistinguishable from the tail being where the outliers are.

Even if all three pass, the effect is ~6 bps against a 30 bps round trip. It is not a
strategy and I will not describe it as one. It would be a REGIME FEATURE - a reason to
stand aside or size down after an over-extended move - and that is a different and much
weaker claim than an edge.

Run from the repo root:
    PYTHONPATH=trading-system python research/system08/tools/r03_overshoot_posthoc.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r02_h1r_screen import (CLUSTER_BARS, DECIDING_H, FLOW_P, HORIZONS,  # noqa: E402
                            bps, cluster, day_clustered, per_symbol)

OUT = Path("research/system08/rnd")
OVERSHOOT_P = 0.80        # "moved MORE than expected" = top quintile of the residual
KILL_BPS = 5.0
COST_BPS = 30.0
MIN_YEARS_SAME_SIGN = 7


def by_year(rows: list[dict], key: str) -> dict[int, tuple[float, int]]:
    out = {}
    grouped = defaultdict(list)
    for r in rows:
        grouped[r["year"]].append(r)
    for y in sorted(grouped):
        m, _, _ = day_clustered(grouped[y], key)
        out[y] = (bps(m), len(grouped[y]))
    return out


def main() -> int:
    import quantlab_catalog as cat

    symbols = cat.load_universe()
    print(f"loading {len(symbols)} symbols at 15m (research era only) ...", flush=True)
    research = cat.research(symbols)

    everything: list[dict] = []
    for sym in symbols:
        rows = per_symbol(research.get(sym) or [])
        if not rows:
            continue
        for r in rows:
            r["sym"] = sym
        everything.extend(rows)
    if not everything:
        sys.exit("no usable bars")

    A = everything
    B = [r for r in A if r["pf"] >= FLOW_P]
    D_raw = [r for r in B if r["pr"] >= OVERSHOOT_P]

    def clustered(rows):
        per = defaultdict(list)
        for r in rows:
            per[r["sym"]].append(r)
        out = []
        for sym in sorted(per):
            out.extend(cluster(sorted(per[sym], key=lambda r: r["i"])))
        return out

    B_cl, D = clustered(B), clustered(D_raw)

    print("\n" + "=" * 84)
    print("HOW MUCH EVIDENCE - before any return")
    print("=" * 84)
    print(f"  B  high flow (>= p{FLOW_P * 100:.0f})               "
          f"{len(B_cl):,} clustered events")
    print(f"  D  + overshoot (resid >= p{OVERSHOOT_P * 100:.0f})    "
          f"{len(D):,} clustered events over "
          f"{len({r['day'] for r in D}):,} distinct days")

    print("\n" + "=" * 84)
    print("TEST 1 - MAGNITUDE.  forward return signed by the flow, in bps")
    print("=" * 84)
    print(f"{'horizon':>9} {'B high flow':>13} {'D overshoot':>13} {'D - B':>10} "
          f"{'se(D)':>9} {'t(D-B)':>8}")
    table = {}
    for h in HORIZONS:
        k = f"y{h}"
        mb, seb, _ = day_clustered(B_cl, k)
        md, sed, nd = day_clustered(D, k)
        diff = md - mb
        se_d = float(np.sqrt(sed ** 2 + seb ** 2))
        t = diff / se_d if se_d > 0 else float("nan")
        table[h] = {"B": bps(mb), "D": bps(md), "diff": bps(diff), "t": t, "days": nd}
        print(f"{h * 15:>7}m {bps(mb):>13.2f} {bps(md):>13.2f} {bps(diff):>10.2f} "
              f"{bps(sed):>9.2f} {t:>8.2f}")

    dec = table[DECIDING_H]
    mag_ok = abs(dec["diff"]) >= KILL_BPS

    print("\n" + "=" * 84)
    print(f"TEST 2 - CONSISTENCY.  D at {DECIDING_H * 15}m, per calendar year")
    print("=" * 84)
    yr = by_year(D, f"y{DECIDING_H}")
    yb = by_year(B_cl, f"y{DECIDING_H}")
    print(f"{'year':>6} {'D bps':>10} {'B bps':>10} {'D-B bps':>10} {'events':>9}")
    signs = []
    for y in sorted(yr):
        d_bps, n = yr[y]
        b_bps = yb.get(y, (float('nan'), 0))[0]
        gap = d_bps - b_bps
        signs.append(np.sign(gap))
        print(f"{y:>6} {d_bps:>10.2f} {b_bps:>10.2f} {gap:>10.2f} {n:>9,}")
    dom = max(signs.count(-1), signs.count(1)) if signs else 0
    cons_ok = dom >= MIN_YEARS_SAME_SIGN
    print(f"\n  same sign in {dom} of {len(signs)} years "
          f"(registered requirement: >= {MIN_YEARS_SAME_SIGN})")

    print("\n" + "=" * 84)
    print(f"TEST 3 - MONOTONICITY.  top flow decile only, {DECIDING_H * 15}m, by residual "
          f"quintile")
    print("=" * 84)
    means = []
    for q in range(5):
        sel = [r for r in B if min(4, int(r["pr"] * 5)) == q]
        m, _, _ = day_clustered(sel, f"y{DECIDING_H}")
        means.append(bps(m))
        print(f"  residual q{q + 1}  {bps(m):>8.2f} bps   ({len(sel):,} bars)")
    steps = np.diff(means)
    mono_ok = bool(np.all(steps <= 0.0) or np.all(steps >= 0.0))
    print(f"\n  monotone: {mono_ok}  (steps: "
          f"{', '.join(f'{s:+.2f}' for s in steps)})")

    passed = [mag_ok, cons_ok, mono_ok]
    if all(passed):
        verdict = (
            f"SURVIVES ALL THREE. D - B = {dec['diff']:+.2f} bps at {DECIDING_H * 15}m, "
            f"same sign in {dom}/{len(signs)} years, monotone in the residual. This is "
            f"still POST-HOC and still ~{abs(dec['diff']):.0f} bps against a "
            f"{COST_BPS:.0f} bp round trip: not an edge, a candidate REGIME FEATURE. "
            f"The honest next step is a pre-registered out-of-sample test, not a "
            f"strategy.")
    else:
        failed = [n for n, ok in zip(("magnitude", "consistency", "monotonicity"),
                                     passed) if not ok]
        verdict = (
            f"REFUSED on {', '.join(failed)}. D - B = {dec['diff']:+.2f} bps at "
            f"{DECIDING_H * 15}m, same sign in {dom}/{len(signs)} years, monotone="
            f"{mono_ok}. The gradient in R02's table does not survive its own follow-up. "
            f"Recorded and closed - this is why a pattern found in a table is not a "
            f"result.")

    print("\n" + "=" * 84)
    print("VERDICT:", verdict)
    print("=" * 84)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"r03_overshoot_posthoc_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    path.write_text(json.dumps({
        "id": "R03", "at": datetime.now(timezone.utc).isoformat(),
        "post_hoc": True,
        "found_by": "reading R02's flow x residual table, not by prediction",
        "events_D": len(D), "events_B": len(B_cl),
        "by_horizon_bps": table,
        "per_year": {str(y): {"D_bps": v[0], "events": v[1]} for y, v in yr.items()},
        "quintile_means_bps": means,
        "tests": {"magnitude": mag_ok, "consistency": cons_ok,
                  "monotonicity": mono_ok},
        "verdict": verdict,
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
