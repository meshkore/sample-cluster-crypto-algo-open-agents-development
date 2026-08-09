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
from datetime import date, datetime, timezone
from statistics import median
from typing import Any, Callable, Sequence

from quantlab_trading import grammar
from quantlab_trading.space import Dimension, SearchSpace  # noqa: F401 - re-exported
import json
import math
import random

# Historical optimisation ends here. Not a default, not a suggestion.
LOCK = "2025-12-31"


# --------------------------------------------------------------------------- #
# The objective


@dataclass(frozen=True)
class Window:
    start: str
    end: str

    def __post_init__(self) -> None:
        if self.end > LOCK:
            # Not an assertion about intent. A window past the lock is how the
            # forward year gets consumed by accident, one clamp-less helper at
            # a time.
            raise ValueError(
                f"a fitting window may not end after {LOCK}; got {self.end}. "
                "The 2026 evaluation is `promote()`, once, deliberately."
            )


def folds(start: str, end: str = LOCK, count: int = 4) -> list[Window]:
    """Disjoint consecutive windows across the fittable era.

    Disjoint rather than expanding: an expanding window shares most of its bars
    with the previous one, so a configuration that fits the early years scores
    well on every fold and "consistent across folds" stops meaning anything.
    """
    if count < 2:
        raise ValueError("a walk-forward needs at least two folds")
    first = date.fromisoformat(start)
    last = date.fromisoformat(min(end, LOCK))
    span = (last - first).days
    if span < count * 90:
        raise ValueError("the window is too short to split into that many folds")
    edges = [first.toordinal() + round(span * i / count) for i in range(count + 1)]
    return [
        Window(
            date.fromordinal(edges[i]).isoformat(),
            date.fromordinal(edges[i + 1]).isoformat(),
        )
        for i in range(count)
    ]


@dataclass(frozen=True)
class Score:
    value: float
    returns: tuple[float, ...]
    drawdowns: tuple[float, ...]
    trades: int
    rejected: str | None = None

    def document(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "returns": list(self.returns),
            "drawdowns": list(self.drawdowns),
            "trades": self.trades,
            "rejected": self.rejected,
        }


def objective(
    results: Sequence[dict[str, Any]],
    minimum_trades: int = 30,
    maximum_drawdown: float = 0.30,
    drawdown_weight: float = 1.0,
) -> Score:
    """Score a configuration across the folds it was measured on.

    Three deliberate choices, each against a more obvious alternative:

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
    """
    if not results:
        return Score(-math.inf, (), (), 0, "no folds evaluated")
    returns = tuple(float(r.get("return_pct") or 0.0) for r in results)
    drawdowns = tuple(float(r.get("max_drawdown") or 0.0) for r in results)
    trades = sum(int(r.get("trades") or 0) for r in results)
    worst = max(drawdowns) if drawdowns else 0.0

    if worst >= maximum_drawdown:
        return Score(-math.inf, returns, drawdowns, trades, f"drawdown {worst:.1%}")
    if trades < minimum_trades:
        # A configuration that barely trades has not been measured, it has
        # abstained. Zero trades is a legitimate live behaviour and a useless
        # search result: every such genome ties, and the population fills with
        # them because they can never lose money.
        return Score(-math.inf, returns, drawdowns, trades, f"only {trades} trades")

    consistency = sum(1 for r in returns if r > 0) / len(returns)
    middle = median(returns)
    value = (middle * consistency if middle > 0 else middle) - drawdown_weight * worst
    return Score(value, returns, drawdowns, trades)


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
        self.rng = random.Random(seed)
        self.cache: dict[str, Score] = {}
        self.history: list[dict[str, Any]] = []
        self.evaluations = 0
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
        for window in self.windows:
            parameters = {**self.fixed, **individual.genome}
            try:
                results.append(
                    self.lab.evaluate(
                        self.strategy,
                        self.symbols,
                        window.start,
                        window.end,
                        parameters=parameters,
                    )
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
            "windows": [{"start": w.start, "end": w.end} for w in self.windows],
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
        start: str = "2022-01-01",
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
