import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from quantlab import walkforward
from quantlab.backtest import CostModel
from quantlab.memory import ExperimentMemory
from quantlab.models import Bar, utc_now
from quantlab.optimization import ExecutionOptimizer
from quantlab.portfolio import MoneyManagement
from quantlab.walkforward import (
    FoldOutcome,
    WalkForwardEvaluator,
    evaluate_folds,
    rank_correlation,
    rolling_folds,
)


UTC = timezone.utc


def outcome(index, return_pct, drawdown=0.05, trades=20, aborted=False):
    start = datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=182 * index)
    return FoldOutcome(
        fold_index=index,
        test_start=start,
        test_end=start + timedelta(days=182),
        return_pct=return_pct,
        max_drawdown=drawdown,
        trades=trades,
        aborted=aborted,
    )


class FoldPlanTest(unittest.TestCase):
    def test_scored_windows_are_consecutive_and_never_overlap(self):
        folds = rolling_folds(
            datetime(2018, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
            train_days=365,
            test_days=90,
            embargo_days=10,
        )
        self.assertGreater(len(folds), 3)
        for earlier, later in zip(folds, folds[1:]):
            self.assertLessEqual(earlier.test_end, later.test_start)
            self.assertEqual(later.index, earlier.index + 1)

    def test_the_embargo_separates_training_from_the_window_that_scores_it(self):
        """A position open when training ended must not reach the test window."""
        folds = rolling_folds(
            datetime(2018, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
            train_days=730,
            test_days=182,
            embargo_days=21,
        )
        for fold in folds:
            self.assertEqual(fold.embargo, timedelta(days=21))
            self.assertLess(fold.train_end, fold.test_start)
            self.assertFalse(fold.covers(fold.train_end))

    def test_no_fold_reaches_past_the_end_of_the_history(self):
        end = datetime(2026, 1, 1, tzinfo=UTC)
        for fold in rolling_folds(datetime(2017, 1, 1, tzinfo=UTC), end):
            self.assertLessEqual(fold.test_end, end)

    def test_the_plan_is_identical_every_time_it_is_built(self):
        arguments = (datetime(2018, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC))
        self.assertEqual(rolling_folds(*arguments), rolling_folds(*arguments))

    def test_a_history_too_short_for_one_fold_produces_none(self):
        self.assertEqual(
            rolling_folds(
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 6, 1, tzinfo=UTC),
                train_days=730,
                test_days=182,
            ),
            (),
        )

    def test_naive_timestamps_and_impossible_windows_are_refused(self):
        with self.assertRaises(ValueError):
            rolling_folds(datetime(2018, 1, 1), datetime(2026, 1, 1, tzinfo=UTC))
        with self.assertRaises(ValueError):
            rolling_folds(
                datetime(2018, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 1, tzinfo=UTC),
                train_days=0,
            )
        with self.assertRaises(ValueError):
            rolling_folds(
                datetime(2018, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 1, tzinfo=UTC),
                embargo_days=-1,
            )


class SelectionScoreTest(unittest.TestCase):
    def test_one_spectacular_fold_cannot_outrank_a_consistent_candidate(self):
        """The failure mode being replaced: a single lucky window winning.

        The lottery ticket has by far the better mean and the better total, and
        it is the candidate the in-sample ranking would promote.
        """
        lottery = [
            outcome(0, 12.0),
            outcome(1, -0.2),
            outcome(2, -0.15),
            outcome(3, -0.1),
            outcome(4, -0.2),
        ]
        steady = [outcome(index, 0.06) for index in range(5)]

        lottery_score = evaluate_folds(lottery)
        steady_score = evaluate_folds(steady)

        self.assertGreater(
            sum(item.return_pct for item in lottery),
            sum(item.return_pct for item in steady),
        )
        self.assertGreater(steady_score.median_score, lottery_score.median_score)
        self.assertTrue(steady_score.eligible)
        self.assertFalse(lottery_score.eligible)

    def test_a_candidate_profitable_in_under_half_its_folds_is_refused(self):
        score = evaluate_folds(
            [
                outcome(0, 0.5),
                outcome(1, 0.4),
                outcome(2, -0.1),
                outcome(3, -0.1),
                outcome(4, -0.1),
            ]
        )
        self.assertAlmostEqual(score.consistency, 0.4)
        self.assertFalse(score.eligible)
        self.assertIn("below the 50% floor", score.reason)

    def test_breaching_the_drawdown_stop_in_any_fold_disqualifies(self):
        """Criterion 7 bars a breached trial from parenting, per fold as well."""
        folds = [
            outcome(0, 0.3),
            outcome(1, 0.25),
            outcome(2, 0.2),
            outcome(3, -0.26, drawdown=0.26, aborted=True),
        ]
        score = evaluate_folds(folds)
        self.assertEqual(score.folds_aborted, 1)
        self.assertFalse(score.eligible)
        self.assertIn("breached the drawdown stop", score.reason)
        self.assertTrue(evaluate_folds(folds, disqualify_on_abort=False).eligible)

    def test_too_few_folds_is_not_a_measurement(self):
        score = evaluate_folds([outcome(0, 0.5), outcome(1, 0.5)])
        self.assertFalse(score.eligible)
        self.assertIn("3 required", score.reason)

    def test_no_folds_at_all_scores_nothing(self):
        score = evaluate_folds([])
        self.assertFalse(score.eligible)
        self.assertEqual(score.folds_evaluated, 0)

    def test_an_aborted_fold_never_counts_as_profitable(self):
        score = evaluate_folds([outcome(0, 0.1, aborted=True)])
        self.assertEqual(score.folds_profitable, 0)

    def test_failed_folds_are_summarised_rather_than_dropped(self):
        score = evaluate_folds([outcome(0, 0.4), outcome(1, -0.3), outcome(2, 0.2)])
        self.assertEqual(score.folds_evaluated, 3)
        self.assertAlmostEqual(score.worst_score, -0.35)
        self.assertEqual(score.total_trades, 60)


class RankCorrelationTest(unittest.TestCase):
    def test_a_perfectly_ordered_pairing_correlates_at_one(self):
        pairs = [(1.0, 10.0), (2.0, 20.0), (3.0, 30.0), (4.0, 40.0)]
        self.assertAlmostEqual(rank_correlation(pairs), 1.0)

    def test_a_reversed_pairing_correlates_at_minus_one(self):
        pairs = [(1.0, 40.0), (2.0, 30.0), (3.0, 20.0), (4.0, 10.0)]
        self.assertAlmostEqual(rank_correlation(pairs), -1.0)

    def test_ties_are_averaged_rather_than_ordered_arbitrarily(self):
        # Left ranks are [1, 2.5, 2.5, 4] because the two 2.0 values share
        # positions two and three; right ranks are [1, 3, 2, 4]. Both mean 2.5,
        # giving a covariance of 4.5 over sqrt(4.5) * sqrt(5).
        pairs = [(1.0, 1.0), (2.0, 3.0), (2.0, 2.0), (4.0, 4.0)]
        self.assertAlmostEqual(rank_correlation(pairs), 4.5 / 22.5**0.5)

    def test_it_refuses_to_invent_a_correlation(self):
        self.assertIsNone(rank_correlation([(1.0, 2.0), (2.0, 3.0)]))
        self.assertIsNone(rank_correlation([(1.0, 5.0), (1.0, 6.0), (1.0, 7.0)]))


class LeakageTest(unittest.TestCase):
    """The reason the embargo and `trading_start` exist."""

    def test_training_bars_warm_indicators_without_ever_becoming_a_trade(self):
        train_start = datetime(2020, 1, 1, tzinfo=UTC)
        test_start = train_start + timedelta(days=121)
        prices = []
        # Training collapses, the scored window climbs. If warm-up bars reached
        # the ledger the fold would report the collapse.
        for day in range(120):
            level = 100.0 - day * 0.5
            prices.append(level)
        for day in range(120):
            level = 40.0 + day * 0.5
            prices.append(level)
        bars = [
            Bar(
                train_start + timedelta(days=index),
                level,
                level * 1.01,
                level * 0.99,
                level,
                1_000_000,
            )
            for index, level in enumerate(prices)
        ]
        fold = walkforward.Fold(
            index=0,
            train_start=train_start,
            train_end=train_start + timedelta(days=100),
            test_start=test_start,
            test_end=train_start + timedelta(days=240),
        )
        evaluator = WalkForwardEvaluator(
            CostModel(10.0, 5.0),
            MoneyManagement(minimum_order_notional=1.0, minimum_daily_quote_volume=0.0),
            100_000.0,
            [fold],
        )
        outcomes = evaluator.run({"BTCUSDT": bars}, lambda: lambda observed: 1.0)

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].test_start, test_start)
        self.assertGreater(outcomes[0].return_pct, 0.0)

    def test_a_fold_with_no_tradable_bar_is_skipped_not_scored_as_flat(self):
        start = datetime(2020, 1, 1, tzinfo=UTC)
        bars = [
            Bar(start + timedelta(days=index), 100, 101, 99, 100, 1_000_000)
            for index in range(30)
        ]
        fold = walkforward.Fold(
            index=0,
            train_start=start,
            train_end=start + timedelta(days=20),
            test_start=start + timedelta(days=200),
            test_end=start + timedelta(days=380),
        )
        evaluator = WalkForwardEvaluator(
            CostModel(10.0, 5.0), MoneyManagement(), 100_000.0, [fold]
        )
        self.assertEqual(
            evaluator.run({"BTCUSDT": bars}, lambda: lambda observed: 1.0), []
        )


