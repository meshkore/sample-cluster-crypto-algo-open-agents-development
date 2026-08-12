"""Fitting a hypothesis to the past, without fitting it to the answer.

Setting a few numbers by hand and running one backtest is not an algorithm; it
is a guess with a receipt. This module is the part that was missing: a declared
search space, a genetic search over it, and an objective that scores a
configuration on windows it was not chosen on.

**The one measurement that shapes everything here.** This laboratory has already
found that optimising harder on the pre-2026 era makes 2026 *worse*: rank
correlation between holdout return and forward return is -0.371, and residual
alpha falls from -2.95% to -11.19% as holdout return rises. Six forward
observations cannot validate a selection rule (critical |rho| >= 0.771, best p =
0.329), so that finding is a warning, not a law -- but it is the only evidence
we have and it points one way. A search that maximises pre-2026 return is
therefore searching in the direction the evidence says is wrong.

So this does not maximise return. It splits the fittable era into disjoint
windows, scores every configuration on all of them, and rewards the ones that
work in MOST of them rather than the one that works spectacularly in the best.
`objective()` is where that is written down, and it is the piece most worth
arguing about.

**The lock is structural.** Every window this module can produce is clamped to
`LOCK` (2025-12-31), and it evaluates through a service started without
`--forward`, which physically cannot serve a later bar. Reaching 2026 is a
separate, deliberate act -- `promote()` -- performed once on the winner.

    space = FourModuleBrain.search_space()
    search = GeneticSearch(lab, "four-module", space, symbols)
    best = search.run(generations=8, population=24)
    forward = search.promote(best)      # the single 2026 shot
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any, Callable, Sequence

from quantlab_trading import grammar
from quantlab_trading.space import Dimension, SearchSpace  # noqa: F401 - re-exported
import json
import math
import random

# Historical optimisation ends here. Not a default, not a suggestion.
LOCK = "2025-12-31"

# The first bar this laboratory holds for any reference asset. A window that
# loads from here inherits the whole cycle, which is what the major-trend
# detector needs to have an opinion on its first TRADING bar rather than on its
# hundredth.
HISTORY_BEGINS = "2017-08-17"

# How much tape a fitting fold loads before the bar it starts trading.
#
# The detector is a stateful reading of the market and it cannot be started
# cold. Three of its outputs need history that a fold boundary does not supply:
# the composite's trailing average (up to `trend_period`, searchable to 300
# bars), the hysteresis streak that decides whether a label has been confirmed,
# and `depth` -- the drawdown from the composite's RUNNING HIGH, which resets to
# the first bar loaded and therefore reads 0% at the top of a fold no matter
# where the market actually is. A fold beginning 2024-01-01 believed the market
# was at its all-time high on that day.
#
# 400 bars covers the longest searchable trend window with room for the streak,
# and carries a year of high-water mark. It is not "all of it": the forward run
# loads from `HISTORY_BEGINS` because it happens once and correctness there is
# what the laboratory is judged on, while a fold is evaluated hundreds of times
# per iteration and every extra bar is paid for on all of them.
FOLD_RUNUP_DAYS = 400


# --------------------------------------------------------------------------- #
# The objective


@dataclass(frozen=True)
class Window:
    """A fold: the bars LOADED, and the bar trading starts on.

    These are two different dates and conflating them is a measurement error,
    not a presentation one. `start` is the first bar the fold is SCORED on;
    `load_from` is the first bar the strategy is shown. Everything stateful --
    the trailing averages, the regime detector's hysteresis, the running high
    that `depth` is measured against -- is built over the gap between them and
    is therefore warm on the first scored bar.

    `load_from` defaults to `start`, which is the old behaviour and is wrong for
    anything with memory. It is kept as the default only so a caller that
    genuinely wants a cold start has to say nothing, and every caller in this
    package says something.
    """

    start: str
    end: str
    load_from: str | None = None

    def __post_init__(self) -> None:
        if self.end > LOCK:
            # Not an assertion about intent. A window past the lock is how the
            # forward year gets consumed by accident, one clamp-less helper at
            # a time.
            raise ValueError(
                f"a fitting window may not end after {LOCK}; got {self.end}. "
                "The 2026 evaluation is `promote()`, once, deliberately."
            )
        if self.load_from is not None and self.load_from > self.start:
            raise ValueError(
                f"load_from ({self.load_from}) is after the window starts "
                f"({self.start}): that is not a run-up, it is a shorter window."
            )

    @property
    def loaded(self) -> str:
        """The first bar served. Never later than the first bar scored."""
        return self.load_from or self.start

    @property
    def warm(self) -> bool:
        return self.loaded < self.start


def folds(
    start: str,
    end: str = LOCK,
    count: int = 4,
    runup_days: int = FOLD_RUNUP_DAYS,
    floor: str = HISTORY_BEGINS,
) -> list[Window]:
    """Disjoint consecutive windows across the fittable era, each warmed.

    Disjoint rather than expanding: an expanding window shares most of its bars
    with the previous one, so a configuration that fits the early years scores
    well on every fold and "consistent across folds" stops meaning anything.

    Disjoint in what is SCORED, that is. Each fold now also loads `runup_days`
    of tape before its first scored bar, which does overlap its predecessor --
    and must, because a stateful strategy that begins at a fold boundary is
    being asked what the trend is by a system that has never seen a trend. The
    run-up is never scored, so it cannot leak a return into the fold; it only
    decides what the strategy KNOWS on the first bar that counts.

    Fold one used to be handled by pinning a single global `trade_from` of
    2019-06-01, which warmed it by muting seventeen of its twenty-four months
    and scoring the remaining seven as if they were the fold. Every fold now
    gets its run-up from outside its own window instead, so fold one is scored
    over all of itself.
    """
    if count < 2:
        raise ValueError("a walk-forward needs at least two folds")
    first = date.fromisoformat(start)
    last = date.fromisoformat(min(end, LOCK))
    span = (last - first).days
    if span < count * 90:
        raise ValueError("the window is too short to split into that many folds")
    edges = [first.toordinal() + round(span * i / count) for i in range(count + 1)]
    earliest = date.fromisoformat(floor)
    out = []
    for i in range(count):
        opens = date.fromordinal(edges[i])
        # Clamped at the first bar that exists: asking for tape from 2016 does
        # not produce a warmer detector, it produces a window whose first
        # served bar is 2017-08-17 anyway and a start date that lies about it.
        warm_from = max(opens - timedelta(days=runup_days), earliest)
        out.append(
            Window(
                opens.isoformat(),
                date.fromordinal(edges[i + 1]).isoformat(),
                load_from=min(warm_from, opens).isoformat(),
            )
        )
    return out


# Bumped whenever `objective` changes what a number MEANS. Scores from
# different versions are not comparable and must never be ranked against each
# other -- an incumbent carrying a v1 score would win or lose on units alone.
# v1: median*consistency - worst_drawdown, in units of return.
# v2: (median*consistency) / worst_drawdown, dimensionless, plus an exposure gate.
OBJECTIVE_VERSION = 2

# How much of the book a run commits ON THE DAYS IT HOLDS ANYTHING --
# `average_exposure / time_in_market`, not average exposure. The distinction is
# the whole point and it was measured rather than reasoned: this laboratory's
# incumbent is out of the market 75% of days by design, so its AVERAGE exposure
# cannot exceed 4.3% even at four times its position size, at which point the
# worst fold drawdown is 23% and the mandate is nearly breached.
#
# THERE IS NO EXPOSURE FLOOR, and the attempt to add one is worth recording
# because it failed for a reason that is itself the finding.
#
# The plan was to reject a run that never commits the book, the way one that
# never trades is rejected. Calibrated at 10% deployed on a 2018-2025 window
# over all 386 symbols, it looked right. On the ACTUAL fold windows under the
# actual deployment scope (top 100 by turnover) the same genome deploys 2.0-4.2%
# — and the pathological v1 configuration deploys 4.3%. The metric does not
# separate the healthy case from the broken one, so a floor drawn anywhere
# useful rejects both. It rejected 149 consecutive candidates before the
# measurement was taken.
#
# What separates them is the ratio itself, and it does so cleanly. Measured on
# the incumbent genome, 2018-2025:
#
#     size   return   worst dd   return/dd
#       1x    -2.29%    10.33%       -0.22   <- where v1 left it
#       2x   +26.16%    15.46%       +1.69
#       3x   +43.79%    20.55%       +2.13
#       4x   +68.20%    23.01%       +2.96
#
# The ratio RISES with position size here, because return grows superlinearly
# while drawdown grows sublinearly: `notional_for` returns zero below
# `minimum_position_fraction`, so shrinking does not scale positions down, it
# deletes them, and at 1x the strategy does not earn less — it loses. The
# objective therefore already carries a gradient toward proper sizing without
# any floor bolted on beside it, and a floor that cannot tell 4.23% from 4.3%
# was never going to add one.
#
# Exposure is still measured and still recorded on every Score and every run.
# It is what made the original defect visible, and a number worth reading is not
# the same as a number worth gating on.

# Denominator floor. Without it a run that barely moves gets a huge ratio from a
# rounding-error drawdown -- 2% over a one-in-a-million drawdown scores 20,000
# and wins every tournament it enters. With the exposure gate gone this is the
# only lock on that door, which is the reason it is not merely a nicety.
DRAWDOWN_FLOOR = 0.02


@dataclass(frozen=True)
class Score:
    value: float
    returns: tuple[float, ...]
    drawdowns: tuple[float, ...]
    trades: int
    rejected: str | None = None
    exposure: float = 0.0
    version: int = OBJECTIVE_VERSION

    def document(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "returns": list(self.returns),
            "drawdowns": list(self.drawdowns),
            "trades": self.trades,
            "rejected": self.rejected,
            "exposure": self.exposure,
            "objective_version": self.version,
        }


def deployed_exposure(result: dict[str, Any]) -> float | None:
    """Share of the book committed on the days this run held anything.

    `None` when the run did not report exposure at all -- folds measured before
    the backtester's summary carried it, which must still score rather than
    silently vanish into a rejection.
    """
    average = result.get("average_exposure")
    if average is None:
        return None
    active = result.get("time_in_market")
    if active is None:
        # Better than nothing: without the denominator this is the average,
        # which understates deployment and can only make the floor stricter.
        return float(average)
    if active <= 0:
        return 0.0
    return float(average) / float(active)


def objective(
    results: Sequence[dict[str, Any]],
    minimum_trades: int = 30,
    maximum_drawdown: float = 0.30,
) -> Score:
    """Score a configuration across the folds it was measured on.

    **Return PER UNIT OF DRAWDOWN, not return minus drawdown.** This is the
    correction that matters, and it was found by measurement rather than
    taste. The previous form was `median*consistency - worst_drawdown`, which
    is not scale-invariant: halve every position and both terms halve, so a
    negative score moves toward zero and the configuration looks better. For
    any candidate whose median return did not already exceed its worst
    drawdown -- 75 of the 90 this laboratory has recorded -- the objective's
    optimum was a position size of zero, and the search found it. By iteration
    91 the incumbent risked 0.54% per trade at a 34% sizing distance, deployed
    0.18% of the book in 2026 and held anything on 4% of days, and each further
    shrink scored as an improvement. Iteration 89, the one iteration that DID
    raise size, was scored worse than the incumbent for doing it.

    A ratio is invariant to size, so the search is finally free to ask the only
    question worth asking -- is this edge real -- and size becomes a separate
    decision instead of a way to game the score.

    **Median, not mean.** One spectacular fold and three bad ones is the exact
    shape of an overfit, and a mean rewards it. The median asks the configuration
    to be decent in most windows.

    **Discounted by consistency**, the share of folds that finished positive. A
    configuration that works in one era out of four is not a strategy with a
    good average; it is a strategy that needs that era.

    The discount applies to a POSITIVE median only. Multiplying a negative
    median by a consistency of zero collapses every losing configuration to the
    same score, and the search loses its gradient across the whole losing half
    of the space -- it wanders there instead of climbing out. Found by a test
    that asked the optimiser to locate a known optimum and watched it stall 68
    units away.

    **Worst drawdown, not average.** The mandate binds on the worst thing that
    happened, and averaging it away is how a run that breached 30% once looks
    acceptable. Breaching it at all is a rejection, not a penalty: the operator's
    rule is an abort, and a scorer that prices it as a cost will eventually buy
    it for enough return.

    **No exposure floor**, though there was one for an afternoon. A ratio has
    its own degenerate corner -- a run that barely moves posting a fine ratio on
    a rounding-error drawdown -- and the obvious guard is to reject a book that
    is never committed. On this laboratory's data that guard cannot be drawn:
    the healthy configuration deploys 4.23% of the book when active and the
    pathological one deploys 4.3%, so any floor between them rejects both. It
    rejected 149 consecutive candidates before anyone measured it. `DRAWDOWN_
    FLOOR` closes the corner instead, and the ratio itself carries the gradient
    toward proper sizing -- see the table above `DRAWDOWN_FLOOR`, where the
    ratio rises monotonically from -0.22 to +2.96 as position size grows.

    Exposure is still measured and recorded on every Score. It is what made the
    original defect visible, and a number worth reading is not automatically a
    number worth gating on.
    """
    if not results:
        return Score(-math.inf, (), (), 0, "no folds evaluated")
    returns = tuple(float(r.get("return_pct") or 0.0) for r in results)
    drawdowns = tuple(float(r.get("max_drawdown") or 0.0) for r in results)
    trades = sum(int(r.get("trades") or 0) for r in results)
    worst = max(drawdowns) if drawdowns else 0.0
    measured = [d for d in (deployed_exposure(r) for r in results) if d is not None]
    exposure = sum(measured) / len(measured) if measured else 0.0

    if worst >= maximum_drawdown:
        return Score(
            -math.inf, returns, drawdowns, trades, f"drawdown {worst:.1%}", exposure
        )
    if trades < minimum_trades:
        # A configuration that barely trades has not been measured, it has
        # abstained. Zero trades is a legitimate live behaviour and a useless
        # search result: every such genome ties, and the population fills with
        # them because they can never lose money.
        return Score(
            -math.inf, returns, drawdowns, trades, f"only {trades} trades", exposure
        )
    consistency = sum(1 for r in returns if r > 0) / len(returns)
    middle = median(returns)
    numerator = middle * consistency if middle > 0 else middle
    value = numerator / max(worst, DRAWDOWN_FLOOR)
    return Score(value, returns, drawdowns, trades, None, exposure)


# --------------------------------------------------------------------------- #
# The search


@dataclass
class Individual:
    genome: dict[str, Any]
    score: Score | None = None

    def key(self) -> str:
        return json.dumps(self.genome, sort_keys=True, default=str)


class GeneticSearch:
    """A population of configurations, bred against the walk-forward objective.

    Elitism keeps the best few unchanged so a generation can never be worse than
    the one before it; the rest are tournament-selected, crossed and mutated.
    Every evaluation is memoised by genome, because a converging population
    re-proposes its own elites constantly and each re-evaluation is a full pass
    over the tape for no new information.

    The random seed is a parameter and it is recorded. A search nobody can
    re-run is an anecdote with more steps.
    """

    def __init__(
        self,
        lab: Any,
        strategy: str,
        space: SearchSpace,
        symbols: Sequence[str],
        windows: Sequence[Window] | None = None,
        fixed: dict[str, Any] | None = None,
        seed: int = 42,
        minimum_trades: int = 30,
        rule_slots: Sequence[str] = (),
        rule_depth: int = 2,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
        on_evaluation: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.lab = lab
        self.strategy = strategy
        self.space = space
        self.symbols = list(symbols)
        self.windows = list(windows or folds("2018-01-01"))
        # Parameters the search must NOT move: the trade_from run-up, the
        # reference basket, anything the hypothesis fixes by construction.
        self.fixed = dict(fixed or {})
        self.seed = seed
        self.minimum_trades = minimum_trades
        # Genome keys holding an expression tree rather than a number. These are
        # what let an iteration change the SHAPE of a rule instead of its knobs
        # -- the difference between tuning a hypothesis and generating one. They
        # are bred with the grammar's own operators, because a gaussian step on
        # a syntax tree means nothing.
        self.rule_slots = tuple(rule_slots)
        self.rule_depth = rule_depth
        self.on_progress = on_progress
        self.on_evaluation = on_evaluation
        self.rng = random.Random(seed)
        self.cache: dict[str, Score] = {}
        self.history: list[dict[str, Any]] = []
        self.evaluations = 0
        # Genomes are what the search counts; BACKTESTS are what it spends. One
        # genome is one per fold, and the difference is the number a reader
        # watching a progress bar is actually waiting on.
        self.backtests = 0
        self.best: Individual | None = None

    # -- evaluation ---------------------------------------------------------- #

    def _sample(self) -> dict[str, Any]:
        genome = self.space.sample(self.rng)
        for slot in self.rule_slots:
            genome[slot] = grammar.random_rule(self.rng, self.rule_depth)
        return genome

    def _breed(self, mother: dict, father: dict) -> dict:
        genome = self.space.crossover(mother, father, self.rng)
        genome = self.space.mutate(genome, self.rng)
        for slot in self.rule_slots:
            left, right = mother.get(slot), father.get(slot)
            if not isinstance(left, dict):
                genome[slot] = grammar.random_rule(self.rng, self.rule_depth)
                continue
            tree = (
                grammar.crossover_rules(left, right, self.rng)
                if isinstance(right, dict)
                else left
            )
            if self.rng.random() < 0.45:
                tree = grammar.mutate_rule(tree, self.rng, self.rule_depth)
            genome[slot] = tree
        return genome

    def _clip(self, genome: dict[str, Any]) -> dict[str, Any]:
        clipped = self.space.clip(genome)
        for slot in self.rule_slots:
            tree = genome.get(slot)
            try:
                clipped[slot] = grammar.validate(tree)
            except (grammar.GrammarError, TypeError):
                clipped[slot] = grammar.random_rule(self.rng, self.rule_depth)
        return clipped

    def score(self, genome: dict[str, Any]) -> Score:
        individual = Individual(self._clip(genome))
        cached = self.cache.get(individual.key())
        if cached is not None:
            return cached
        results = []
        for fold, window in enumerate(self.windows):
            # `trade_from` is the fold's own opening bar, and it OVERRIDES
            # whatever `fixed` carries. It used to be a single global date in
            # `fixed`, which meant one warm fold and three cold ones -- and the
            # warm one paid for it by having most of its months muted and the
            # remainder scored as though it were the whole fold.
            parameters = {
                **self.fixed,
                **individual.genome,
                "trade_from": window.start,
            }
            try:
                outcome = self.lab.evaluate(
                    self.strategy,
                    self.symbols,
                    window.loaded,
                    window.end,
                    parameters=parameters,
                )
                results.append(outcome)
                self.backtests += 1
                # Per BACKTEST, not per generation. A generation is four
                # minutes; reporting only at its boundary left a progress bar
                # that moved four times in a quarter of an hour and a reader
                # with no way to tell work from a hang.
                if self.on_evaluation:
                    self.on_evaluation(
                        {
                            "fold": fold + 1,
                            "folds": len(self.windows),
                            "window": {
                                "start": window.start,
                                "end": window.end,
                                "loaded_from": window.loaded,
                            },
                            "return_pct": outcome.get("return_pct"),
                            "trades": outcome.get("trades"),
                            "max_drawdown": outcome.get("max_drawdown"),
                            "backtests": self.backtests,
                            "best": self.best.score.value if self.best else None,
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                # An illegal combination is a normal event in a search -- a
                # policy whose floor exceeds its cap, a rule name that does not
                # exist. It is a dead genome, not a dead search.
                self.cache[individual.key()] = Score(
                    -math.inf, (), (), 0, f"{type(exc).__name__}: {exc}"
                )
                return self.cache[individual.key()]
        score = objective(results, minimum_trades=self.minimum_trades)
        self.cache[individual.key()] = score
        self.evaluations += 1
        # The incumbent is tracked HERE rather than read off the final
        # population, so "the search returns the best thing it ever saw" is true
        # by construction instead of true because elitism usually preserves it.
        # It usually does -- and "usually" is not a property worth relying on
        # when the answer is what gets promoted to the 2026 window.
        if self.best is None or score.value > self.best.score.value:
            self.best = Individual(individual.genome, score)
        return score

    # -- the loop ------------------------------------------------------------ #

    def run(
        self, generations: int = 8, population: int = 24, elite: int = 3
    ) -> dict[str, Any]:
        if population < 4:
            raise ValueError("a population needs at least four individuals")
        elite = max(1, min(elite, population // 2))
        people = [Individual(self._sample()) for _ in range(population)]

        for generation in range(generations):
            for individual in people:
                individual.score = self.score(individual.genome)
            people.sort(key=lambda i: i.score.value, reverse=True)
            self._report(generation, people)

            survivors = people[:elite]
            children: list[Individual] = list(survivors)
            while len(children) < population:
                mother = self._tournament(people)
                father = self._tournament(people)
                children.append(Individual(self._breed(mother.genome, father.genome)))
            people = children

        for individual in people:
            if individual.score is None:
                individual.score = self.score(individual.genome)
        people.sort(key=lambda i: i.score.value, reverse=True)
        self._report(generations, people)
        best = self.best or people[0]
        return {
            "genome": best.genome,
            "score": best.score.document() if best.score else None,
            "evaluations": self.evaluations,
            "cached": len(self.cache),
            "seed": self.seed,
            "windows": [
                {"start": w.start, "end": w.end, "loaded_from": w.loaded}
                for w in self.windows
            ],
            "history": self.history,
        }

    def _tournament(self, people: list[Individual], size: int = 3) -> Individual:
        """Pick the best of a few at random.

        Fitness-proportionate selection needs positive, comparable fitness and
        this objective produces neither -- a rejected genome scores negative
        infinity. A tournament only ever compares, so it does not care.
        """
        contenders = [self.rng.choice(people) for _ in range(size)]
        return max(contenders, key=lambda i: i.score.value if i.score else -math.inf)

    def _report(self, generation: int, people: list[Individual]) -> None:
        alive = [i for i in people if i.score and i.score.value > -math.inf]
        entry = {
            "generation": generation,
            "best": people[0].score.value if people[0].score else None,
            "viable": len(alive),
            "population": len(people),
            "evaluations": self.evaluations,
            "best_genome": people[0].genome,
        }
        self.history.append(entry)
        if self.on_progress:
            self.on_progress(entry)

    # -- the one shot -------------------------------------------------------- #

    def promote(
        self,
        genome: dict[str, Any],
        label: str | None = None,
        start: str = HISTORY_BEGINS,
        end: str = "2026-12-31",
        trade_from: str = "2026-01-01",
    ) -> dict[str, Any]:
        """Run the winner once, on the sealed window, and RECORD it.

        This is the only function here that reaches past the lock, and it needs
        a laboratory constructed with `forward=True` -- the orchestrator refuses
        to reuse a service that cannot serve those bars rather than returning a
        tape that silently stops at 2025-12-31.

        It runs once. Coming back to adjust a threshold because 2026 did not
        cooperate is the failure this whole module is arranged to prevent, and
        no code can stop it -- only the person reading this.

        THE RUN-UP IS THE WHOLE CYCLE, and that is the point of loading from
        2017 rather than 2022. On its first trading bar the strategy has to
        answer "what major trend is this?", and the honest answer on
        2026-01-01 depends on 2021's top and 2022's bottom. Started in 2022 the
        detector's `depth` -- drawdown from the composite's running high --
        measures from a high set in early 2022 rather than from the actual peak,
        and the bear-phase gate reads that number directly. Loading from the
        first bar the laboratory holds costs one extra run per iteration and
        removes a whole class of "the label was an artifact of where we started"
        from the only result anybody is going to quote.

        None of this touches the lock. The run-up ends at `trade_from` and every
        bar of it is before 2026; what is SCORED is still 2026 alone.
        """
        parameters = {**self.fixed, **self._clip(genome), "trade_from": trade_from}
        return self.lab.launch(
            self.strategy,
            symbols=self.symbols,
            start=start,
            end=end,
            parameters=parameters,
            label=label or f"{self.strategy}-fitted-2026",
            submitted_by="search",
        )


def utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
