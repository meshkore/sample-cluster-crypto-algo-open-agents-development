"""The fitting layer: the lock, the objective, and the search that uses them.

The objective is the argumentative part of this module and the tests say so: a
scorer that maximises return would pick the overfit in every one of these cases,
and this laboratory has measured that pre-2026 return is anti-predictive of 2026
(rho = -0.371). Each test below names the alternative it rules out.

All sabotage-verified.
"""

import math
import random
import unittest

from quantlab_manager.search import (
    DRAWDOWN_FLOOR,
    HISTORY_BEGINS,
    LOCK,
    OBJECTIVE_VERSION,
    GeneticSearch,
    Window,
    folds,
    objective,
)
from quantlab_trading.space import Dimension, SearchSpace


def _fold(
    return_pct,
    max_drawdown=0.05,
    trades=50,
    average_exposure=0.05,
    time_in_market=0.25,
):
    """One fold. The exposure defaults describe a book that stands aside three
    days in four and commits a fifth of itself when it acts -- the shape this
    laboratory actually runs. Nothing gates on them; they are recorded."""
    return {
        "return_pct": return_pct,
        "max_drawdown": max_drawdown,
        "trades": trades,
        "average_exposure": average_exposure,
        "time_in_market": time_in_market,
    }


class TestTheLock(unittest.TestCase):
    def test_a_fitting_window_may_not_end_after_the_lock(self):
        """Sabotage: drop the check. The forward year is then reachable from any
        helper that happens to take an end date, which is exactly how it gets
        consumed by accident."""
        Window("2024-01-01", LOCK)  # the boundary itself is legal
        with self.assertRaises(ValueError):
            Window("2024-01-01", "2026-06-30")

    def test_folds_are_clamped_and_disjoint(self):
        windows = folds("2018-01-01", "2030-01-01", count=4)
        self.assertEqual(windows[-1].end, LOCK)
        for earlier, later in zip(windows, windows[1:]):
            self.assertEqual(earlier.end, later.start)

    def test_folds_refuse_a_window_too_short_to_split(self):
        with self.assertRaises(ValueError):
            folds("2025-01-01", "2025-03-01", count=4)


class TestEveryFoldIsWarm(unittest.TestCase):
    """A stateful strategy started at a fold boundary is being asked what the
    trend is by a system that has never seen one.

    The detector carries a trailing average, a hysteresis streak, and a running
    high that `depth` is measured from. All three reset to the first bar SERVED,
    so a fold beginning 2024-01-01 believed the market was at its all-time high
    on that day. The run-up is never scored -- it only decides what the strategy
    knows on the first bar that is.
    """

    def test_each_fold_loads_tape_before_the_bar_it_is_scored_on(self):
        """Sabotage: return `load_from=None` from `folds`. Everything else
        passes and every fold silently starts cold again."""
        for window in folds("2018-01-01", count=4):
            with self.subTest(window=window.start):
                self.assertTrue(window.warm, f"{window.start} starts cold")
                self.assertLess(window.loaded, window.start)

    def test_the_run_up_never_reaches_before_the_first_bar_we_hold(self):
        """Asking for tape from 2016 does not warm anything. It produces a
        window whose first served bar is 2017-08-17 regardless and a start date
        that misreports it."""
        first = folds("2018-01-01", count=4)[0]
        self.assertGreaterEqual(first.loaded, HISTORY_BEGINS)

    def test_the_scored_windows_are_still_disjoint(self):
        """The run-up overlaps its predecessor and must. What may NOT overlap is
        what is scored, or 'consistent across folds' stops meaning anything."""
        windows = folds("2018-01-01", count=4)
        for earlier, later in zip(windows, windows[1:]):
            self.assertEqual(earlier.end, later.start)

    def test_a_run_up_that_starts_after_the_window_is_refused(self):
        Window("2024-01-01", LOCK, load_from="2023-01-01")
        Window("2024-01-01", LOCK, load_from="2024-01-01")  # no run-up is legal
        with self.assertRaises(ValueError):
            Window("2024-01-01", LOCK, load_from="2024-06-01")

    def test_the_run_up_stays_behind_the_lock(self):
        """A warm window is still a fitting window. Nothing about loading more
        tape may reach past 2025-12-31."""
        for window in folds("2018-01-01", count=4):
            self.assertLessEqual(window.end, LOCK)
            self.assertLess(window.loaded, LOCK)