def _strategy(db, family, policy):
    digest = json.dumps(policy, sort_keys=True)
    db.execute(
        """INSERT INTO strategy_definitions(strategy_hash,family,signal_json,
             execution_json,money_management_json,long_only,created_at)
           VALUES(?,?,'{}','{}',?,1,?)""",
        (digest, family, json.dumps(policy), utc_now()),
    )
    return int(
        db.execute(
            "SELECT strategy_number FROM strategy_definitions WHERE strategy_hash=?",
            (digest,),
        ).fetchone()[0]
    )


def _phase1(db, number, return_pct, drawdown):
    db.execute(
        """INSERT INTO portfolio_backtest_runs(strategy_number,status,initial_capital,
             current_equity,return_pct,max_drawdown,total_days,processed_days,
             assets_available,assets_traded,trades,wins,losses,win_rate,
             open_positions,cash,updated_at)
           VALUES(?,'COMPLETE',100000,100000,?,?,0,0,1,1,10,5,5,0.5,0,0,?)""",
        (number, return_pct, drawdown, utc_now()),
    )


def _policy(risk):
    return {
        "risk_per_trade": risk,
        "maximum_position_fraction": 0.15,
        "stop_loss_pct": 0.05,
        "take_profit_pct": 0.10,
        "volatility_target": 0.025,
        "maximum_concurrent_assets": 12,
        "minimum_confidence": 0.5,
    }


