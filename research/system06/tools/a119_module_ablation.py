"""A119: which of the champion's modules actually earn their place? Turn each off.

Operator, 2026-09-07: "are we not over-complicating everything? Sometimes a simple
algorithm is much better than a complex one."

A118 answered half of that question - the apparatus is NOT leveraged beta; it beats
buy-and-hold, a 200-day moving average and an equal-weight basket on the sealed year
and never had a year worse than -2.96% against BTC's -72.77%. But "the machine works"
is not the same claim as "every part of the machine is doing something", and the second
claim has never been tested here. It is the operator's instinct pointed at a place where
it can be measured.

The shipping champion sets NINE of the thirty-three levers the brain accepts. Each of
those nine was switched on by its own one-lever experiment, against a book tuned for its
absence, and then frozen - some of them a month and several nets ago. Nothing since has
asked whether a lever still contributes NOW, beside the other eight, on this net.

So: hold every other lever at the champion's value and turn ONE off, then read the same
record. Fourteen arms, one backtest each over 2018-2025.

  baseline            the champion, verbatim, through this code path
  trend_off           trend_soft=1.0 - enter down-trend names at full size (the veto gone)
  stop_loss_off       stop_loss 0.08 -> 0
  trail_stop_off      trail_stop 0.12 -> 0
  stops_off           both, together - they overlap and one may be covering the other
  breadth_off         breadth_gate 0.30 -> 0
  regime_off          regime_deploy 0.50 -> 0 (static position_fraction)
  meta_off            meta_margin -> None (the meta-labelling overlay unused)
  money_model_off     money_model 0.50 -> 0 (learned sizing unused)
  fng_off             fng_min 25 -> 0 (the Fear & Greed entry veto gone)
  drawdown_brake_off  max_drawdown 0.50 -> 0 (the equity circuit breaker gone)
  min_hold_off        min_hold 16 -> 1 bar
  concentration_off   max_positions 2 -> 8 (the concentration constraint relaxed)
  risk_layer_off      ALL of the above at once: the naked net with only size and band

The last arm is the one that keeps the others honest. If the whole risk layer removed
costs little, then A118's verdict belongs to the NET and the modules are ceremony; if it
costs everything, the modules matter in aggregate even where no single one shows up -
and this study's per-arm numbers are then a statement about REDUNDANCY, not about worth.

------------------------------------------------------------------------------------
THE DECISION RULE, WRITTEN BEFORE ANY NUMBER EXISTS
------------------------------------------------------------------------------------
Read on the FIT half (2018-2023) with the held-out half (2024-2025) recorded beside it
and used only to veto. 2026 is not read at all: this is a diagnosis, not an adoption,
and a diagnosis has no business inside the sealed window.

  DECORATION   |d fit score| < 0.005 AND the worst fit year no worse than 1.0pp
               AND the fit drawdown no worse than 1.0pp AND the held-out score no
               worse than 0.005.
               -> the module is carrying nothing. Propose deleting it from the recipe,
                  which simplifies the system AND shrinks every future search space.

  COST         removing it IMPROVES the fit score by >= 0.005 and does not worsen the
               held-out score.
               -> the module is actively paying to be here. Candidate removal, but it
                  must still clear walk-forward before it touches best.json.

  LOAD-BEARING removing it costs >= 0.005 of fit score, or >= 2pp of the worst year,
               or >= 3pp of drawdown.
               -> keep, and we now know what it is for.

Anything between DECORATION and LOAD-BEARING is UNCLEAR and stays exactly where it is.
The asymmetry is deliberate: the burden of proof falls on removal, because the cheap
mistake here is deleting a module that only earns its keep in a year we have not lived
through yet.

WHAT THIS CANNOT SETTLE, stated up front. Every arm is measured on the same years the
champion's levers were chosen against, so a module that looks load-bearing may only be
load-bearing FOR THIS RECORD. That is why the rule vetoes on the held-out half and why
removal needs walk-forward afterwards. What the study can settle cheaply and honestly is
the negative: a module whose removal changes nothing anywhere changed nothing.

Run from repo root:
    PYTHONPATH=trading-system python research/system06/tools/a119_module_ablation.py
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

# arm -> (one line on what it removes, {lever: the off value})
# A literal dict of string keys on purpose: test_experiment_tools_report reads this
# table by AST and checks that every arm the report block indexes exists here, which is
# the guard that catches a report copied from a previous experiment.
# `_MDD` is not a lever in SPACE - it rides in from best.json's risk block - so it is
# named here and applied to the Evaluator's own risk dict for that arm only.
_MDD = "__max_drawdown"
ARMS: dict[str, tuple[str, dict]] = {
    "baseline": ("the champion, verbatim", {}),
    "trend_off": ("60d up-trend entry veto", {"trend_soft": 1.0}),
    "stop_loss_off": ("8% hard stop", {"stop_loss": 0.0}),
    "trail_stop_off": ("12% trailing stop", {"trail_stop": 0.0}),
    "stops_off": ("both stops", {"stop_loss": 0.0, "trail_stop": 0.0}),
    "breadth_off": ("breadth risk-off gate", {"breadth_gate": 0.0}),
    "regime_off": ("regime-scaled deployment", {"regime_deploy": 0.0}),
    "meta_off": ("meta-labelling veto", {"meta_margin": 0.0}),
    "money_model_off": ("learned money-management sizing", {"money_model": 0.0}),
    "fng_off": ("Fear & Greed entry veto", {"fng_min": 0.0}),
    "drawdown_brake_off": ("50% equity circuit breaker", {_MDD: 0.0}),
    "min_hold_off": ("16-bar minimum hold", {"min_hold": 1}),
    "concentration_off": ("2-position concentration cap", {"max_positions": 8}),
    "risk_layer_off": ("EVERY module above, at once", {
        "trend_soft": 1.0, "stop_loss": 0.0, "trail_stop": 0.0, "breadth_gate": 0.0,
        "regime_deploy": 0.0, "meta_margin": 0.0, "money_model": 0.0, "fng_min": 0.0,
        "min_hold": 1, _MDD: 0.0}),
}

# The pre-registered thresholds, as constants so the report cannot quietly use others.
EPS_SCORE = 0.005      # fit-score movement that counts as "something happened"
EPS_YEAR = 0.010       # 1.0pp on the worst calendar year
EPS_DD = 0.010         # 1.0pp of drawdown for DECORATION
BIG_YEAR = 0.020       # 2.0pp on the worst year for LOAD-BEARING
BIG_DD = 0.030         # 3.0pp of drawdown for LOAD-BEARING


def _nopt():
    spec = importlib.util.spec_from_file_location(
        "nopt", ROOT / "tools" / "numerical_optimization.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _verdict(base: dict, arm: dict) -> str:
    """Apply the rule above. Positive d = the ablation SCORED HIGHER than the champion."""
    d_fit = arm["fit"] - base["fit"]
    d_hold = arm["holdout"] - base["holdout"]
    d_year = (arm["fit_min_year"] or 0.0) - (base["fit_min_year"] or 0.0)
    d_dd = (arm["fit_worst_drawdown"] or 0.0) - (base["fit_worst_drawdown"] or 0.0)
    if d_fit >= EPS_SCORE and d_hold >= -EPS_SCORE:
        return "COST"
    if (d_fit <= -EPS_SCORE) or (d_year <= -BIG_YEAR) or (d_dd >= BIG_DD):
        return "LOAD-BEARING"
    if (abs(d_fit) < EPS_SCORE and d_year >= -EPS_YEAR
            and d_dd <= EPS_DD and d_hold >= -EPS_SCORE):
        return "DECORATION"
    return "UNCLEAR"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="run just these arms (baseline is forced)")
    args = ap.parse_args()

    nopt = _nopt()
    ev = nopt.Evaluator(nopt.FIT_YEARS, nopt.HOLDOUT_YEARS, with_enter=False)
    names = list(nopt.SPACE)
    missing = [k for k, f in nopt.NEEDS_FILE.items() if not (ROOT / f).exists()]
    if missing:
        print(f"note: overlays missing for {missing}; those arms measure nothing", flush=True)
    anchor = nopt._champion_point_full(ev.risk, ev.band, names)
    base_mdd = float(ev.risk.get("max_drawdown") or 0.0)

    arms = ARMS if not args.only else \
        {n: v for n, v in ARMS.items() if n == "baseline" or n in args.only}
    print(f"A119 module ablation - {len(arms)} arms, "
          f"fit {nopt.FIT_YEARS[0]}-{nopt.FIT_YEARS[-1]}, "
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

    # ---- report ---------------------------------------------------------------------
    print("\n" + "=" * 104)
    print(f"{'arm':<20} {'removes':<34} {'d fit':>9} {'d held':>9} "
          f"{'d worst':>9} {'d maxDD':>9}  verdict")
    print("=" * 104)
    rows = []
    for name, (what, _off) in arms.items():
        if name not in results or name == "baseline":
            continue
        r = results[name]
        d_fit = r["fit"] - base["fit"]
        d_hold = r["holdout"] - base["holdout"]
        d_year = (r["fit_min_year"] or 0.0) - (base["fit_min_year"] or 0.0)
        d_dd = (r["fit_worst_drawdown"] or 0.0) - (base["fit_worst_drawdown"] or 0.0)
        v = _verdict(base, r)
        rows.append((name, what, d_fit, d_hold, d_year, d_dd, v))
    for name, what, d_fit, d_hold, d_year, d_dd, v in sorted(rows, key=lambda x: x[2]):
        print(f"{name:<20} {what:<34} {d_fit:+9.4f} {d_hold:+9.4f} "
              f"{d_year:+8.2%} {d_dd:+8.2%}  {v}")

    print("\nper-year returns (the champion first, then every arm):")
    years = [str(y) for y in sorted({int(y) for r in results.values()
                                     for y in r["returns"]})]
    print(f"{'arm':<20} " + " ".join(f"{y:>9}" for y in years))
    for name in arms:
        if name not in results:
            continue
        rr = results[name]["returns"]
        print(f"{name:<20} " + " ".join(
            f"{rr[y]:+8.1%}" if y in rr else "        -" for y in years))

    dec = [r[0] for r in rows if r[6] == "DECORATION"]
    cost = [r[0] for r in rows if r[6] == "COST"]
    print(f"\ncarrying nothing (DECORATION): {dec or 'none'}")
    print(f"actively paying to be here (COST): {cost or 'none'}")
    print("Neither is adopted here. Removal changes the live path and therefore has to "
          "clear walk-forward first; this study only says WHERE to point it.")

    out = ROOT / "rnd" / f"a119_ablation_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A119", "at": datetime.now(timezone.utc).isoformat(),
        "fit_years": list(nopt.FIT_YEARS), "holdout_years": list(nopt.HOLDOUT_YEARS),
        "sealed_read": False,
        "rule": {"eps_score": EPS_SCORE, "eps_year": EPS_YEAR, "eps_dd": EPS_DD,
                 "big_year": BIG_YEAR, "big_dd": BIG_DD},
        "arms": {n: {"removes": w, "off": dict(o)} for n, (w, o) in arms.items()},
        "results": {n: {k: r[k] for k in (
            "fit", "holdout", "fit_min_year", "holdout_min_year", "fit_worst_drawdown",
            "worst_drawdown", "fit_mandate_years", "fit_months_won", "months_won",
            "trades", "all_positive", "returns")} for n, r in results.items()},
        "verdicts": {r[0]: r[6] for r in rows},
        "note": "one-at-a-time ablation on the champion net, measured on the years its "
                "levers were chosen against; a LOAD-BEARING verdict may be specific to "
                "this record, which is why removal still needs walk-forward.",
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
