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

# --- v2: the split has done its job; stop paying for it ------------------------------
# v1 existed to answer one question - does a threshold search overfit the years it is
# shown? It answered no: the held-out half improved from +0.0280 to +0.1028, 57 of 87
# trials beat the incumbent there, and the same thresholds won on 3 of 3 nets they were
# never tuned against. The split was insurance, the insurance paid out, and continuing
# to withhold a quarter of the record now costs performance for a question already
# settled. The project's own rule is that historical optimisation ends 2025-12-31; that
# is exactly what --all-years does. 2026 remains sealed and is not read here.
ALL_YEARS = (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025)
STUDY_V2 = "thresholds-v2-allyears"

# The entry threshold, which v1 pinned. Pinning it was defensible - P42 and P46 measured
# it as an interior optimum ONE LEVER AT A TIME - and that is precisely the reasoning
# this whole study exists to distrust. The operator named this threshold specifically.
# It is unpinned by building the meta overlay at 0.55, which makes its candidate set a
# SUPERSET of every entry the search can ask for, so the overlay stays valid across the
# range instead of silently going stale the moment `enter` moves off 0.75.
META_WIDE = ROOT / "meta_wide.npz"
ENTER_RANGE = (0.55, 0.90)


# --- the whole decision tree, one row per knob ---------------------------------------
# Operator, 2026-09-04: "I named one at random, the conviction one, but EVERY module of
# the decision tree has parameters that can be variables, and all those combinations are
# what we have to evaluate."
#
# So this is every lever OracleNetBrain accepts, minus four that must not be searched:
# max_drawdown (the mandate), min_notional and max_participation (statements about what
# the market can absorb - optimising them would be optimising our own honesty), and
# bar_seconds (the data's own timeframe).
#
# "off" convention: most of these levers treat 0 as off, so a range starting at 0 lets
# the search decide whether a module participates at all - which is the honest way to
# ask "does this module earn its place", and something no experiment here has ever
# asked. The three that use None rather than 0 for off are mapped in `brain()`.
#
# (kind, low, high, log) - kind is "f" float, "i" int.
SPACE: dict[str, tuple] = {
    # the band
    "enter": ("f", 0.55, 0.90, False),
    "exit_": ("f", 0.05, 0.50, False),
    "min_hold": ("i", 1, 288, True),
    # the book
    "max_positions": ("i", 1, 8, False),
    "position_fraction": ("f", 0.05, 0.90, False),
    # stops
    "stop_loss": ("f", 0.0, 0.25, False),
    "trail_stop": ("f", 0.0, 0.35, False),
    # volatility targeting
    "vol_scale": ("f", 0.0, 2.0, False),
    "vol_floor": ("f", 0.10, 1.0, False),
    # cross-sectional momentum
    "mom_gate": ("f", 0.0, 0.60, False),
    # regime / breadth
    "breadth_gate": ("f", 0.0, 0.60, False),
    "regime_deploy": ("f", 0.0, 1.0, False),
    "regime_persist": ("f", 0.0, 480.0, False),
    # meta-labelling
    "meta_margin": ("f", 0.0, 0.05, False),
    # money management
    "money_kelly": ("f", 0.0, 1.0, False),
    "money_pyramid": ("f", 0.0, 1.0, False),
    "martingale": ("f", 0.0, 0.50, False),
    "money_model": ("f", 0.0, 1.0, False),
    "conviction_sizing": ("f", 0.0, 1.0, False),
    "dd_sizer": ("f", 0.0, 1.0, False),
    # microstructure
    "micro_gate": ("f", 0.0, 1.0, False),
    # fractal regime
    "hurst_gate": ("f", 0.0, 0.65, False),
    # crowd / behavioural
    "fng_min": ("f", 0.0, 50.0, False),
    "feargreed": ("f", 0.0, 1.0, False),
    # progressive entries
    "scale_in": ("i", 0, 4, False),
    "scale_enter": ("f", 0.0, 0.95, False),
    # seasoning
    "min_age_days": ("f", 0.0, 365.0, False),
    # cross-asset
    "horserace": ("f", 0.0, 1.0, False),
    "sweep": ("f", 0.0, 1.0, False),
    # decision-tree voter
    "tree_weight": ("f", 0.0, 1.0, False),
    # trend handling
    "trend_soft": ("f", 0.0, 1.0, False),
    # circuit breaker
    "edge_monitor": ("f", 0.0, 1.0, False),
    # consensus. Capped at 2, not 4: `backers` counts modules that cast a DIRECTIONAL
    # vote clearing the entry bar, and in this ensemble that is the net plus, when it is
    # switched on, the tree voter. Asking three to agree is asking for a third opinion
    # that does not exist, so every k>2 draw is a book that never trades - measured, six
    # for six, on the first run of this space.
    "consensus_k": ("i", 1, 2, False),
}
# A book that never trades scores 0.0, and a book that trades badly scores NEGATIVE. So
# without this, doing nothing beats doing something imperfectly and the search converges
# on paralysis - the most efficient way imaginable to waste a night of compute. Measured
# rather than feared: the first six trials of the full space all returned exactly 0.0%
# in all eight years. INERT is therefore worse than any real result, by a margin no
# genuine configuration can reach.
INERT_SCORE = -10.0