class TestObjective(unittest.TestCase):
    def test_one_spectacular_fold_does_not_beat_four_decent_ones(self):
        """The shape of an overfit, and the reason this is a median.

        Sabotage: score on `sum(returns)` or `mean(returns)`. The lucky
        configuration wins -- its mean is more than double -- and the assertion
        below fails.
        """
        lucky = objective([_fold(8.0), _fold(-0.15), _fold(-0.10), _fold(-0.12)])
        steady = objective([_fold(0.12), _fold(0.09), _fold(0.14), _fold(0.07)])
        self.assertGreater(steady.value, lucky.value)
        # The lucky configuration must actually score badly, not merely tie: a
        # +800% fold cannot be allowed to buy its way past three losing eras.
        self.assertLess(lucky.value, 0.0)

    def test_working_in_one_era_out_of_four_is_penalised(self):
        """Consistency multiplies. Two configurations with the SAME median can
        still be told apart by how many folds they actually survived."""
        broad = objective([_fold(0.10), _fold(0.10), _fold(0.10), _fold(0.10)])
        narrow = objective([_fold(0.10), _fold(0.10), _fold(-0.30), _fold(-0.30)])
        self.assertGreater(broad.value, narrow.value)

    def test_a_drawdown_breach_is_a_rejection_not_a_discount(self):
        """The operator's rule is an abort. Sabotage: price it as a penalty
        instead -- `value -= worst` with no rejection -- and a configuration
        returning +400% at a 45% drawdown outranks every legal one."""
        breached = objective([_fold(4.0, max_drawdown=0.45)] * 4)
        self.assertEqual(breached.value, -math.inf)
        self.assertIn("drawdown", breached.rejected)

    def test_a_configuration_that_barely_trades_is_not_a_result(self):
        """Zero trades is legitimate live behaviour and a useless search result:
        every such genome ties at 0.00% and can never lose, so the population
        fills with them."""
        idle = objective([_fold(0.0, trades=1)] * 4)
        self.assertEqual(idle.value, -math.inf)
        self.assertIn("trades", idle.rejected)

    def test_the_worst_drawdown_is_what_counts_not_the_average(self):
        spiky = objective(
            [_fold(0.12, 0.02), _fold(0.12, 0.02), _fold(0.12, 0.02), _fold(0.12, 0.28)]
        )
        calm = objective([_fold(0.12, 0.08)] * 4)
        self.assertGreater(calm.value, spiky.value)


