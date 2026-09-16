"""min_hold 32: one lever, one sealed reading, bought with eight boundaries.

WHY THIS READING IS BEING TAKEN, written before the number exists.

A120's sealed reading was spent and lost this morning - the lean champion made -11.65%
against +25.71%. It had been bought with a held-out win on 2024-2025, and those years
were held out from the THRESHOLDS while the net had trained on them. The instrument was
weak and the loss said so.

What followed explains the loss rather than excusing it. A121 proposed memorisation and
A122 refuted it: with the calendar year held fixed across three training cutoffs, whether
the net had seen a year changed almost nothing (2024 pays 0.86x seen and 0.81x unseen).
What survives is a REGIME CHANGE. The payoff for trading fast collapsed:

    2018 2.97x  2019 1.94x  2020 1.58x  2021 4.17x
    2022 1.12x  2023 1.00x  2024 0.82x  2025 1.08x  2026 0.70x (sealed)

The champion's 16-bar hold was fitted on a record four-fifths of which predates that
change, and every study since re-confirmed it on the same record.

WHAT BOUGHT THIS READING. Eight walk-forward boundaries - three cutoffs, single nets,
five-seed ensembles, a recency-weighted net and a reference-feature net, every one of
which LOST its own exam - scored on the years each net never saw:

    net              <=      16        32        48        64
    _wf22_ens5      2022  -0.1130   -0.0337   -0.0792   -0.0221
    _wf22_single    2022  +0.0885   +0.1362   +0.1428   +0.1707
    _wf23_ens5      2023  +0.1395   +0.2271   +0.2088   +0.2184
    _wf23_ref       2023  -0.1417   +0.0112   +0.0059   +0.1946
    _wf23_single    2023  +0.1064   +0.2077   +0.2182   +0.1963
    _wf192x3        2024  -0.0429   -0.0333   -0.0822   -0.0358
    _wf_recency_hl2 2024  +0.0417   -0.2703   -0.0973   -0.1486   <- the dissenter
    _wf_ref         2024  +0.0398   +0.2013   +0.2059   +0.0881

Seven of eight. The setting was decided by the tie-break registered before the last five
cells were filled - votes, then median margin, then closest to 16 - and it resolved
NARROWLY: 32 and 64 both win 7 of 8, with median margins of +0.0834 and +0.0805. That
0.0029 is what separates them, and it is honest to say so rather than to present 32 as
a clear winner. The consolation is that the whole 32-64 band beats 16 nearly everywhere,
so this is a plateau and not a peak - had it been a peak, the number would have been
fitted rather than found.

THE PREDICTION, registered here so the reading can falsify something. If the regime
account is right, min_hold 32 should BEAT the champion's +25.71% on 2026 at roughly half
its turnover - 90 trades is already low, and a longer hold cuts it further. If it loses,
the regime account is wrong or 2026 is not the market the other boundaries describe, and
min_hold closes for good with the reason on the record.

ONE LEVER MOVES. Not four, as in the lean arm - `min_hold` 16 -> 32, the champion's net,
overlays, band and every other threshold untouched. The control is re-run through this
same path rather than copied, and the brain kwargs come from the same Evaluator that
scored the boundaries.

Recorded in rnd/sealed_readouts.jsonl whatever it says.

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a124_sealed.py
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


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    from system006_oracle_net_15m import launch, universe
    from system006_oracle_net_15m.dataset import Dataset

    t0 = time.time()
    grids = sorted((ROOT / "rnd").glob("a124_complete_grid_*.json"))
    if not grids:
        sys.exit("no A124 grid on disk - the reading has not been earned")
    grid = json.loads(grids[-1].read_text(encoding="utf-8"))
    if not grid.get("replicates"):
        sys.exit(f"A124 records replicates={grid.get('replicates')} - nothing is read")
    setting = grid.get("setting")
    if not setting:
        sys.exit("A124 named no setting")
    setting = int(setting)
    # Every cell filled, or the vote is over a grid with holes in it - which is the flaw
    # A124 existed to repair and would silently return if one backtest had failed. JSON
    # keys are strings, so the holds are compared as strings on both sides.
    holds = sorted(grid["stats"], key=int)
    for net, blk in grid["grid"].items():
        missing = [h for h in holds if h not in blk["long"]]
        if missing:
            sys.exit(f"{net} is missing {missing}; the vote is over an incomplete grid")

    nopt = _load("nopt", ROOT / "tools" / "numerical_optimization.py")
    ev = nopt.Evaluator(nopt.FIT_YEARS, nopt.HOLDOUT_YEARS, with_enter=False)
    anchor = nopt._champion_point_full(ev.risk, ev.band, list(nopt.SPACE))
    candidate = dict(anchor)
    candidate["min_hold"] = setting
    control_brain, cand_brain = ev.brain(anchor), ev.brain(candidate)
    changed = {k: (control_brain.get(k), cand_brain.get(k))
               for k in set(control_brain) | set(cand_brain)
               if control_brain.get(k) != cand_brain.get(k)}
    if set(changed) != {"min_hold"}:
        sys.exit(f"this reading must move ONE lever; it moves {sorted(changed)}")
    print(f"one lever moves: min_hold {changed['min_hold'][0]} -> "
          f"{changed['min_hold'][1]}\n", flush=True)

    symbols = universe.load()
    dataset = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    sig = str(ROOT / "signals.npz")

    print("control (the shipping champion) through this same path ...", flush=True)
    ctl = launch.forward(dataset, sig, brain_kwargs=control_brain)
    print(f"  {ctl['return_pct']:+.2%}  maxDD {ctl['max_drawdown']:.2%}  "
          f"trades {ctl['trades']}", flush=True)

    print(f"opening the sealed window for min_hold {setting} ...", flush=True)
    fwd = launch.forward(dataset, sig, brain_kwargs=cand_brain)

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    inc = best.get("forward_2026") or {}
    delta = fwd["return_pct"] - ctl["return_pct"]
    print("\n" + "=" * 78)
    print(f"SEALED 2026 - min_hold {setting} (ONE deliberate reading)")
    print("=" * 78)
    print(f"  candidate {fwd['return_pct']:+.2%}   maxDD {fwd['max_drawdown']:.2%}   "
          f"trades {fwd['trades']}   exposure {fwd['average_exposure']:.2%}")
    print(f"  control   {ctl['return_pct']:+.2%}   maxDD {ctl['max_drawdown']:.2%}   "
          f"trades {ctl['trades']}   exposure {ctl['average_exposure']:.2%}")
    print(f"  on record {inc.get('return_pct', 0):+.2%}   "
          f"maxDD {inc.get('max_drawdown', 0):.2%}   trades {inc.get('trades')}")
    print(f"\n  difference {delta:+.2%}; the prediction registered before the run was "
          f"that a longer hold WINS here. It {'held' if delta > 0 else 'did not hold'}.")
    print("  the mandate asks for +30% every year, which neither arm reaches in 2025.")

    row = {
        "id": "A124-sealed", "at": datetime.now(timezone.utc).isoformat(),
        "candidate": f"champion with min_hold {setting} (one lever; net, overlays, band "
                     f"and every other threshold unchanged)",
        "earned_by": f"A124 complete grid: some longer hold beats 16 on "
                     f"{grid['replications']} of {len(grid['grid'])} walk-forward "
                     f"boundaries; {setting} wins {grid['stats'][str(setting)]['wins']}"
                     f"/{grid['stats'][str(setting)]['n']} with median margin "
                     f"{grid['stats'][str(setting)]['median_margin']:+.4f}",
        "prediction_registered": "a longer hold beats the champion on 2026",
        "prediction_held": bool(delta > 0),
        "sealed_2026": {k: fwd.get(k) for k in
                        ("return_pct", "max_drawdown", "trades", "average_exposure",
                         "status", "stop_reason")},
        "control_2026_rerun": {k: ctl.get(k) for k in
                               ("return_pct", "max_drawdown", "trades",
                                "average_exposure", "status", "stop_reason")},
        "champion_2026_on_record": inc,
        "tie_break_note": "32 and 64 both won 7 of 8; median margins +0.0834 and +0.0805. "
                          "The registered tie-break resolved it, narrowly.",
        "minutes": round((time.time() - t0) / 60, 1),
    }
    ledger = ROOT / "rnd" / "sealed_readouts.jsonl"
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    print(f"\nrecorded in {ledger} whatever it says.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
