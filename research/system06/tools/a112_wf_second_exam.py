"""A112: the ensemble's SECOND independent walk-forward exam, before any sealed spend.

The first exam (A106-wf, 2026-09-05) was the first candidate change ever to win a
walk-forward A/B: train_until=2024, exam 2025 - single seed -6.54% / DD 21.9% / 72
trades vs ensemble-of-5 +6.46% / DD 16.4% / 45 trades. Thirteen points with LOWER
drawdown and FEWER trades, which is the signature of variance reduction rather than
of luck.

But it is one exam year, and this project has now watched three candidates carry a
research-side win into the sealed year and lose it. The 2026-08-29 mandate says
walk-forward "across all research years", not once. So before the ensemble earns the
adoption attempt (retrain on everything through 2025, then ONE sealed 2026 reading),
it must repeat the trick on a second, independent year:

    train on <= 2023, examine on 2024 alone - both arms, same seed, same recipe.

2 of 2 earns the adoption attempt. 1 of 2 means the 2025 win was probably the draw,
and the honest next step is more exam years, not a sealed reading. Kill criterion
written before the number, as always.

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a112_wf_second_exam.py
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
ARMS = {
    "wf23_single": {"ensemble": 1},
    "wf23_ens5": {"ensemble": 5},
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
        print(f"\n=== {name}: ensemble={arm['ensemble']}, train_until={TRAIN_UNTIL} ===",
              flush=True)
        if not (scratch / "oracle_net.pt").exists():
            train.train(data_root=DATA, symbols=symbols, threshold=cfg["threshold"],
                        window=cfg["window"], epochs=cfg["epochs"], lr=cfg["lr"],
                        dropout=cfg["dropout"], out_dir=str(scratch), seed=91002,
                        uniqueness_weighting=float(cfg.get("uniqueness_weighting", 0.0)),
                        enter=enter, exit_=exit_, min_hold=hold,
                        channels=(192, 192, 192), train_until=TRAIN_UNTIL,
                        ensemble=arm["ensemble"])
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

    single, ens = results["wf23_single"], results["wf23_ens5"]
    wins = (ens["return"] or -9) > (single["return"] or -9)
    print(f"\n=== SECOND EXAM ({EXAM_YEAR}, never seen by either arm) ===")
    print(f"  single    : {single['return']:+.2%}  DD {single['max_drawdown']:.1%}  trades {single['trades']}")
    print(f"  ensemble5 : {ens['return']:+.2%}  DD {ens['max_drawdown']:.1%}  trades {ens['trades']}")
    print(f"  ensemble wins the second exam: {wins}")
    print("2 of 2 earns the adoption attempt (retrain through 2025, ONE sealed reading);"
          " anything less does not." if wins else
          "1 of 2: the 2025 win was probably the draw; more exam years, no sealed reading.")

    out = ROOT / "rnd" / f"a112_wf_second_exam_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A112", "at": datetime.now(timezone.utc).isoformat(),
        "train_until": TRAIN_UNTIL, "exam_year": EXAM_YEAR, "arms": results,
        "first_exam": {"year": 2025, "single": -0.0654, "ensemble5": 0.0646,
                       "source": "rnd/a106_wf_ensemble_2026-09-05.json"},
        "ensemble_wins": bool(wins),
        "rule": "2 of 2 earns the adoption attempt; 2026 not read here",
    }, indent=1, default=str), encoding="utf-8")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