class ParentSelectionTest(unittest.TestCase):
    """The behaviour change: mutation inherits from out-of-sample evidence."""

    def _memory(self, tmp):
        return ExperimentMemory(Path(tmp) / "lab.db")

    def test_an_out_of_sample_parent_outranks_the_in_sample_winner(self):
        with TemporaryDirectory() as tmp:
            memory = self._memory(tmp)
            with memory.transaction() as db:
                in_sample = _strategy(db, "volatility_expansion", _policy(0.001))
                out_of_sample = _strategy(db, "volatility_expansion", _policy(0.009))
                # The in-sample winner by a wide margin, and the candidate the
                # old ranking promoted.
                _phase1(db, in_sample, 43.0, 0.20)
                _phase1(db, out_of_sample, 0.9, 0.11)
            walkforward.record(
                memory,
                out_of_sample,
                [outcome(index, 0.08) for index in range(5)],
                evaluate_folds([outcome(index, 0.08) for index in range(5)]),
            )

            optimizer = ExecutionOptimizer(memory, _policy(0.002))
            proposal = optimizer.propose("volatility_expansion", 3 * 12 + 1)

            self.assertEqual(proposal["optimizer_source"], "walkforward_elite_mutation")
            # 0.009 mutated by the bounded factors stays far above the 0.001 line.
            self.assertGreater(proposal["risk_per_trade"], 0.005)

    def test_an_ineligible_walkforward_record_does_not_become_a_parent(self):
        with TemporaryDirectory() as tmp:
            memory = self._memory(tmp)
            with memory.transaction() as db:
                number = _strategy(db, "volatility_expansion", _policy(0.009))
                _phase1(db, number, 5.0, 0.10)
            folds = [
                outcome(0, 0.5),
                outcome(1, -0.1),
                outcome(2, -0.1),
                outcome(3, -0.1),
            ]
            walkforward.record(memory, number, folds, evaluate_folds(folds))

            proposal = ExecutionOptimizer(memory, _policy(0.002)).propose(
                "volatility_expansion", 3 * 12 + 1
            )
            self.assertEqual(proposal["optimizer_source"], "feasible_elite_mutation")

    def test_a_family_without_fold_evidence_keeps_the_previous_behaviour(self):
        with TemporaryDirectory() as tmp:
            memory = self._memory(tmp)
            with memory.transaction() as db:
                number = _strategy(db, "volatility_expansion", _policy(0.009))
                _phase1(db, number, 5.0, 0.10)

            proposal = ExecutionOptimizer(memory, _policy(0.002)).propose(
                "volatility_expansion", 3 * 12 + 1
            )
            self.assertEqual(proposal["optimizer_source"], "feasible_elite_mutation")

    def test_the_seed_population_is_untouched_by_any_of_this(self):
        with TemporaryDirectory() as tmp:
            proposal = ExecutionOptimizer(self._memory(tmp), _policy(0.002)).propose(
                "volatility_expansion", 1
            )
            self.assertEqual(proposal["optimizer_source"], "latin_hypercube_seed")


