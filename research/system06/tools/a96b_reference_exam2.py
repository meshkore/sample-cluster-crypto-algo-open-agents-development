"""A96b: the reference features' SECOND exam - and a prediction made before the run.

Exam 1 (train <= 2024, examine 2025), against the measured 44-column control:

    control, 44 columns          -6.54%   DD 21.9%    72 trades
    +8 reference columns         +0.98%   DD 11.8%   116 trades   [confirmation]
    + recency half-life 2y      +20.44%   DD 11.5%    75 trades   [exploratory]

Both arms roughly HALVED the drawdown, which is a steadier property than return and
the first thing in this project to move that far. But three candidates have now won a
first exam and lost the next, so exam 1 buys exam 2 and nothing else.

THE PREDICTION, written before the numbers exist, because it is what makes this run
worth its GPU hours rather than just another pass:

  Recency half-life 2y ALONE was measured on this exact split (A110b) and LOST by
  thirty points: -7.76% against the +22.36% control on 2024. So if the combination
  arm collapses on 2024 too, the +20.44% of exam 1 was mostly the recency lever
  finding one specific year, and the reference columns were along for the ride.
  If the combination HOLDS on 2024 where recency alone failed, the reference columns
  are carrying it and the pair is real.

Either outcome is informative, which is the point of stating it in advance.

    control (44 columns)   ALREADY MEASURED: 2024 +22.36% DD 17.9% 308 trades
    arm A   reference alone      - the CONFIRMATION arm; 2 of 2 earns the adoption attempt
    arm B   reference + recency  - its own series; also needs 2 of 2, and carries a
                                   lever already known to fail this exact exam

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a96b_reference_exam2.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
TRAIN_UNTIL = 2023
EXAM_YEAR = 2024
CONTROL = {"return": 0.2236, "max_drawdown": 0.179, "trades": 308,
           "source": "rnd/a112_wf_second_exam_2026-09-05.json, arm wf23_single"}
ARMS = {
    "wf23_ref": {"reference_features": True, "recency_half_life": 0.0},
    "wf23_ref_rec2": {"reference_features": True, "recency_half_life": 2.0},
}


def main() -> int:
    from system006_oracle_net_15m import autoloop, infer, launch, moneymodel, train, universe
    from system006_oracle_net_15m import meta as metalabel
    from system006_oracle_net_15m.dataset import Dataset

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    cfg, band, risk = dict(best["config"]), dict(best["band"]), dict(best["risk"])
    enter, exit_, hold = float(band["enter"]), float(band["exit_"]), int(band["min_hold"])
    symbols = universe.load()
    dataset = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for series in rbars.values() for b in series})

    results = {}
    for name, arm in ARMS.items():
        scratch = ROOT / f"_{name}"
        scratch.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        print(f"\n=== {name}: half-life {arm['recency_half_life']}y, "
              f"train_until={TRAIN_UNTIL} ===", flush=True)
        if not (scratch / "oracle_net.pt").exists():
            train.train(data_root=DATA, symbols=symbols, threshold=cfg["threshold"],
                        window=cfg["window"], epochs=cfg["epochs"], lr=cfg["lr"],
                        dropout=cfg["dropout"], out_dir=str(scratch), seed=91002,
                        uniqueness_weighting=float(cfg.get("uniqueness_weighting", 0.0)),
                        enter=enter, exit_=exit_, min_hold=hold,
                        channels=(192, 192, 192), train_until=TRAIN_UNTIL,
                        reference_features=arm["reference_features"],
                        recency_half_life=arm["recency_half_life"])
            print(f"{name} trained in {(time.time() - t0) / 60:.1f} min", flush=True)

        sig = str(scratch / "signals.npz")
        if not Path(sig).exists():
            infer.export(data_root=DATA, symbols=symbols, model_dir=str(scratch),
                         out_path=sig,
                         trend_span=int(cfg.get("trend_span", autoloop.TREND_SPAN)))
        if not (scratch / "meta.npz").exists():
            cand = metalabel.gather_candidates(dataset, sig, symbols, enter=enter)
            verdicts, _doc = metalabel.build_verdicts(cand)
            metalabel.write_meta(verdicts, str(scratch / "meta.npz"))
        brain = {"enter": enter, "exit_": exit_, "min_hold": hold,
                 "meta_signals": str(scratch / "meta.npz"), **risk}
        if float(risk.get("money_model") or 0) > 0:
            if not (scratch / "moneymodel.npz").exists():
                overlay = moneymodel.build_sizing(
                    sig, DATA, enter=enter, exit_=exit_, min_hold=hold,
                    stop_loss=float(risk.get("stop_loss") or 0.0),
                    trail_stop=float(risk.get("trail_stop") or 0.0), research=rbars)
                moneymodel.write_sizing(overlay, str(scratch / "moneymodel.npz"))
            brain["size_signals"] = str(scratch / "moneymodel.npz")

        py = launch.per_year(rbars, rstamps, [EXAM_YEAR], sig, brain_kwargs=brain)
        r = (py.get(EXAM_YEAR) or py.get(str(EXAM_YEAR))) or {}
        results[name] = {"return": r.get("return_pct"), "max_drawdown": r.get("max_drawdown"),
                         "trades": r.get("trades"), "minutes": round((time.time() - t0) / 60, 1)}
        print(f"{name}  {EXAM_YEAR}: {r.get('return_pct', 0):+.2%}  "
              f"DD {r.get('max_drawdown', 0):.1%}  trades {r.get('trades')}", flush=True)

    print(f"\n=== A110 EXAM ({EXAM_YEAR}, never seen by any arm) ===")
    print(f"  control (no decay) : {CONTROL['return']:+.2%}  "
          f"DD {CONTROL['max_drawdown']:.1%}  trades {CONTROL['trades']}")
    for name, r in results.items():
        print(f"  {name:19}: {r['return']:+.2%}  DD {r['max_drawdown']:.1%}  "
              f"trades {r['trades']}")
    wins = (results["wf23_ref"]["return"] or -9) > CONTROL["return"]
    print(f"  CONFIRMATION arm (reference features alone) beats the control: {wins}")
    print("a win buys a SECOND exam year, not a sealed reading - the rule that has now "
          "saved three sealed readings.")

    out = ROOT / "rnd" / f"a96b_reference_exam2_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A96b", "at": datetime.now(timezone.utc).isoformat(),
        "train_until": TRAIN_UNTIL, "exam_year": EXAM_YEAR, "arms": results,
        "control": CONTROL, "confirmation_wins": bool(wins),
        "exam1": {"year": 2025, "control": -0.0654, "ref": 0.0098, "ref_rec2": 0.2044,
                  "control_dd": 0.219, "ref_dd": 0.118, "ref_rec2_dd": 0.115},
        "prediction": "recency alone lost this exam by 30pp (A110b); if arm B collapses the exam-1 win was the recency lever finding 2025, if it holds the reference columns carry it",
        "features": "44 -> 52 columns (VIX pct/chg, NASDAQ 20d/60d, dollar 20d, oil 20d, 10y chg, 10y-2y curve), each lagged past its measured publication delay",
        "real_time_obtainable": "FRED daily, free, no key, non-revised series only",
        "rule": "a win buys a second exam year; 2026 not read here",
    }, indent=1, default=str), encoding="utf-8")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