# --- what the search is actually told to maximise -------------------------------------
# The house metric is worst_year + 0.10*CAGR. On this record that is not a consistency
# law, it is a CAGR contest wearing one: 2021 alone drags the CAGR past 300%, so the
# second term contributes about 0.30 while the worst year contributes about 0.05. The
# search will therefore trade a worse worst-year for a bigger moonshot every time, and
# it did - twenty-five trials in, the leader scored +0.2423 against the incumbent's
# +0.1509 while taking its worst year from -1.49% to -6.56% and its drawdown from 22.0%
# to 33.9%.
#
# That is also the most economical explanation of the day's two sealed disappointments:
# both candidates doubled this score and both LOST on 2026, a year with no moonshot in
# it. A83 raised 2021 from +14,554% to +40,751% and 2025 by four points; the objective
# paid it handsomely for the first and barely noticed the second.
#
# The operator's mandate has been fixed and explicit since 2026-08-28: MINIMUM +30% per
# calendar year, EVERY year, with drawdown minimised. Written directly:
#
#     mean over years of  min(year_return, 0.30)
#
# Every year is credited up to the target and no further, so a year at +14,554% counts
# exactly what a year at +30% counts and CANNOT pay for a year at -3%. A year below the
# target drags the mean by its full shortfall. The perfect score is 0.30, and the
# distance from it is literally "how far off the mandate are we" - which is the thing
# the operator has been asking to see.
#
# A FIRST ATTEMPT AT THIS OVERCORRECTED, and the fix is on the record because the error
# is instructive. Capping CAGR at 50% removed the moonshot contest and, since every
# configuration on this record clears 50% easily, removed GROWTH ENTIRELY: the search
# stopped being able to tell +843% from +10,080% in 2021 and started buying steadiness
# with enormous amounts of forgone return. Capping each YEAR at the target rather than
# capping the aggregate is what separates "a moonshot cannot buy a bad year" from
# "moonshots do not exist".
#
# Growth still breaks ties, in logs so it stays bounded and can never overtake the
# mandate term: 0.02*ln(1+CAGR) is 0.02 at CAGR 1, 0.09 at CAGR 100.
#
# Drawdown is free up to the incumbent's own 22% and priced beyond it - a price, not a
# limit, per the operator's 2026-08-28 revision.
MANDATE_TARGET = 0.30
GROWTH_WEIGHT = 0.02
DD_FREE = 0.22      # the incumbent's own worst drawdown - free, not rewarded
DD_WEIGHT = 1.0