class PersistenceTest(unittest.TestCase):
    def test_rerunning_a_strategy_replaces_its_folds_instead_of_doubling_them(self):
        with TemporaryDirectory() as tmp:
            memory = ExperimentMemory(Path(tmp) / "lab.db")
            with memory.transaction() as db:
                number = _strategy(db, "breakout", _policy(0.003))
            folds = [outcome(index, 0.05) for index in range(4)]
            walkforward.record(memory, number, folds, evaluate_folds(folds))
            walkforward.record(memory, number, folds, evaluate_folds(folds))

            with memory.session() as db:
                stored = db.execute(
                    "SELECT COUNT(*) FROM walkforward_folds WHERE strategy_number=?",
                    (number,),
                ).fetchone()[0]
            self.assertEqual(stored, 4)

            score = walkforward.stored_score(memory, number)
            self.assertIsNotNone(score)
            self.assertTrue(score.eligible)
            self.assertEqual(score.folds_evaluated, 4)

    def test_an_unmeasured_strategy_has_no_score(self):
        with TemporaryDirectory() as tmp:
            memory = ExperimentMemory(Path(tmp) / "lab.db")
            self.assertIsNone(walkforward.stored_score(memory, 999))

    def test_the_diagnostic_reads_forward_results_without_writing_anything(self):
        with TemporaryDirectory() as tmp:
            memory = ExperimentMemory(Path(tmp) / "lab.db")
            report = walkforward.selection_diagnostic(memory)
            self.assertEqual(report["paired_runs"], 0)
            self.assertIsNone(report["in_sample_rank_correlation"])
            self.assertIsNone(report["walkforward_rank_correlation"])


if __name__ == "__main__":
    unittest.main()