class TestTheObjectiveCannotBeGamedByBettingLess(unittest.TestCase):
    """The defect this objective was rewritten to remove.

    The previous form was `median*consistency - worst_drawdown`. Halving every
    position halves both terms, so any candidate scoring below zero -- 75 of the
    90 this laboratory recorded -- was improved by shrinking, and the optimum
    was a position size of zero. The search found it: by iteration 91 the
    incumbent deployed 0.18% of the book in 2026 and every further shrink read
    as progress. A ratio is invariant to size; these tests hold that line.
    """

    @staticmethod
    def _at(
        scale,
        returns=(0.008, 0.128, 0.076, -0.041),
        drawdowns=(0.005, 0.052, 0.040, 0.043),
    ):
        """The four folds of H-L091, verbatim, scaled as position size scales
        them. Time in market is held fixed because size does not change how
        often the strategy acts -- only how much it commits when it does."""
        return [
            _fold(
                r * scale,
                d * scale,
                trades=274,
                average_exposure=0.05 * scale,
                time_in_market=0.25,
            )
            for r, d in zip(returns, drawdowns)
        ]

    def test_the_same_strategy_scores_the_same_at_any_size(self):
        """Sabotage: restore `numerator - worst`. The scores then differ by a
        factor of four across these three rows and the assertion fails."""
        full = objective(self._at(1.0)).value
        double = objective(self._at(2.0)).value
        half = objective(self._at(0.5)).value
        self.assertAlmostEqual(full, double, places=9)
        self.assertAlmostEqual(full, half, places=9)

    def test_shrinking_a_losing_configuration_no_longer_improves_it(self):
        """The exact exploit, in the regime where it paid: a negative score
        scaled toward zero used to read as an improvement. Under the old form
        `big` was -0.35 and `small` was -0.175, so betting half as much was
        worth twice the score."""
        losing = ((-0.05, -0.02, -0.08, -0.01), (0.10, 0.10, 0.10, 0.10))
        big = objective(self._at(1.0, *losing)).value
        small = objective(self._at(0.5, *losing)).value
        self.assertLess(big, 0.0)
        self.assertAlmostEqual(big, small, places=9)

    def test_low_exposure_is_recorded_and_not_rejected(self):
        """There is no exposure floor, and the attempt to add one is worth a
        test because it failed for a reason that is the finding.

        A floor looked obviously right and was calibrated at 10% deployed on a
        2018-2025 window over all 386 symbols. On the ACTUAL fold windows under
        the actual deployment scope the healthy configuration deploys 4.23% and
        the pathological one deploys 4.3% -- the metric does not separate them,
        so a floor drawn anywhere useful rejects both. It rejected 149
        consecutive candidates before anyone measured it.

        Sabotage: reinstate any exposure rejection. This scores -inf and the
        loop stops producing.
        """
        thin = objective(
            [_fold(0.06, 0.08, trades=60, average_exposure=0.0011, time_in_market=0.24)]
            * 4
        )
        self.assertGreater(thin.value, 0.0)
        self.assertIsNone(thin.rejected)
        # Measured and carried regardless: it is what made the defect visible.
        self.assertAlmostEqual(thin.exposure, 0.0011 / 0.24)

    def test_the_ratio_itself_prefers_the_larger_position_size(self):
        """Why no floor is needed. Measured on the incumbent genome over
        2018-2025: return grows superlinearly with size while drawdown grows
        sublinearly, because `notional_for` returns zero below
        `minimum_position_fraction` and shrinking DELETES positions rather than
        scaling them. At 1x the strategy does not earn less, it loses."""
        measured = [  # size, return, worst drawdown
            (1, -0.0229, 0.1033),
            (2, 0.2616, 0.1546),
            (3, 0.4379, 0.2055),
            (4, 0.6820, 0.2301),
        ]
        scores = [
            objective([_fold(r, d, trades=600)] * 4).value for _, r, d in measured
        ]
        self.assertEqual(
            scores, sorted(scores), f"ratio not monotone in size: {scores}"
        )
        self.assertLess(scores[0], 0.0)
        self.assertGreater(scores[-1], 2.0)

    def test_a_run_with_no_exposure_recorded_still_scores(self):
        """Folds measured before the backtester reported exposure must still
        score. A silent -inf on historical data would look like a search that
        suddenly found nothing."""
        blind = [
            {"return_pct": 0.10, "max_drawdown": 0.05, "trades": 50} for _ in range(4)
        ]
        self.assertGreater(objective(blind).value, 0.0)
        self.assertIsNone(objective(blind).rejected)

    def test_a_rounding_error_drawdown_cannot_manufacture_a_huge_ratio(self):
        """Unfloored, 2% over a one-in-a-million drawdown scores 20,000 and
        wins every tournament it enters. Sabotage: drop `max(worst, FLOOR)`."""
        floored = objective([_fold(0.02, 0.000001, trades=274)] * 4)
        self.assertEqual(floored.value, 0.02 / DRAWDOWN_FLOOR)
        self.assertLess(floored.value, objective([_fold(0.20, 0.05)] * 4).value)

    def test_the_score_carries_the_version_that_produced_it(self):
        """v1 numbers are returns and v2 numbers are ratios. Ranking one against
        the other decides the incumbent on units alone."""
        self.assertEqual(
            objective([_fold(0.10)] * 4).document()["objective_version"],
            OBJECTIVE_VERSION,
        )


