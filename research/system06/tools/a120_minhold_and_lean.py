"""A120: the min_hold response curve, the lean champion, and A119's two broken arms.

A119 found three things and got two arms wrong.

WHAT IT FOUND. Removing the 16-bar minimum hold improved EVERY YEAR of the record -
fit +0.3143 against the champion's +0.2760, held out +0.1738 against +0.1572, the worst
fit year from +8.68% to +29.81%, and the drawdown slightly LOWER at 18.5% - on 36% more
trades, each paying the same toll. Two more levers turned out to carry nothing: the 12%
trailing stop (fit unchanged, held-out +0.0064) and the breadth gate (fit +0.0023,
held-out +0.0253, and no year worse). The Fear & Greed veto moved nothing at all.

WHAT IT GOT WRONG. `max_drawdown = 0.0` is not "no brake", it is the tightest brake
expressible: the orchestrator halts on `equity <= peak * (1 - max_drawdown)`, which is
true at bar one. Both arms that used it traded zero times and were then reported as the
two most load-bearing modules in the system. Repaired here with 1.0, which equity would
have to reach zero to breach, and pinned by a test against the brain rather than against
my reading of it.

WHY THE JOINT SEARCH NEVER FOUND THE MIN_HOLD RESULT, which is the part worth keeping.
v3 ran 1,607 usable trials with min_hold in its space and sampled the low end 82 times;
its best score there was +0.2714, BELOW the champion. That looks like a contradiction
and is not one. Of every v3 trial with min_hold <= 2, the one closest to the champion
differed in 24 of the other 31 levers. The point "the champion, with min_hold at 1" was
never evaluated, or approached. A 32-dimensional TPE anchored on an incumbent does not
measure the incumbent's ONE-LEVER NEIGHBOURS - it measures the joint space, where every
draw moves everything at once and a single lever's effect is invisible underneath.

That is the operator's own objection from three days ago, in numbers: "going from 0.75
to 0.72 HAS to produce a change - it cannot be that the initial values happen to be the
best in the world." They were not. The search simply could not see one lever move.

------------------------------------------------------------------------------------
THE RULE, WRITTEN BEFORE THE NUMBERS
------------------------------------------------------------------------------------
A single winning point is exactly what this project has been fooled by before, four
times. So min_hold does not get adopted for winning at 1; it gets adopted for being
ORDERED. The curve is measured at 1, 2, 4, 8, 12, 16 (the champion), 24 and 48:

  ORDERED     the fit score is non-increasing in min_hold across those eight points,
              allowing at most ONE inversion. A lever the book responds to smoothly is
              a mechanism; a lever that wins at exactly one setting is a draw.
  TRANSFERS   at the chosen setting the held-out score is at least the champion's AND
              the held-out worst year is no worse. 2024-2025 were never fitted.

BOTH, or nothing is adopted and this is filed as a curiosity. If both hold, the
candidate has earned ONE sealed 2026 reading - the same currency every other adoption
in this project has had to pay for, and the same one the 2-of-2 rule has now saved four
times.

The two lean arms ask the operator's simplicity question directly: `lean_three` drops
the trailing stop, the breadth gate and the Fear & Greed veto together (A119 says each
carries nothing alone - together is a different claim), and `lean_all` drops those three
AND the minimum hold. If lean_all clears the rule, the champion gets SIMPLER and better
at the same time, which is the outcome the operator asked for on 2026-09-07.

2026 is not read here.

Run from repo root:
    PYTHONPATH=trading-system python research/system06/tools/a120_minhold_and_lean.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")

_MDD = "__max_drawdown"
_MDD_OFF = 1.0          # see the docstring: 0.0 is the TIGHTEST brake, not the absent one
CHAMPION_MIN_HOLD = 16
CURVE = (1, 2, 4, 8, 12, 16, 24, 48)

# The three A119 called decoration or near-decoration, dropped together.
_LEAN3 = {"trail_stop": 0.0, "breadth_gate": 0.0, "fng_min": 0.0}

ARMS: dict[str, tuple[str, dict]] = {
    "baseline": ("the champion, verbatim", {}),
    "min_hold_1": ("min_hold -> 1 bar", {"min_hold": 1}),
    "min_hold_2": ("min_hold -> 2 bars", {"min_hold": 2}),
    "min_hold_4": ("min_hold -> 4 bars", {"min_hold": 4}),
    "min_hold_8": ("min_hold -> 8 bars", {"min_hold": 8}),
    "min_hold_12": ("min_hold -> 12 bars", {"min_hold": 12}),
    "min_hold_24": ("min_hold -> 24 bars", {"min_hold": 24}),
    "min_hold_48": ("min_hold -> 48 bars", {"min_hold": 48}),
    "lean_three": ("trailing stop + breadth gate + F&G, together", dict(_LEAN3)),
    "lean_all": ("those three AND the minimum hold", {**_LEAN3, "min_hold": 1}),
    "drawdown_brake_off": ("50% equity circuit breaker (A119 arm, repaired)",
                           {_MDD: _MDD_OFF}),
    "risk_layer_off": ("the whole risk layer (A119 arm, repaired)", {
        "trend_soft": 1.0, "stop_loss": 0.0, "trail_stop": 0.0, "breadth_gate": 0.0,
        "regime_deploy": 0.0, "meta_margin": 0.0, "money_model": 0.0, "fng_min": 0.0,
        "min_hold": 1, _MDD: _MDD_OFF}),
}

MAX_INVERSIONS = 1      # of the seven steps along the curve


def _nopt():
    spec = importlib.util.spec_from_file_location(
        "nopt", ROOT / "tools" / "numerical_optimization.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def ordered(curve: list[tuple[int, float]]) -> tuple[bool, int]:
    """Is the score non-increasing in min_hold, give or take one inversion?

    `curve` is [(min_hold, fit_score)] in ascending min_hold. Returns (verdict, count).
    """
    inversions = sum(1 for (_a, va), (_b, vb) in zip(curve, curve[1:]) if vb > va)
    return inversions <= MAX_INVERSIONS, inversions


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="run just these arms (baseline is forced)")
    args = ap.parse_args()

    nopt = _nopt()
    ev = nopt.Evaluator(nopt.FIT_YEARS, nopt.HOLDOUT_YEARS, with_enter=False)
    names = list(nopt.SPACE)
    anchor = nopt._champion_point_full(ev.risk, ev.band, names)
    base_mdd = float(ev.risk.get("max_drawdown") or 0.0)
    if int(anchor.get("min_hold", 0)) != CHAMPION_MIN_HOLD:
        print(f"note: the champion's min_hold is {anchor.get('min_hold')}, not "
              f"{CHAMPION_MIN_HOLD} - the curve still stands, its centre has moved")

    arms = ARMS if not args.only else \
        {n: v for n, v in ARMS.items() if n == "baseline" or n in args.only}
    print(f"A120 - {len(arms)} arms, fit {nopt.FIT_YEARS[0]}-{nopt.FIT_YEARS[-1]}, "
          f"held out {nopt.HOLDOUT_YEARS}, 2026 NOT read\n", flush=True)

    results: dict[str, dict] = {}
    for name, (what, off) in arms.items():
        point = dict(anchor)
        for k, v in off.items():
            if k != _MDD:
                point[k] = int(v) if nopt.SPACE[k][0] == "i" else float(v)
        ev.risk["max_drawdown"] = float(off.get(_MDD, base_mdd))
        t0 = time.time()
        try:
            r = ev.score(point)
        except Exception as exc:  # noqa: BLE001
            print(f"  {name:<20} FAILED: {exc}", flush=True)
            continue
        finally:
            ev.risk["max_drawdown"] = base_mdd
        results[name] = r
        print(f"  {name:<20} fit {r['fit']:+.4f}  held-out {r['holdout']:+.4f}  "
              f"worst yr {(r['fit_min_year'] or 0):+7.2%}  "
              f"maxDD {(r['fit_worst_drawdown'] or 0):5.1%}  "
              f"trades {r['trades']:>5}  ({time.time() - t0:.0f}s)", flush=True)

    if "baseline" not in results:
        print("\nno baseline - nothing to compare against")
        return 1
    base = results["baseline"]

    # ---- the curve ------------------------------------------------------------------
    curve = []
    for mh in CURVE:
        key = "baseline" if mh == CHAMPION_MIN_HOLD else f"min_hold_{mh}"
        if key in results:
            curve.append((mh, results[key]["fit"], results[key]["holdout"],
                          results[key]["fit_min_year"]))
    print("\nmin_hold response curve (ascending; the champion sits at "
          f"{CHAMPION_MIN_HOLD}):")
    print(f"{'min_hold':>9} {'fit':>10} {'held-out':>10} {'worst fit yr':>14}")
    for mh, fit, hold, worst in curve:
        mark = "  <- champion" if mh == CHAMPION_MIN_HOLD else ""
        print(f"{mh:>9} {fit:>+10.4f} {hold:>+10.4f} {(worst or 0):>13.2%}{mark}")
    is_ordered, inversions = ordered([(mh, f) for mh, f, _h, _w in curve])
    print(f"\nORDERED: {is_ordered}  ({inversions} inversion(s) of "
          f"{max(0, len(curve) - 1)} steps; at most {MAX_INVERSIONS} allowed)")

    # ---- the arms -------------------------------------------------------------------
    print("\n" + "=" * 104)
    print(f"{'arm':<20} {'changes':<40} {'d fit':>9} {'d held':>9} "
          f"{'d worst':>9} {'d maxDD':>9}")
    print("=" * 104)
    for name, (what, _off) in arms.items():
        if name not in results or name == "baseline":
            continue
        r = results[name]
        print(f"{name:<20} {what:<40} {r['fit'] - base['fit']:+9.4f} "
              f"{r['holdout'] - base['holdout']:+9.4f} "
              f"{(r['fit_min_year'] or 0) - (base['fit_min_year'] or 0):+8.2%} "
              f"{(r['fit_worst_drawdown'] or 0) - (base['fit_worst_drawdown'] or 0):+8.2%}")

    print("\nper-year returns:")
    years = [str(y) for y in sorted({int(y) for r in results.values()
                                     for y in r["returns"]})]
    print(f"{'arm':<20} " + " ".join(f"{y:>9}" for y in years))
    for name in arms:
        if name not in results:
            continue
        rr = results[name]["returns"]
        print(f"{name:<20} " + " ".join(
            f"{rr[y]:+8.1%}" if y in rr else "        -" for y in years))

    # ---- adjudication ---------------------------------------------------------------
    print("\n" + "-" * 104)
    verdicts = {}
    for name in ("min_hold_1", "lean_three", "lean_all"):
        if name not in results:
            continue
        r = results[name]
        transfers = (r["holdout"] >= base["holdout"]
                     and (r["holdout_min_year"] or 0.0) >= (base["holdout_min_year"] or 0.0))
        # The curve is a statement about min_hold, so only the arms that MOVE min_hold
        # have to answer to it. lean_three leaves it at the champion's 16.
        needs_curve = int(ARMS[name][1].get("min_hold", CHAMPION_MIN_HOLD)) != CHAMPION_MIN_HOLD
        ok = transfers and (is_ordered or not needs_curve)
        verdicts[name] = "EARNS A SEALED READING" if ok else "FILED, NOT ADOPTED"
        print(f"{name:<20} transfers={transfers}  "
              f"{'ordered=' + str(is_ordered) if needs_curve else 'curve n/a'}  "
              f"-> {verdicts[name]}")
    print("A sealed reading is spent ONCE, on the best of whatever qualifies - not on "
          "each arm that does.")

    out = ROOT / "rnd" / f"a120_minhold_lean_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A120", "at": datetime.now(timezone.utc).isoformat(),
        "fit_years": list(nopt.FIT_YEARS), "holdout_years": list(nopt.HOLDOUT_YEARS),
        "sealed_read": False,
        "curve": [{"min_hold": mh, "fit": f, "holdout": h, "worst_fit_year": w}
                  for mh, f, h, w in curve],
        "ordered": is_ordered, "inversions": inversions,
        "max_inversions_allowed": MAX_INVERSIONS,
        "arms": {n: {"changes": w, "off": dict(o)} for n, (w, o) in arms.items()},
        "results": {n: {k: r[k] for k in (
            "fit", "holdout", "fit_min_year", "holdout_min_year", "fit_worst_drawdown",
            "worst_drawdown", "fit_mandate_years", "fit_months_won", "months_won",
            "trades", "all_positive", "returns")} for n, r in results.items()},
        "verdicts": verdicts,
        "note": "v3 sampled min_hold<=2 eighty-two times and never within 24 levers of "
                "the champion; a joint TPE does not measure one-lever neighbours of its "
                "own anchor, which is why this study exists.",
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
