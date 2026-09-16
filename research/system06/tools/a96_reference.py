"""A96: give the net the markets AROUND crypto - VIX, NASDAQ, dollar, oil, yields, curve.

Operator, 2026-09-07: "develop the data route... give it more information", with the
constraint that shapes every choice: "make sure that whatever it trains on is
information we will be able to obtain in real time for executions from today into the
future."

Eight new columns, all from FRED (free, no key, NOT revised after publication), each
lagged by MORE than its own measured publication delay so a bar can only read a number
the live system could genuinely have fetched. See system006_oracle_net_15m/reference.py for
the lag table and why it is per series rather than global.

Why this experiment and not another. Five improvement routes were measured and refused
this week - 1,668 threshold combinations, a deeper net, a 5-seed ensemble, recency
weighting, a vector memory - and their common shape is that all five rearranged the
SAME information. The champion's 44 features are all derived from the price of 27
crypto symbols; the book has never known whether the dollar was rising, whether credit
was tightening, or whether equity risk appetite had turned. This is the first
experiment that adds information rather than rearranging it.

Judged by the instrument that has earned it (A109 agreed with the sealed year; A112,
A113 and A110b each refused a candidate that had won its first exam): walk-forward,
train_until=2024, exam on 2025 alone, champion band and risk verbatim, ONE thing
changed - the feature matrix goes from 44 columns to 52.

    control    44 columns, no reference   ALREADY MEASURED: 2025 -6.54% DD 21.9% 72 trades
    arm A      52 columns, reference features ON
    arm B      52 columns, reference ON, plus recency half-life 2y

Arm B exists because A110 showed the recency lever helps 2025 specifically (+1.16% vs
-6.54%) before failing its own confirmation on 2024 - and the operator's instruction is
to try combinations rather than only single levers once each piece is understood. It is
EXPLORATORY: only arm A can earn the confirmation exam, because only arm A isolates the
new information. If B beats A it starts its own series.

A win buys a SECOND exam year, never a sealed reading. That rule has now saved three
sealed readings from candidates that won their first exam and lost the next.

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a96_reference.py
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
    "wf_ref": {"reference_features": True, "recency_half_life": 0.0},
    "wf_ref_rec2": {"reference_features": True, "recency_half_life": 2.0},
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
    wins = (results["wf_ref"]["return"] or -9) > CONTROL["return"]
    print(f"  CONFIRMATION arm (reference features alone) beats the control: {wins}")
    print("a win buys a SECOND exam year, not a sealed reading - the rule that has now "
          "saved three sealed readings.")

    out = ROOT / "rnd" / f"a96_reference_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A96", "at": datetime.now(timezone.utc).isoformat(),
        "train_until": TRAIN_UNTIL, "exam_year": EXAM_YEAR, "arms": results,
        "control": CONTROL, "confirmation_wins": bool(wins),
        "features": "44 -> 52 columns (VIX pct/chg, NASDAQ 20d/60d, dollar 20d, oil 20d, 10y chg, 10y-2y curve), each lagged past its measured publication delay",
        "real_time_obtainable": "FRED daily, free, no key, non-revised series only",
        "rule": "a win buys a second exam year; 2026 not read here",
    }, indent=1, default=str), encoding="utf-8")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
