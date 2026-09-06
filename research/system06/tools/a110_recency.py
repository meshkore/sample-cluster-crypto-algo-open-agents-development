"""A110: recency-weighted training - the operator's own hypothesis, measured alone.

Operator, 2026-09-05: "the market evolves with time, depending on the volume of
capital we have, depending on what the algorithms learn... something that worked in
2020 did not work in 2025." Exponential decay by sample age keeps every bar but lets
the net care more about the recent regime - the honest version of "use the most
recent data", since truncating history would just throw samples away.

Judged by the instrument that has now proved itself twice (A109 agreed with the
sealed year; A112/A113 correctly refused an ensemble that looked like a winner after
one exam): walk-forward, train_until=2024, exam on 2025 alone, champion band and risk
verbatim, ONE lever moved.

    control    single 192x3, no recency   ALREADY MEASURED: 2025 -6.54% DD 21.9% 72 trades
    arm A      half-life 2 years
    arm B      half-life 4 years

Two half-lives because a single one cannot tell "recency does not help" from "that
particular half-life was wrong" - and because the pair shows the DIRECTION of the
response, which one point cannot. Both arms are the same seed and recipe as the
control, so any difference is the decay and nothing else.

A win here does NOT buy a sealed reading: it buys a second exam year, exactly as the
ensemble had to earn. That rule cost the ensemble its adoption and is why it exists.

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a110_recency.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
TRAIN_UNTIL = 2024
EXAM_YEAR = 2025
CONTROL = {"return": -0.0654, "max_drawdown": 0.219, "trades": 72,
           "source": "rnd/a109_walkforward_2026-09-05.json, arm wf192x3"}
ARMS = {
    "wf_recency_hl2": {"recency_half_life": 2.0},
    "wf_recency_hl4": {"recency_half_life": 4.0},
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

    single, ens = results["wf23_single"], results["wf23_ens5"]
    wins = (ens["return"] or -9) > (single["return"] or -9)
    print(f"\n=== SECOND EXAM ({EXAM_YEAR}, never seen by either arm) ===")
    print(f"  single    : {single['return']:+.2%}  DD {single['max_drawdown']:.1%}  trades {single['trades']}")
    print(f"  ensemble5 : {ens['return']:+.2%}  DD {ens['max_drawdown']:.1%}  trades {ens['trades']}")
    print(f"  ensemble wins the second exam: {wins}")
    print("2 of 2 earns the adoption attempt (retrain through 2025, ONE sealed reading);"
          " anything less does not." if wins else
          "1 of 2: the 2025 win was probably the draw; more exam years, no sealed reading.")

    out = ROOT / "rnd" / f"a110_recency_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A110", "at": datetime.now(timezone.utc).isoformat(),
        "train_until": TRAIN_UNTIL, "exam_year": EXAM_YEAR, "arms": results,
        "control": CONTROL, "recency_wins": bool(wins),
        "rule": "a win buys a second exam year; 2026 not read here",
    }, indent=1, default=str), encoding="utf-8")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
