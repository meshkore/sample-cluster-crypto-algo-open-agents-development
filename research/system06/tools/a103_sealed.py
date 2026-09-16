"""The deep-field net's ONE sealed 2026 reading, earned by a held-out win.

Why this reading is being taken, on the record before the number exists:

  P50 (rnd/a103_paired_2026-09-05.json) ran the deep-field net under the champion's
  exact band and risk layer and scored it with the study's own instrument:

      FIT      +0.3196   vs champion  +0.2805
      HELD-OUT +0.2019   vs champion  +0.1643      <- first candidate ever to win here
      2025 (the only year neither net trained on): +3.72% vs -1.49%

  The standing method (operator, 2026-09-04; A90) is that research numbers are
  context, out-of-sample numbers are evidence, and a sealed reading is bought only
  by a held-out win. This is that purchase. The two candidates that previously
  spent readings (P47, A83) had no such gate to clear - both doubled the research
  score and lost the sealed year, which is why the gate exists.

The reading is taken with the SAME brain kwargs as P50 - champion band and risk
verbatim, only the net and its derived overlays swapped - and is recorded in
rnd/sealed_readouts.jsonl WHATEVER it says. A bad number is recorded with the same
keystrokes as a good one.

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a103_sealed.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
NEW = ROOT / "_w192d6"


def main() -> int:
    from system006_oracle_net_15m import launch, universe
    from system006_oracle_net_15m.dataset import Dataset

    t0 = time.time()
    paired = json.loads((ROOT / "rnd" / "a103_paired_2026-09-05.json").read_text())
    assert paired["wins_holdout"] is True, (
        "the sealed reading is only bought by a held-out win; P50 does not record one")

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    band, risk = dict(best["band"]), dict(best["risk"])
    brain = {"enter": float(band["enter"]), "exit_": float(band["exit_"]),
             "min_hold": int(band["min_hold"]),
             "meta_signals": str(NEW / "meta.npz"), **risk}
    if float(risk.get("money_model") or 0) > 0:
        brain["size_signals"] = str(NEW / "moneymodel.npz")

    symbols = universe.load()
    dataset = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    sig = str(NEW / "signals.npz")

    print("opening the sealed window once ...", flush=True)
    fwd = launch.forward(dataset, sig, brain_kwargs=brain)
    inc = best.get("forward_2026") or {}
    print("\n" + "=" * 74)
    print("SEALED 2026 - deep-field net, champion book (ONE deliberate reading)")
    print("=" * 74)
    print(f"  return {fwd['return_pct']:+.2%}   maxDD {fwd['max_drawdown']:.2%}   "
          f"trades {fwd['trades']}   exposure {fwd['average_exposure']:.2%}")
    print(f"  champion on record: {inc.get('return_pct', 0):+.2%} at "
          f"{inc.get('max_drawdown', 0):.2%} DD, {inc.get('trades')} trades")

    row = {
        "id": "A103-sealed", "at": datetime.now(timezone.utc).isoformat(),
        "candidate": "deep-field 192x6 (receptive field 127/96), champion band+risk",
        "earned_by": "P50 held-out win: +0.2019 vs +0.1643 (first candidate to clear the gate)",
        "sealed_2026": {k: fwd.get(k) for k in
                        ("return_pct", "max_drawdown", "trades", "average_exposure",
                         "status", "stop_reason")},
        "champion_2026_on_record": inc,
        "minutes": round((time.time() - t0) / 60, 1),
    }
    ledger = ROOT / "rnd" / "sealed_readouts.jsonl"
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    print(f"\nrecorded in {ledger} whatever it says.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
