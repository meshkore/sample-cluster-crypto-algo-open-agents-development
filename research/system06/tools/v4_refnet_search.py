"""v4: the decision tree searched ON TOP OF the reference-features net.

Operator, 2026-09-07: "it is not only one parameter we have to vary, it is COMBINATIONS
of parameters. On one side the model, and then inside the decision tree a series of
modules that also have parameters and thresholds. The point is to play with combinations
of everything until we get a significantly winning option... keep going without rest, go
from less to more."

He is right, and it exposes a real gap in what has been measured. The v3 study varied 33
levers - but always above the SAME net. A96 then swapped the net (8 reference-market
columns added) and judged it under the CHAMPION'S thresholds, which were tuned for a
different net. A net and the decision tree above it are one joint object; measuring
either against the other's settings measures the pair badly. That is very likely part of
why the reference net halved the drawdown on one exam and collapsed on the next.

So: the same 33-lever TPE search, but against `_wf23_ref` - and that net makes the split
CLEAN IN A WAY NO PREVIOUS STUDY MANAGED:

    the net trained on          2018-2023   (train_until=2023, from A96b)
    thresholds fitted on        2018-2023
    HELD OUT, untouched by both 2024-2025
    sealed                      2026

In v3 the champion net had trained through 2025, so its "held-out" years were only
held out from the THRESHOLDS, never from the net. Here nothing - not a weight, not a
threshold, not a standardiser - has seen 2024 or 2025. It is the first genuinely clean
joint search this project has run.

`enter` is PINNED at the champion value here, deliberately. This net's meta overlay was
gathered at 0.75, so a lower entry would have no verdicts for the candidates it admits
and would read as a bad configuration rather than an untested one - the same failure that
made P46 measure a lever that did not exist. Unpinning it needs a wide overlay built from
THIS net's signals, which is phase two rather than a reason to delay phase one.

Coarse to fine, as asked: this is the coarse phase - the whole space, seeded from the
champion point, running until stopped.

    PYTHONPATH=trading-system python research/system06/tools/v4_refnet_search.py [--trials N]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
NET = ROOT / "_wf23_ref"
STUDY = "thresholds-v4-refnet"
STORAGE = f"sqlite:///{(ROOT / 'rnd' / 'optuna_thresholds.db').as_posix()}"
LIVE = ROOT / "v4_live.json"


def _nopt():
    spec = importlib.util.spec_from_file_location(
        "nopt", ROOT / "tools" / "numerical_optimization.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=4000)
    ap.add_argument("--startup", type=int, default=30)
    ap.add_argument("--seeds", type=int, default=64)
    args = ap.parse_args()

    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    nopt = _nopt()

    if not (NET / "signals.npz").exists():
        sys.exit(f"{NET}/signals.npz missing - this study needs the A96b net")

    ev = nopt.Evaluator(nopt.FIT_YEARS, nopt.HOLDOUT_YEARS,
                        with_enter=False, net_dir=NET)
    names = [n for n in nopt.SPACE if n != "enter"]
    missing = {k: f for k, f in nopt.NEEDS_FILE.items()
               if not (NET / f).exists() and not (ROOT / f).exists()}
    names = [n for n in names if n not in missing]

    seed = 20260907 + os.getpid()
    sampler = optuna.samplers.TPESampler(seed=seed, n_startup_trials=args.startup,
                                         multivariate=True, group=True,
                                         constant_liar=True)
    study = optuna.create_study(study_name=STUDY, storage=STORAGE,
                                direction="maximize", sampler=sampler,
                                load_if_exists=True)

    anchor = nopt._champion_point_full(ev.risk, ev.band, names)
    if not study.trials:
        for p in nopt.seed_points(anchor, names, n=args.seeds):
            study.enqueue_trial(p)
        print(f"enqueued the champion + {args.seeds - 1} perturbations", flush=True)

    done = len([t for t in study.trials if t.state.name == "COMPLETE"])
    print(f"study `{STUDY}`  net {NET.name}  seed {seed}\n"
          f"  {len(names)} levers (enter pinned at {ev.band['enter']}; this net's overlay "
          f"was gathered there)\n"
          f"  NET trained   <= 2023      thresholds fitted 2018-2023\n"
          f"  HELD OUT      2024, 2025   seen by neither the net nor the thresholds\n"
          f"  {done} trials done, running to {args.trials}", flush=True)

    def objective(trial):
        point = nopt._space(trial, ev.risk, names)
        point["enter"] = float(ev.band["enter"])
        t0 = time.time()
        r = ev.score(point)
        for k in ("holdout", "fit_min_year", "holdout_min_year", "worst_drawdown",
                  "all_positive", "inert", "trades", "mandate_years", "months_won",
                  "fit_months_won", "fit_mandate_years", "fit_years_n",
                  "fit_worst_drawdown", "holdout_worst_drawdown"):
            if k in r:
                trial.set_user_attr(k, r[k])
        trial.set_user_attr("returns", r["returns"])
        trial.set_user_attr("net", NET.name)
        if r["inert"]:
            print(f"  trial {trial.number:>4}  INERT ({time.time() - t0:.0f}s)", flush=True)
        else:
            print(f"  trial {trial.number:>4}  fit {r['fit']:+.4f}  "
                  f"HELD-OUT {r['holdout']:+.4f}  "
                  f"yrs>30% {r.get('fit_mandate_years')}/{r.get('fit_years_n')}  "
                  f"maxDD {(r.get('fit_worst_drawdown') or 0):5.1%}  "
                  f"({time.time() - t0:.0f}s)", flush=True)
        return r["fit"]

    def heartbeat(study_, trial_):
        try:
            comp = [t for t in study_.trials
                    if t.state.name == "COMPLETE" and t.value is not None]
            if not comp:
                return
            best = max(comp, key=lambda t: t.value)
            LIVE.write_text(json.dumps({
                "at": datetime.now(timezone.utc).isoformat(),
                "study": STUDY, "net": NET.name, "levers": len(names),
                "trials_done": len(comp), "trials_target": args.trials,
                "leader": {"trial": best.number, "fit": best.value,
                           "holdout": best.user_attrs.get("holdout"),
                           "returns": best.user_attrs.get("returns"),
                           "worst_drawdown": best.user_attrs.get("fit_worst_drawdown")},
                "note": "net trained <=2023 and thresholds fitted 2018-2023, so 2024-2025 "
                        "are held out from BOTH. 2026 sealed and not read.",
            }, indent=1, default=str), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            print(f"    (heartbeat failed: {exc})", flush=True)

    study.optimize(objective, callbacks=[
        heartbeat,
        optuna.study.MaxTrialsCallback(
            args.trials, states=(optuna.trial.TrialState.COMPLETE,))])
    return 0


if __name__ == "__main__":
    sys.exit(main())