class TestSpace(unittest.TestCase):
    def _space(self):
        return SearchSpace(
            (
                Dimension("bars", 10, 100, integer=True),
                Dimension("fraction", 0.0, 1.0),
                Dimension("rule", choices=("a", "b", "c")),
            )
        )

    def test_a_sample_is_always_inside_the_declared_range(self):
        rng = random.Random(7)
        space = self._space()
        for _ in range(200):
            genome = space.sample(rng)
            self.assertTrue(10 <= genome["bars"] <= 100)
            self.assertIsInstance(genome["bars"], int)
            self.assertTrue(0.0 <= genome["fraction"] <= 1.0)
            self.assertIn(genome["rule"], ("a", "b", "c"))

    def test_mutation_stays_inside_the_range(self):
        """Sabotage: return the raw gaussian from `nudge`. Out-of-range genomes
        then reach the brain, which either raises or -- worse -- silently clips
        somewhere else and the search optimises a parameter it is not setting."""
        rng = random.Random(3)
        space = self._space()
        genome = {"bars": 100, "fraction": 1.0, "rule": "a"}
        for _ in range(500):
            genome = space.mutate(genome, rng, rate=1.0)
            self.assertTrue(10 <= genome["bars"] <= 100)
            self.assertTrue(0.0 <= genome["fraction"] <= 1.0)

    def test_crossover_takes_every_gene_from_one_parent_or_the_other(self):
        rng = random.Random(11)
        space = self._space()
        a = {"bars": 10, "fraction": 0.0, "rule": "a"}
        b = {"bars": 100, "fraction": 1.0, "rule": "c"}
        for _ in range(100):
            child = space.crossover(a, b, rng)
            for key in child:
                self.assertIn(child[key], (a[key], b[key]))

    def test_two_dimensions_may_not_share_a_name(self):
        with self.assertRaises(ValueError):
            SearchSpace((Dimension("x", 0, 1), Dimension("x", 5, 9)))


class _FakeLab:
    """A laboratory whose optimum is known, so the search can be checked.

    Return peaks at `target` and falls off linearly. Nothing here touches a
    backtester: the question is whether the optimiser finds a maximum it is
    given, not whether the tape is right.
    """

    def __init__(self, target=60.0):
        self.target = target
        self.calls = 0

    def evaluate(self, strategy, symbols, start, end, parameters=None):
        self.calls += 1
        assert end <= LOCK, f"the search reached past the lock: {end}"
        distance = abs(float(parameters["bars"]) - self.target) / self.target
        return {
            "return_pct": max(-0.5, 0.4 - distance),
            "max_drawdown": 0.05,
            "trades": 60,
        }


class _WideLab(_FakeLab):
    """A landscape that needs every gene right at once.

    Multi-dimensional so a child does not inherit the whole answer from one
    parent by default. That is what makes elitism observable.
    """

    def evaluate(self, strategy, symbols, start, end, parameters=None):
        self.calls += 1
        assert end <= LOCK, f"the search reached past the lock: {end}"
        error = (
            sum(
                abs(float(parameters[name]) - self.target) / self.target
                for name in "abcd"
            )
            / 4
        )
        return {
            "return_pct": max(-0.5, 0.4 - error),
            "max_drawdown": 0.05,
            "trades": 60,
        }


