"""A110b: recency's SECOND exam - the confirmation the ensemble never survived.

Exam 1 (train <= 2024, exam 2025), against the measured no-decay control:

    control (no decay)   -6.54%   DD 21.9%   72 trades
    half-life 4 years    -6.30%   DD 17.7%   71 trades    <- mild decay ~ control
    half-life 2 years    +1.16%   DD 15.6%   86 trades    <- WON, and by 7.7 points

Two things make this stronger than the ensemble's exam-1 win. The response is
ORDERED with the lever - weak decay reproduces the control almost exactly, strong
decay improves it - which a coin flip does not do; and the win comes with LOWER
drawdown (15.6% vs 21.9%), so it is not the usual "more risk, more return".

None of that is proof. The ensemble also won its first exam by 13 points and then
lost the next two, and the rule written after that episode is absolute: a win buys a
SECOND EXAM YEAR, never a sealed reading. This is that exam.

    CONFIRMATION arm   half-life 2y, train <= 2023, exam 2024
                       control ALREADY MEASURED: +22.36% DD 17.9% 308 trades
    EXPLORATORY arm    half-life 1y, same split

The exploratory arm is here because exam 1 showed a DIRECTION (shorter half-life,
better result) and one more point says whether it continues or turns over. It is
explicitly NOT eligible for adoption on this run: if 1y wins it starts its own exam
series from zero rather than inheriting 2y's. Writing that down before the numbers
exist is the whole reason the ensemble cost us nothing.

Adjudication, pre-registered: half-life 2y earns the adoption attempt only by beating
+22.36% here. 1 of 2 sends it to a third exam like everything else.

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a110b_recency_exam2.py
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
    "wf23_recency_hl2": {"recency_half_life": 2.0},   # CONFIRMATION - can earn adoption
    "wf23_recency_hl1": {"recency_half_life": 1.0},   # EXPLORATORY - starts its own series
}


def main() -> int:
    from quantlab_system06 import autoloop, infer, launch, moneymodel, train, universe
    from quantlab_system06 import meta as metalabel
    from quantlab_system06.dataset import Dataset

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

    print(f"\n=== A110b EXAM 2 ({EXAM_YEAR}, never seen by any arm) ===")
    print(f"  control (no decay)     : {CONTROL['return']:+.2%}  "
          f"DD {CONTROL['max_drawdown']:.1%}  trades {CONTROL['trades']}")
    for name, r in results.items():
        tag = "CONFIRMATION" if name.endswith("hl2") else "exploratory"
        print(f"  {name:23}: {r['return']:+.2%}  DD {r['max_drawdown']:.1%}  "
              f"trades {r['trades']}   [{tag}]")
    wins = (results["wf23_recency_hl2"]["return"] or -9) > CONTROL["return"]
    print(f"  CONFIRMATION arm (half-life 2y) beats the control: {wins}")
    print("2 of 2 - the 2y half-life earns the adoption attempt (retrain through 2025, "
          "ONE sealed 2026 reading)." if wins else
          "1 of 2: exam 1 was probably the draw. No sealed reading. The exploratory arm "
          "adopts nothing here whatever it did - it starts its own series.")

    out = ROOT / "rnd" / f"a110b_recency_exam2_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A110b", "at": datetime.now(timezone.utc).isoformat(),
        "train_until": TRAIN_UNTIL, "exam_year": EXAM_YEAR, "arms": results,
        "control": CONTROL, "confirmation_wins": bool(wins),
        "exam1": {"year": 2025, "control": -0.0654, "hl2": 0.0116, "hl4": -0.0630},
        "exploratory_arm": "wf23_recency_hl1 - starts its own series, adopts nothing here",
        "rule": "a win buys a second exam year; 2026 not read here",
    }, indent=1, default=str), encoding="utf-8")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