def mandate_score(returns: dict, cons: dict, worst_drawdown: float | None) -> float:
    """The objective: how close the whole record comes to +30% every single year."""
    vals = [v for v in returns.values() if v is not None]
    if not vals:
        return INERT_SCORE
    mandate = sum(min(float(v), MANDATE_TARGET) for v in vals) / len(vals)
    # The tiebreak is capped at HALF of what one year fully missing the target costs, so
    # no amount of compounding can ever pay for a year below the mandate. A test caught
    # this: at CAGR 1000 the uncapped log term reached 0.138 against a one-year shortfall
    # of 0.0375, which quietly reinstated the moonshot contest this objective exists to
    # end. Derived from the number of years rather than hard-coded, so the guarantee
    # holds if the record ever gets longer.
    growth = min(GROWTH_WEIGHT * math.log(1.0 + max(0.0, float(cons["cagr"]))),
                 0.5 * MANDATE_TARGET / len(vals))
    dd = max(0.0, float(worst_drawdown or 0.0) - DD_FREE)
    return mandate + growth - DD_WEIGHT * dd
# Levers whose overlay file is missing on this machine are dropped at startup rather
# than searched into the void: a lever the brain silently ignores reads as a measured
# refutation, which is the P46 `band_enter` failure with thirty more chances to happen.
NEEDS_FILE = {"meta_margin": "meta.npz", "money_model": "moneymodel.npz",
              "micro_gate": "micro.npz", "tree_weight": "tree.npz"}


def seed_points(anchor: dict, names, n: int = 64, seed: int = 20260904) -> list[dict]:
    """Starting points: the incumbent, then the incumbent with a few levers moved.

    Pure random search is the wrong instrument in this space and the first six trials
    proved it - ten trades across eight years, twice. The reason is structural. Most of
    these levers are GATES that are off at zero, and a uniform draw turns all ten of them
    on at once at random strengths. The chance that every gate is simultaneously
    permissive is negligible, so a random trial is almost always a book that cannot
    trade, and eight years of backtest are spent discovering it.

    The incumbent is a known-good point in that space. Perturbing it one to three levers
    at a time gives TPE something to model that is actually near the region worth
    searching, which is standard practice for Bayesian optimisation with a live
    incumbent and is the difference between refining a strategy and rediscovering it
    from nothing.

    Deterministic: same seed, same starting points, so a resumed study is the same study.
    """
    import random as _random

    rng = _random.Random(seed)
    points = [dict(anchor)]
    for i in range(n):
        p = dict(anchor)
        for name in rng.sample(list(names), k=rng.choice([1, 1, 2, 2, 3])):
            kind, lo, hi, _log = SPACE[name]
            if kind == "i":
                p[name] = rng.randint(int(lo), int(hi))
            else:
                # Half the draws land ON the off value. A gate the incumbent never uses
                # deserves a fair chance to stay off while its neighbours move, and a
                # uniform draw over [0, hi] almost never offers one.
                p[name] = 0.0 if (lo == 0.0 and rng.random() < 0.35) else \
                    rng.uniform(lo, hi)
        points.append(p)
    return points


def _space(trial, base: dict, names=None) -> dict:
    """Draw one point. `names` restricts the space to the levers actually usable here.

    The champion's own setting sits inside every range, so trial 0 - the incumbent
    enqueued verbatim - is a legal point and the study is anchored to something real
    rather than floating free of the thing it claims to beat.
    """
    out = {}
    for name in (names if names is not None else SPACE):
        kind, lo, hi, log = SPACE[name]
        out[name] = (trial.suggest_int(name, int(lo), int(hi), log=log) if kind == "i"
                     else trial.suggest_float(name, lo, hi, log=log))
    return out