class TestGeneticSearch(unittest.TestCase):
    def _search(self, lab, **kwargs):
        space = SearchSpace((Dimension("bars", 10, 200, integer=True),))
        return GeneticSearch(
            lab,
            "fake",
            space,
            ["BTCUSDT"],
            windows=folds("2018-01-01", count=3),
            seed=5,
            **kwargs,
        )

    def test_it_finds_a_known_optimum(self):
        lab = _FakeLab(target=60.0)
        result = self._search(lab).run(generations=6, population=12)
        self.assertLess(abs(result["genome"]["bars"] - 60), 12)
        self.assertGreater(result["score"]["value"], 0.3)

    def test_it_never_evaluates_past_the_lock(self):
        """The assertion lives inside `_FakeLab.evaluate`, so any window that
        escaped the clamp fails the test rather than quietly consuming 2026."""
        self._search(_FakeLab()).run(generations=3, population=8)

    def test_the_same_seed_produces_the_same_answer(self):
        """A search nobody can re-run is an anecdote with more steps."""
        first = self._search(_FakeLab()).run(generations=4, population=10)
        second = self._search(_FakeLab()).run(generations=4, population=10)
        self.assertEqual(first["genome"], second["genome"])

    def test_every_evaluation_loads_earlier_than_it_trades(self):
        """The fold's run-up has to reach `evaluate`, or `Window.load_from` is
        a field nobody reads.

        Sabotage: pass `window.start` as the start again, or drop the
        `trade_from` override. Both leave the search working and every fold
        cold, which is the bug this replaced -- silent, and worth roughly the
        whole bear-market result.
        """
        seen = []

        class Recording(_FakeLab):
            def evaluate(self, strategy, symbols, start, end, parameters=None):
                seen.append((start, parameters.get("trade_from")))
                return super().evaluate(strategy, symbols, start, end, parameters)

        self._search(Recording()).run(generations=2, population=6)
        self.assertTrue(seen)
        for loaded, trades_from in seen:
            self.assertIsNotNone(trades_from, "trade_from never reached the lab")
            self.assertLess(loaded, trades_from, "the tape started where trading did")

    def test_a_fixed_trade_from_cannot_mute_a_fold(self):
        """`fixed` used to carry one global `trade_from` for every fold, so one
        fold was scored over a fraction of itself and the rest started cold.
        The window's own opening bar wins now."""
        seen = []

        class Recording(_FakeLab):
            def evaluate(self, strategy, symbols, start, end, parameters=None):
                seen.append(parameters.get("trade_from"))
                return super().evaluate(strategy, symbols, start, end, parameters)

        search = self._search(Recording(), fixed={"trade_from": "2019-06-01"})
        search.run(generations=1, population=4)
        starts = {w.start for w in search.windows}
        self.assertTrue(seen)
        self.assertEqual(set(seen), starts)
        self.assertNotIn("2019-06-01", set(seen) - starts)

    def test_repeated_genomes_are_evaluated_once(self):
        """Elitism re-proposes its own survivors every generation, and each
        re-evaluation is a full pass over the tape for no new information.

        Sabotage: remove the cache lookup in `score`. The call count roughly
        triples and this assertion fails.
        """
        lab = _FakeLab()
        search = self._search(lab)
        search.run(generations=6, population=12)
        self.assertLess(lab.calls, 6 * 12 * 3)

    def test_the_answer_is_the_best_thing_the_search_ever_saw(self):
        """The search reports its incumbent, not its last population.

        Elitism usually preserves the best individual, and "usually" is not a
        property worth relying on when the answer is what gets promoted to the
        2026 window. So the incumbent is tracked at evaluation time and this
        pins that: sabotage `best = self.best or people[0]` to `people[0]` and
        the returned score stops matching the maximum over everything evaluated.

        Said plainly: on these landscapes the assertion below ALSO holds with
        elitism alone, so it is a regression guard, not a discriminating test.
        `test_the_incumbent_survives_a_worse_evaluation` is the discriminating
        one. Two earlier attempts to make this test do that job -- a monotone
        history, and the same assertion on a one-dimensional landscape -- both
        passed against a version with elitism entirely removed, which is the
        kind of test this project has shipped before and should not ship again.
        """
        # SEVERAL dimensions on purpose. With one, crossover just copies a
        # parent's only gene and mutation leaves it alone three times in four,
        # so the best individual survives by accident and the test passes
        # against a version with no elitism at all -- which is what happened.
        space = SearchSpace(
            tuple(Dimension(name, 10, 4000, integer=True) for name in "abcd")
        )
        search = GeneticSearch(
            _WideLab(target=60.0),
            "fake",
            space,
            ["BTCUSDT"],
            windows=folds("2018-01-01", count=3),
            seed=5,
        )
        result = search.run(generations=5, population=8)
        best_ever = max(s.value for s in search.cache.values())
        self.assertEqual(result["score"]["value"], best_ever)

        bests = [h["best"] for h in search.history]
        for earlier, later in zip(bests, bests[1:]):
            self.assertGreaterEqual(later, earlier)

    def test_the_incumbent_survives_a_worse_evaluation(self):
        """The discriminating test for the incumbent tracker.

        Sabotage: delete the `self.best` update in `score`. The tracker then
        holds whatever was evaluated last and this fails immediately -- no
        landscape, no seed, no convergence luck involved.
        """
        search = self._search(_FakeLab(target=60.0))
        good = search.score({"bars": 60})
        search.score({"bars": 200})
        self.assertIsNotNone(search.best)
        self.assertEqual(search.best.genome["bars"], 60)
        self.assertEqual(search.best.score.value, good.value)

    def test_a_genome_that_cannot_be_built_kills_itself_not_the_search(self):
        class _Hostile(_FakeLab):
            def evaluate(self, strategy, symbols, start, end, parameters=None):
                if parameters["bars"] > 100:
                    raise ValueError("illegal combination")
                return super().evaluate(strategy, symbols, start, end, parameters)

        result = self._search(_Hostile(target=60.0)).run(generations=4, population=10)
        self.assertLessEqual(result["genome"]["bars"], 100)


if __name__ == "__main__":
    unittest.main()
