"""Joint numerical optimisation of the decision thresholds (Bayesian / TPE).

    PYTHONPATH=trading-system python research/system06/tools/numerical_optimization.py \
        [--trials 300] [--workers 4] [--resume]

WHAT THE OPERATOR ASKED (2026-09-04), and he is right that it is missing:

    "all these modules that contribute to the entry or exit decision have FIXED values
     - conviction at 0.75, and so on. There will be combinations of thresholds that
     produce better results than the current ones. Could we not run a mathematical
     simulation - there are libraries for this - that adjusts and varies these values?
     Not testing all the millions of combinations, but approximating: instead of moving
     one threshold digit by digit, a function that gets close to the winning formulas
     without having to try them all."

That is Bayesian optimisation, and the specific algorithm here is TPE (Tree-structured
Parzen Estimator, Bergstra et al. 2011) via Optuna. It builds a probability model of
which regions of the space produce good scores and spends its next evaluation where the
expected improvement is highest, so it converges in hundreds of trials on a space that
brute force could not finish in a lifetime.

WHAT WAS ALREADY HERE, so the gap is stated honestly rather than oversold:

  - the NN genome IS searched, by a genetic algorithm (autoloop._evolve: elite
    crossover plus mutation, with an explore rate so it cannot collapse),
  - the band (enter / exit / min_hold) IS swept, 72 combinations inside train(),
  - the risk layer is a HAND-WRITTEN LIST OF NINE TUPLES over four dimensions
    (autoloop.RISK_GRID: max_positions, position_fraction, stop_loss, trail_stop).

So of the twelve thresholds the shipping champion actually runs on, four have ever been
searched - along nine points of a coarse axis-aligned grid - and EIGHT have never been
searched at all. breadth_gate, regime_deploy, meta_margin, fng_min, money_model and the
rest were each set by a separate one-lever-at-a-time experiment and then frozen. Nothing
in this project's history has ever looked for an INTERACTION between two of them, and
gate_forensics has just shown that breadth_gate alone gates over half of 2025.

The operator's instinct is therefore correct, and the gap is larger than he supposed.

------------------------------------------------------------------------------------
THE HAZARD, AND THE DESIGN THAT ANSWERS IT
------------------------------------------------------------------------------------

A twelve-dimensional optimiser turned loose on eight years of history will find a
configuration that fits those eight years beautifully and means nothing. This project
has already been burned four times by selection optimism at a fraction of this power:
three headline results built on the luckiest seed, and a promotion bar derived from two
lucky draws that then blocked promotions for weeks. Handing TPE the whole record would be
the same mistake with a better engine.

So the years are SPLIT, and the split is the entire point of this file:

    FIT       2018-2023   the optimiser sees these; the objective is computed on them
    HOLDOUT   2024-2025   the optimiser never sees these at any point

Every trial runs all eight years anyway - one backtest produces the whole per-year
record - so the held-out score is recorded for free on every trial and used for
nothing. What that buys is the only question worth asking about an optimiser: does its
improvement TRANSFER? At the end this file prints the fit score and the held-out score
side by side, and their rank correlation across all trials. A high fit score with a flat
or negative held-out score is not a disappointing result, it is the correct result -
it says the surface is noise and the honest move is to stop.

That 2025 sits in the HELD-OUT half is deliberate and costly. It is the year we most
want to repair, and optimising on it directly is exactly how we would fool ourselves
about having repaired it. 2022 is the other quiet year and it IS in the fit half, so a
threshold set that genuinely understands quiet markets can still be found - and will
then have to prove it on a year it never saw.

2026 is not read here at all. Not as a readout, not "for shape". A search this powerful
has no business anywhere near the sealed window.

WHAT IS DELIBERATELY NOT OPTIMISED:

  - `enter`, the model's conviction bar. P46 and P42 between them just measured it as an
    interior optimum - it loses in both directions, with size compensating and without -
    and the meta-labelling overlay was gathered AT 0.75, so moving it would silently
    invalidate meta.npz. It is pinned, and round two rebuilds the overlay if it is ever
    unpinned.
  - `min_notional` and `max_participation`. These are not free parameters, they are
    statements about what the market can absorb. Optimising them would be optimising
    our own honesty.
  - `max_drawdown`, which is the mandate.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
OUT = ROOT / "rnd"
STUDY = "thresholds-v1"
STORAGE = f"sqlite:///{(OUT / 'optuna_thresholds.db').as_posix()}"

# The split. Written here, at the top, before any number is measured.
FIT_YEARS = (2018, 2019, 2020, 2021, 2022, 2023)
HOLDOUT_YEARS = (2024, 2025)


def _space(trial, base: dict) -> dict:
    """The threshold space. Ranges bracket the shipping values rather than replacing
    them: every one of these is a knob the system already runs on, and the champion's
    own setting sits inside every range - so trial 0, which is the champion enqueued
    verbatim, is a legal point and the whole study is anchored to something real."""
    return {
        "max_positions": trial.suggest_int("max_positions", 1, 6),
        "position_fraction": trial.suggest_float("position_fraction", 0.05, 0.80),
        "stop_loss": trial.suggest_float("stop_loss", 0.0, 0.20),
        "trail_stop": trial.suggest_float("trail_stop", 0.0, 0.30),
        "breadth_gate": trial.suggest_float("breadth_gate", 0.0, 0.60),
        "regime_deploy": trial.suggest_float("regime_deploy", 0.0, 1.0),
        "meta_margin": trial.suggest_float("meta_margin", 0.0, 0.05),
        "money_model": trial.suggest_float("money_model", 0.0, 1.0),
        "fng_min": trial.suggest_float("fng_min", 0.0, 50.0),
        "exit_": trial.suggest_float("exit_", 0.05, 0.50),
        "min_hold": trial.suggest_int("min_hold", 4, 288, log=True),
    }


def _champion_point(risk: dict, band: dict) -> dict:
    """The shipping champion expressed in the search space, enqueued as the first trial.

    Without this the study has no anchor: a best-of-300 number floating free of the
    incumbent cannot be compared to anything, and the comparison has to be made in the
    SAME units, on the same years, by the same code path - not against a figure copied
    from best.json that was computed by a different route months ago.
    """
    return {
        "max_positions": int(risk["max_positions"]),
        "position_fraction": float(risk["position_fraction"]),
        "stop_loss": float(risk.get("stop_loss") or 0.0),
        "trail_stop": float(risk.get("trail_stop") or 0.0),
        "breadth_gate": float(risk.get("breadth_gate") or 0.0),
        "regime_deploy": float(risk.get("regime_deploy") or 0.0),
        "meta_margin": float(risk.get("meta_margin") or 0.0),
        "money_model": float(risk.get("money_model") or 0.0),
        "fng_min": float(risk.get("fng_min") or 0.0),
        "exit_": float(band["exit_"]),
        "min_hold": int(band["min_hold"]),
    }


class Evaluator:
    """Holds the loaded market data so the cost is paid once per process, not per trial.

    Loading the bars takes about as long as a whole eight-year backtest, so a naive
    implementation would halve the throughput of the study for nothing.
    """

    def __init__(self):
        from quantlab_system06 import autoloop, launch, universe
        from quantlab_system06.dataset import Dataset

        self.autoloop, self.launch = autoloop, launch
        self.best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
        self.band = dict(self.best["band"])
        self.risk = dict(self.best["risk"])
        self.signals = str(ROOT / "signals.npz")

        symbols = universe.load()
        if not isinstance(symbols, list) or len(symbols) < 5:
            raise SystemExit(f"degenerate universe: {symbols!r} - run from the repo root "
                             f"with PYTHONPATH=trading-system")
        ds = Dataset(data_root=DATA, symbols=symbols, interval="15m")
        self.bars = ds.research()
        self.stamps = sorted({b.timestamp for s in self.bars.values() for b in s})
        self.years = tuple(sorted(set(FIT_YEARS) | set(HOLDOUT_YEARS)))

    def brain(self, point: dict) -> dict:
        """A point in the space -> the brain kwargs a backtest takes.

        The realism constants and the mandate ride along untouched: they are not part
        of the space and must not be silently dropped by rebuilding the dict.
        """
        kw = {
            "enter": float(self.band["enter"]),          # pinned, see the module docstring
            "exit_": float(point["exit_"]),
            "min_hold": int(point["min_hold"]),
            "max_drawdown": float(self.risk.get("max_drawdown") or 0.0),
            "min_notional": float(self.risk.get("min_notional") or 0.0),
            "max_participation": float(self.risk.get("max_participation") or 0.0),
        }
        for k in ("max_positions", "position_fraction", "stop_loss", "trail_stop",
                  "breadth_gate", "regime_deploy", "meta_margin", "money_model",
                  "fng_min"):
            kw[k] = point[k]
        kw["max_positions"] = int(kw["max_positions"])
        if self.band.get("meta_signals"):
            kw["meta_signals"] = self.band["meta_signals"]
        if kw["money_model"] > 0 and (ROOT / "moneymodel.npz").exists():
            kw["size_signals"] = str(ROOT / "moneymodel.npz")
        return kw

    def score(self, point: dict) -> dict:
        py = self.launch.per_year(self.bars, self.stamps, self.years, self.signals,
                                  brain_kwargs=self.brain(point))
        rets = {int(y): (py[y] or {}).get("return_pct") for y in py}
        fit = self.autoloop._consistency(
            {y: py[y] for y in py if int(y) in FIT_YEARS and py.get(y)})
        hold = self.autoloop._consistency(
            {y: py[y] for y in py if int(y) in HOLDOUT_YEARS and py.get(y)})
        dds = [(py[y] or {}).get("max_drawdown") for y in py]
        return {
            "fit": float(fit["score"]), "holdout": float(hold["score"]),
            "fit_min_year": fit["min_year"], "holdout_min_year": hold["min_year"],
            "returns": {str(y): rets[y] for y in sorted(rets) if rets[y] is not None},
            "worst_drawdown": max((d for d in dds if d is not None), default=None),
        }


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation between fit and held-out score, over every completed trial.

    The single number that says whether this study measured anything. If the ordering
    the optimiser learned on 2018-2023 carries no information about 2024-2025, then a
    high best-fit score is a description of the fit years and nothing more.
    """
    n = len(xs)
    if n < 8:
        return None
    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        for pos, i in enumerate(order):
            r[i] = float(pos)
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return (num / den) if den else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--startup", type=int, default=40,
                    help="random trials before TPE starts modelling the surface")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    OUT.mkdir(parents=True, exist_ok=True)
    sampler = optuna.samplers.TPESampler(seed=20260904, n_startup_trials=args.startup,
                                         multivariate=True, group=True)
    study = optuna.create_study(study_name=STUDY, storage=STORAGE, direction="maximize",
                                sampler=sampler, load_if_exists=True)

    if not args.report_only:
        ev = Evaluator()
        if not study.trials:
            # Trial 0 is the incumbent, so every later number has something to be
            # better THAN, measured the same way on the same years.
            study.enqueue_trial(_champion_point(ev.risk, ev.band))
            print("enqueued the shipping champion as trial 0", flush=True)

        def objective(trial):
            point = _space(trial, ev.risk)
            t0 = time.time()
            r = ev.score(point)
            for k in ("holdout", "fit_min_year", "holdout_min_year", "worst_drawdown"):
                trial.set_user_attr(k, r[k])
            trial.set_user_attr("returns", r["returns"])
            trial.set_user_attr("seconds", round(time.time() - t0, 1))
            print(f"  trial {trial.number:>4}  fit {r['fit']:+.4f}  "
                  f"holdout {r['holdout']:+.4f}  worst fit year {r['fit_min_year']:+.2%}  "
                  f"({time.time() - t0:.0f}s)", flush=True)
            return r["fit"]

        done = len([t for t in study.trials if t.state.name == "COMPLETE"])
        print(f"study `{STUDY}`: {done} trials done, running to {args.trials}\n"
              f"  FIT     {FIT_YEARS}\n  HOLDOUT {HOLDOUT_YEARS} (never seen by the sampler)",
              flush=True)
        # The trial budget is GLOBAL, not per process. Several workers share this study
        # through the SQLite storage, and passing `n_trials` to each of them would run
        # the budget once per worker - three workers quietly doing 900 trials instead of
        # 300, which on a four-minute evaluation is a day of compute nobody asked for.
        study.optimize(objective, callbacks=[optuna.study.MaxTrialsCallback(
            args.trials, states=(optuna.trial.TrialState.COMPLETE,))])

    # ---- the report ----------------------------------------------------------------
    comp = [t for t in study.trials if t.state.name == "COMPLETE" and t.value is not None]
    if not comp:
        print("no completed trials", file=sys.stderr)
        return 1
    fits = [t.value for t in comp]
    holds = [t.user_attrs.get("holdout") for t in comp]
    pairs = [(f, h) for f, h in zip(fits, holds) if h is not None]
    rho = _spearman([p[0] for p in pairs], [p[1] for p in pairs]) if pairs else None

    base = comp[0]           # trial 0: the champion, by construction
    best = max(comp, key=lambda t: t.value)
    # The point that would actually be shipped is chosen on the FIT score alone. Picking
    # the best held-out trial instead would turn the held-out half into a selection
    # input, which is the whole thing this design exists to prevent.
    print("\n" + "=" * 78)
    print(f"{len(comp)} trials.  TPE over 11 thresholds, fit on {FIT_YEARS[0]}-{FIT_YEARS[-1]}")
    print("=" * 78)
    for label, t in (("champion (trial 0)", base), ("best on FIT", best)):
        print(f"\n{label}")
        print(f"  fit score      {t.value:+.4f}")
        print(f"  holdout score  {t.user_attrs.get('holdout'):+.4f}   "
              f"(worst held-out year {t.user_attrs.get('holdout_min_year', float('nan')):+.2%})")
        print(f"  worst drawdown {t.user_attrs.get('worst_drawdown', float('nan')):.1%}")
        rets = t.user_attrs.get("returns") or {}
        print("  " + "  ".join(f"{y} {v:+.1%}" for y, v in sorted(rets.items())))
        if t is best:
            print("  params: " + ", ".join(f"{k}={v:.4g}" if isinstance(v, float)
                                           else f"{k}={v}" for k, v in sorted(t.params.items())))

    gain_fit = best.value - base.value
    gain_hold = ((best.user_attrs.get("holdout") or 0.0)
                 - (base.user_attrs.get("holdout") or 0.0))
    print(f"\nfit gain      {gain_fit:+.4f}")
    print(f"HELD-OUT gain {gain_hold:+.4f}   <- the only number that means anything")
    print(f"rank correlation fit vs held-out across all trials: "
          f"{'n/a' if rho is None else f'{rho:+.3f}'}")
    if gain_hold <= 0:
        print("\nVERDICT: the search improved the years it was allowed to see and did NOT\n"
              "transfer. That is a real finding about the surface, not a failed run: it\n"
              "says these thresholds are already at a point that generalises, and a\n"
              "better fit score is being bought with overfitting.")
    else:
        print("\nVERDICT: the improvement TRANSFERS to two years the optimiser never saw.\n"
              "That earns a reseed check and then one sealed readout - not adoption yet.")

    out = OUT / f"numerical_optimization_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(), "study": STUDY,
        "algorithm": "TPE (Tree-structured Parzen Estimator), Optuna, multivariate",
        "trials": len(comp), "fit_years": list(FIT_YEARS), "holdout_years": list(HOLDOUT_YEARS),
        "champion": {"params": base.params, "fit": base.value, **base.user_attrs},
        "best_on_fit": {"params": best.params, "fit": best.value, **best.user_attrs},
        "fit_gain": gain_fit, "holdout_gain": gain_hold, "rank_correlation": rho,
        "pinned": {"enter": "P42/P46 measured it as an interior optimum; meta.npz was "
                            "gathered at this value",
                   "min_notional/max_participation": "market realism, not free parameters",
                   "max_drawdown": "the mandate"},
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
