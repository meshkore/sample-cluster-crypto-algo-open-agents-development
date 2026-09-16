"""The lean champion's ONE sealed 2026 reading, earned by an ordered response.

Written before the number exists, so the reason for opening the window is on the record
independently of what it says.

WHAT EARNED IT. A120 measured min_hold at 1, 2, 4, 8, 12, 16 (the champion), 24 and 48
and the response is monotone in the lever with ZERO inversions of seven steps - the fit
score falls 0.3143, 0.3073, 0.3010, 0.2931, 0.2766, 0.2760, 0.2184, 0.0465 and the worst
fitted year falls with it, +29.81% down to -16.61%. That is a mechanism, not a draw, and
it is the pre-registered condition this project has used to refuse four previous
candidates that won exactly one exam.

The arm being read is `lean_all`: the champion with the 16-bar minimum hold removed and
the three levers A119 measured as carrying nothing - the 12% trailing stop, the breadth
gate and the Fear & Greed veto - deleted. On the fitted half it scores +0.3167 against
the champion's +0.2760 with its worst year at +32.85% against +8.68%, and on 2024-2025,
which no threshold here was ever fitted to, +0.1769 against +0.1572. Its drawdown is
11.9% against the champion's 19.1%. It is the only candidate this project has produced
that is simultaneously simpler, more profitable and less exposed.

WHAT THE READING CANNOT REPAIR, stated up front. 2025 stays at +1.7% - better than the
champion's -3.0% but nowhere near the +30% mandate. Whatever 2026 says, the lean
champion does not meet the operator's target in every year, and this study must not be
reported as if it did.

WHY THE OPTIMUM SITS ON THE BOUNDARY, which is a caveat and not a flaw. min_hold cannot
go below 1: at 0 the book could exit on the same bar it entered, which is an execution
fiction rather than a strategy. So the best measured point is at the edge of the
admissible range, and that edge is set by honesty about execution, not by the data.

The control is re-run through this same code path rather than copied from best.json, so
the comparison cannot drift, and the brain kwargs come from the SAME Evaluator that
scored the arm rather than from a dict rebuilt by hand - which is how settings drift
between the experiment and the adoption.

Recorded in rnd/sealed_readouts.jsonl whatever it says. A bad number is written with the
same keystrokes as a good one.

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a120_sealed.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
ARM = "lean_all"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    from system006_oracle_net_15m import launch, universe
    from system006_oracle_net_15m.dataset import Dataset

    t0 = time.time()
    studies = sorted((ROOT / "rnd").glob("a120_minhold_lean_*.json"))
    if not studies:
        sys.exit("no A120 result on disk - the reading has not been earned")
    study = json.loads(studies[-1].read_text(encoding="utf-8"))
    if not study.get("ordered"):
        sys.exit(f"A120 records ordered={study.get('ordered')} - the response is a "
                 f"draw, not a mechanism, and buys nothing")
    if study.get("verdicts", {}).get(ARM) != "EARNS A SEALED READING":
        sys.exit(f"A120 does not record {ARM} as qualifying: "
                 f"{study.get('verdicts', {}).get(ARM)!r}")

    nopt = _load("nopt", ROOT / "tools" / "numerical_optimization.py")
    a120 = _load("a120", ROOT / "tools" / "a120_minhold_and_lean.py")

    ev = nopt.Evaluator(nopt.FIT_YEARS, nopt.HOLDOUT_YEARS, with_enter=False)
    anchor = nopt._champion_point_full(ev.risk, ev.band, list(nopt.SPACE))
    lean = dict(anchor)
    for k, v in a120.ARMS[ARM][1].items():
        if k == a120._MDD:
            continue
        lean[k] = int(v) if nopt.SPACE[k][0] == "i" else float(v)
    control_brain, lean_brain = ev.brain(anchor), ev.brain(lean)
    changed = {k: (control_brain.get(k), lean_brain.get(k))
               for k in set(control_brain) | set(lean_brain)
               if control_brain.get(k) != lean_brain.get(k)}
    print(f"what changes between the two readings: "
          f"{json.dumps(changed, default=str, sort_keys=True)}\n", flush=True)

    symbols = universe.load()
    dataset = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    sig = str(ROOT / "signals.npz")

    print("control (the shipping champion) through this same path ...", flush=True)
    ctl = launch.forward(dataset, sig, brain_kwargs=control_brain)
    print(f"  {ctl['return_pct']:+.2%}  maxDD {ctl['max_drawdown']:.2%}  "
          f"trades {ctl['trades']}", flush=True)

    print("opening the sealed window for the lean champion ...", flush=True)
    fwd = launch.forward(dataset, sig, brain_kwargs=lean_brain)

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    inc = best.get("forward_2026") or {}
    print("\n" + "=" * 78)
    print("SEALED 2026 - the lean champion (ONE deliberate reading)")
    print("=" * 78)
    print(f"  lean      {fwd['return_pct']:+.2%}   maxDD {fwd['max_drawdown']:.2%}   "
          f"trades {fwd['trades']}   exposure {fwd['average_exposure']:.2%}")
    print(f"  control   {ctl['return_pct']:+.2%}   maxDD {ctl['max_drawdown']:.2%}   "
          f"trades {ctl['trades']}   exposure {ctl['average_exposure']:.2%}")
    print(f"  on record {inc.get('return_pct', 0):+.2%}   "
          f"maxDD {inc.get('max_drawdown', 0):.2%}   trades {inc.get('trades')}")
    delta = fwd["return_pct"] - ctl["return_pct"]
    print(f"\n  difference: {delta:+.2%} against the control re-run here, and the "
          f"mandate asks for +30%")

    row = {
        "id": "A120-sealed", "at": datetime.now(timezone.utc).isoformat(),
        "candidate": "lean champion: min_hold 16->1, trail_stop / breadth_gate / "
                     "fng_min removed; champion net and overlays unchanged",
        "earned_by": f"A120 ordered response over {list(a120.CURVE)} with "
                     f"{study.get('inversions')} inversion(s); fit +0.3167 vs +0.2760, "
                     f"held-out +0.1769 vs +0.1572, worst fitted year +32.85% vs +8.68%",
        "changed_levers": {k: {"champion": a, "lean": b} for k, (a, b) in changed.items()},
        "sealed_2026": {k: fwd.get(k) for k in
                        ("return_pct", "max_drawdown", "trades", "average_exposure",
                         "status", "stop_reason")},
        "control_2026_rerun": {k: ctl.get(k) for k in
                               ("return_pct", "max_drawdown", "trades",
                                "average_exposure", "status", "stop_reason")},
        "champion_2026_on_record": inc,
        "caveat": "2025 remains +1.7% against a +30% mandate; a sealed win does not "
                  "make this configuration compliant, only better.",
        "minutes": round((time.time() - t0) / 60, 1),
    }
    ledger = ROOT / "rnd" / "sealed_readouts.jsonl"
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    print(f"\nrecorded in {ledger} whatever it says.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