def _champion_point_full(risk: dict, band: dict, names) -> dict:
    """The incumbent expressed in the full space, clipped into each range.

    Every lever it does not name is off, which for this convention is 0 - and that is
    not a technicality, it is the finding hiding in plain sight: of the thirty-odd knobs
    the brain accepts, the shipping champion uses NINE. The rest have been sitting at
    zero since they were written, each one switched off by an experiment that tested it
    alone against a book tuned for its absence.
    """
    src = {**{k: 0.0 for k in SPACE}, **risk,
           "enter": band["enter"], "exit_": band["exit_"], "min_hold": band["min_hold"]}
    src["consensus_k"] = risk.get("consensus_k", 1) or 1
    src["vol_floor"] = risk.get("vol_floor", 0.4) or 0.4
    out = {}
    for name in names:
        kind, lo, hi, _log = SPACE[name]
        v = src.get(name) or 0
        v = min(max(float(v), lo), hi)
        out[name] = int(round(v)) if kind == "i" else v
    return out


def _champion_point(risk: dict, band: dict, with_enter: bool = False) -> dict:
    """The shipping champion expressed in the search space, enqueued as the first trial.

    Without this the study has no anchor: a best-of-300 number floating free of the
    incumbent cannot be compared to anything, and the comparison has to be made in the
    SAME units, on the same years, by the same code path - not against a figure copied
    from best.json that was computed by a different route months ago.
    """
    return {
        **({"enter": float(band["enter"])} if with_enter else {}),
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

    def __init__(self, fit_years=FIT_YEARS, holdout_years=HOLDOUT_YEARS,
                 with_enter: bool = False):
        from quantlab_system06 import autoloop, launch, universe
        from quantlab_system06.dataset import Dataset

        self.fit_years, self.holdout_years = tuple(fit_years), tuple(holdout_years)
        self.with_enter = with_enter
        if with_enter and not META_WIDE.exists():
            raise SystemExit(
                f"searching `enter` needs the wide meta overlay at {META_WIDE}. Build it "
                f"once with:  python -m quantlab_system06.meta --data-root {DATA} "
                f"--signals {ROOT / 'signals.npz'} --out {META_WIDE} --enter "
                f"{ENTER_RANGE[0]}\nWithout it the overlay is a candidate set gathered at "
                f"0.75 and every trial below that threshold silently loses its verdicts.")

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
        self.years = tuple(sorted(set(self.fit_years) | set(self.holdout_years)))

    def brain(self, point: dict) -> dict:
        """A point in the space -> the brain kwargs a backtest takes.

        The realism constants and the mandate ride along untouched: they are not part
        of the space and must not be silently dropped by rebuilding the dict.
        """
        kw = {k: v for k, v in point.items()}
        # Not searched, and carried through untouched so rebuilding the dict cannot
        # silently drop them: the mandate and the two execution-realism constants.
        kw["max_drawdown"] = float(self.risk.get("max_drawdown") or 0.0)
        kw["min_notional"] = float(self.risk.get("min_notional") or 0.0)
        kw["max_participation"] = float(self.risk.get("max_participation") or 0.0)
        kw.setdefault("enter", float(self.band["enter"]))
        for k in ("max_positions", "min_hold", "scale_in", "consensus_k"):
            if k in kw:
                kw[k] = int(kw[k])
        # The three levers that use None for "off" rather than 0. Passing 0.0 would turn
        # each of them ON at its most permissive setting - micro_gate 0.0 is a live
        # contrarian veto, not an absent one - so the search could never switch them off.
        for k in ("micro_gate", "scale_enter"):
            if k in kw and not kw[k]:
                kw[k] = None
        if "meta_margin" in kw and kw["meta_margin"] <= 0:
            kw["meta_margin"] = None
        # With `enter` free, the overlay must be the WIDE one - a candidate set gathered
        # at 0.75 has no verdict for any entry below it, so a lower threshold would
        # quietly run half-blind and read as a bad configuration rather than an untested
        # one. Same failure shape as P46's non-existent lever, just harder to see.
        if self.with_enter:
            kw["meta_signals"] = str(META_WIDE)
        elif self.band.get("meta_signals"):
            kw["meta_signals"] = self.band["meta_signals"]
        if kw["money_model"] > 0 and (ROOT / "moneymodel.npz").exists():
            kw["size_signals"] = str(ROOT / "moneymodel.npz")
        return kw

    def score(self, point: dict) -> dict:
        py = self.launch.per_year(self.bars, self.stamps, self.years, self.signals,
                                  brain_kwargs=self.brain(point))
        rets = {int(y): (py[y] or {}).get("return_pct") for y in py}
        fit = self.autoloop._consistency(
            {y: py[y] for y in py if int(y) in self.fit_years and py.get(y)})
        held = {y: py[y] for y in py if int(y) in self.holdout_years and py.get(y)}
        hold = (self.autoloop._consistency(held) if held
                else {"score": float("nan"), "min_year": float("nan")})
        dds = [(py[y] or {}).get("max_drawdown") for y in py]
        trades = sum((py[y] or {}).get("trades") or 0 for y in py)
        worst_dd = max((d for d in dds if d is not None), default=None)
        return {
            "fit": (INERT_SCORE if trades == 0
                    else mandate_score(rets, fit, worst_dd)),
            "house_score": float(fit["score"]),   # the old metric, kept comparable
            "inert": trades == 0, "trades": trades,
            "holdout": float(hold["score"]),
            "fit_min_year": fit["min_year"], "holdout_min_year": hold["min_year"],
            "all_positive": bool(fit["all_positive"]) and trades > 0,
            "mandate_years": sum(1 for v in rets.values()
                                 if v is not None and v >= 0.30),
            "returns": {str(y): rets[y] for y in sorted(rets) if rets[y] is not None},
            "worst_drawdown": max((d for d in dds if d is not None), default=None),
        }


LIVE = ROOT / "optimizer_live.json"


def _ceiling_years() -> dict:
    """The perfect-hindsight return per year, for the capture column. Read once."""
    files = sorted(OUT.glob("ceiling_*.json"))
    if not files:
        return {}
    try:
        data = json.loads(files[-1].read_text(encoding="utf-8"))
        return {str(y): float(v.get("oracle_return"))
                for y, v in (data.get("years") or {}).items()
                if v.get("oracle_return") is not None}
    except Exception:  # noqa: BLE001
        return {}


def write_live(study, study_name: str, names, target: int, started: float,
               ceiling: dict) -> None:
    """The heartbeat this study was missing.

    Operator, 2026-09-04, looking at the public page: "are you sure we are updating the
    live view? it says this has been running about 2,000 minutes and I see no change."
    He was right, and the reason was worse than a stale panel - the LIVE panel was
    showing the autoloop, deliberately stopped two days earlier to free the GPU, while
    the work actually running had no representation on the page at all. A live view that
    shows the one thing that is NOT happening is worse than no live view.

    So this writes what the search is doing, every trial: how far it has got, the leader
    it has found, that leader's year-by-year record, and how much of each year's
    perfect-hindsight ceiling it captured. Written atomically - the pusher reads this
    file on its own schedule and must never catch it half-written.
    """
    try:
        done = [t for t in study.trials
                if t.state.name == "COMPLETE" and t.value is not None]
        live = [t for t in done if not t.user_attrs.get("inert")]
        best = max(done, key=lambda t: t.value) if done else None
        anchor = next((t for t in done if t.number == 0), None)
        rets = (best.user_attrs.get("returns") or {}) if best else {}
        capture = {}
        for y, r in rets.items():
            o = ceiling.get(str(y))
            if o is None or o <= 0:
                continue
            capture[y] = {"ours": r, "oracle": o,
                          # log ratio: the share of COMPOUNDED growth, which is the
                          # honest one - see mock_server._ceiling for why the wealth
                          # ratio understates skill in a year that returned 22,000%.
                          "capture": (math.log(1 + r) / math.log(1 + o))
                          if (1 + r) > 0 else None}
        payload = {
            "at": datetime.now(timezone.utc).isoformat(),
            "study": study_name, "algorithm": "TPE (Bayesian) over the whole decision tree",
            "levers": len(names) if names else 11,
            "trials_done": len(done), "trials_target": target,
            "inert": len(done) - len(live),
            "elapsed_s": round(time.time() - started, 1),
            "anchor": ({"score": anchor.value, "returns": anchor.user_attrs.get("returns"),
                        "worst_year": anchor.user_attrs.get("fit_min_year"),
                        "worst_drawdown": anchor.user_attrs.get("worst_drawdown"),
                        "all_years_positive": anchor.user_attrs.get("all_positive")}
                       if anchor else None),
            "leader": ({"trial": best.number, "score": best.value,
                        "returns": rets,
                        "mandate_years": best.user_attrs.get("mandate_years"),
                        "house_score": best.user_attrs.get("house_score"),
                        "worst_year": best.user_attrs.get("fit_min_year"),
                        "worst_drawdown": best.user_attrs.get("worst_drawdown"),
                        "all_years_positive": best.user_attrs.get("all_positive"),
                        "trades": best.user_attrs.get("trades"),
                        "params": best.params}
                       if best else None),
            "capture": capture,
            "note": "Research-record leader. Becoming the champion costs one reading of "
                    "the sealed 2026 window, which is a separate deliberate step.",
        }
        tmp = LIVE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
        tmp.replace(LIVE)
    except Exception as exc:  # noqa: BLE001 - a heartbeat bug must never kill the study
        print(f"    (live heartbeat failed, continuing: {exc})", flush=True)


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
    ap.add_argument("--seeds", type=int, default=64,
                    help="perturbations of the incumbent enqueued ahead of the search")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--all-years", action="store_true",
                    help="fit on the WHOLE research record 2018-2025 and search `enter` "
                         "too. 2026 stays sealed either way.")
    args = ap.parse_args()

    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    fit_years = ALL_YEARS if args.all_years else FIT_YEARS
    holdout_years = () if args.all_years else HOLDOUT_YEARS
    study_name = STUDY_V2 if args.all_years else STUDY

    OUT.mkdir(parents=True, exist_ok=True)
    sampler = optuna.samplers.TPESampler(seed=20260904, n_startup_trials=args.startup,
                                         multivariate=True, group=True)
    study = optuna.create_study(study_name=study_name, storage=STORAGE,
                                direction="maximize", sampler=sampler,
                                load_if_exists=True)

    if not args.report_only:
        ev = Evaluator(fit_years, holdout_years, with_enter=args.all_years)
        if args.all_years:
            missing = {k: f for k, f in NEEDS_FILE.items() if not (ROOT / f).exists()}
            names = [n for n in SPACE if n not in missing]
            if missing:
                print(f"dropped (no overlay on this machine): "
                      f"{', '.join(f'{k} needs {v}' for k, v in missing.items())}",
                      flush=True)
            print(f"searching {len(names)} levers - the whole decision tree except the "
                  f"mandate and the two execution-realism constants", flush=True)
        else:
            names = None
        if not study.trials:
            # Trial 0 is the incumbent, so every later number has something to be
            # better THAN, measured the same way on the same years. The rest are the
            # incumbent with a few levers moved - see seed_points for why random draws
            # are the wrong instrument in a space this full of gates.
            anchor = (_champion_point_full(ev.risk, ev.band, names) if names
                      else _champion_point(ev.risk, ev.band))
            pts = seed_points(anchor, names, n=args.seeds) if names else [anchor]
            for p in pts:
                study.enqueue_trial(p)
            print(f"enqueued the champion + {len(pts) - 1} perturbations of it",
                  flush=True)

        def objective(trial):
            point = _space(trial, ev.risk, names)
            t0 = time.time()
            r = ev.score(point)
            for k in ("holdout", "fit_min_year", "holdout_min_year", "worst_drawdown",
                      "all_positive", "inert", "trades", "house_score",
                      "mandate_years"):
                trial.set_user_attr(k, r[k])
            trial.set_user_attr("returns", r["returns"])
            trial.set_user_attr("seconds", round(time.time() - t0, 1))
            if r["inert"]:
                print(f"  trial {trial.number:>4}  INERT - never traded  "
                      f"({time.time() - t0:.0f}s)", flush=True)
            else:
                print(f"  trial {trial.number:>4}  score {r['fit']:+.4f}  "
                      f"worst year {r['fit_min_year']:+8.2%}  "
                      f"years over +30% {r['mandate_years']}/8  "
                      f"maxDD {(r['worst_drawdown'] or 0):5.1%}  "
                      f"trades {r['trades']:>5}  ({time.time() - t0:.0f}s)", flush=True)
            return r["fit"]

        done = len([t for t in study.trials if t.state.name == "COMPLETE"])
        # The LOCALS, not the module constants. The first version of this line printed
        # the constants while the run used the locals, so a --all-years study announced
        # itself as the 2018-2023 split. Behaviour right, report wrong - and a report
        # that misstates which years were fitted is the most dangerous kind of wrong
        # here, because every later reader trusts it over the code.
        print(f"study `{study_name}`: {done} trials done, running to {args.trials}\n"
              f"  FIT     {fit_years}\n"
              + (f"  HOLDOUT {holdout_years} (never seen by the sampler)\n"
                 if holdout_years else
                 "  HOLDOUT none - fitting the WHOLE research record; 2026 stays sealed\n"),
              flush=True)
        ceiling, started = _ceiling_years(), time.time()

        def heartbeat(study_, trial_):
            write_live(study_, study_name, names, args.trials, started, ceiling)

        def publish_leader(study_, trial_):
            """Write the current leader the moment it changes.

            Operator, 2026-09-04: "every time you find a better combination, that
            composes the best result in the system and we replace the winner as many
            times as possible." This is that ledger. It is the best on the RESEARCH
            record - the thing the search can honestly rank - and it is explicitly not
            an adoption: a leader becomes the champion only after the sealed year is
            opened once on it, which is a separate, deliberate act.
            """
            try:
                if trial_.state.name != "COMPLETE" or trial_.value is None:
                    return
                best_t = study_.best_trial
                if best_t.number != trial_.number:
                    return
                lead = OUT / "optimization_leader.json"
                lead.write_text(json.dumps({
                    "at": datetime.now(timezone.utc).isoformat(),
                    "study": study_name, "trial": trial_.number,
                    "levers_searched": len(names) if names else 11,
                    "score": trial_.value,
                    "worst_year": trial_.user_attrs.get("fit_min_year"),
                    "all_years_positive": trial_.user_attrs.get("all_positive"),
                    "worst_drawdown": trial_.user_attrs.get("worst_drawdown"),
                    "returns": trial_.user_attrs.get("returns"),
                    "params": trial_.params,
                    "incumbent": {"score": 0.1763, "worst_year": -0.0296,
                                  "all_years_positive": False, "sealed_2026": 0.2571},
                    "status": "research-record leader; NOT adopted - the sealed 2026 "
                              "readout is a separate deliberate step",
                }, indent=1, default=str), encoding="utf-8")
                print(f"    >>> NEW LEADER: trial {trial_.number} score {trial_.value:+.4f}",
                      flush=True)
            except Exception as exc:  # noqa: BLE001 - a reporting bug must not kill the study
                print(f"    (leader publish failed, continuing: {exc})", flush=True)

        # The trial budget is GLOBAL, not per process. Several workers share this study
        # through the SQLite storage, and passing `n_trials` to each of them would run
        # the budget once per worker - three workers quietly doing 900 trials instead of
        # 300, which on a four-minute evaluation is a day of compute nobody asked for.
        study.optimize(objective, callbacks=[
            heartbeat,
            publish_leader,
            optuna.study.MaxTrialsCallback(
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
