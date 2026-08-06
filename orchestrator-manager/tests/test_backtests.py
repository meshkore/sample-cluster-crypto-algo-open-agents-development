"""Persisting many backtests under their own ids.

The point of the id is that runs stop overwriting each other. The old
`portfolio_*` tables are keyed by strategy_number and hold one run per strategy;
these tests exist mainly to prove that two runs of two different configurations
survive side by side with their own orders, trades and equity.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from quantlab_backtester.backtest import CostModel
from quantlab_backtester.engine import LongOnlyPortfolioBacktester
from quantlab_backtester.ledger import BacktestRun
from quantlab_backtester.models import Bar, utc_now
from quantlab_manager.backtests import BacktestStore
from quantlab_manager.memory import SCHEMA
from quantlab_trading.policy import MoneyManagement

UTC = timezone.utc


def _bars(closes):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Bar(
            timestamp=start + timedelta(days=i),
            open=c,
            high=c * 1.02,
            low=c * 0.98,
            close=c,
            volume=1_000_000.0,
        )
        for i, c in enumerate(closes)
    ]


def _policy(**overrides) -> MoneyManagement:
    base = {
        "risk_per_trade": 0.02,
        "maximum_position_fraction": 0.50,
        "stop_loss_pct": 0.30,
        "take_profit_pct": 0.20,
        "minimum_confidence": 0.25,
        "maximum_concurrent_assets": 5,
        "minimum_order_notional": 1.0,
        "minimum_position_fraction": 0.0,
        "volatility_target": 1.0,
        "minimum_daily_quote_volume": 0.0,
        "maximum_volume_participation": 1.0,
        "drawdown_deleverage_start": 0.25,
    }
    base.update(overrides)
    return MoneyManagement(**base)


class _AlwaysLong:
    def reset(self):
        pass

    def on_bar(self, bars):
        return 1.0


class _Choppy:
    def reset(self):
        self.n = 0

    def on_bar(self, bars):
        self.n += 1
        return 1.0 if self.n % 5 < 3 else 0.0


class BacktestStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / "lab.db"
        connection = sqlite3.connect(self.path)
        connection.executescript(SCHEMA)
        connection.close()
        self.store = BacktestStore(self.path)
        self.bars = {"AAA": _bars([100.0 * (1.02**i) for i in range(60)])}

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, label, strategy):
        run = BacktestRun(
            backtest_id=BacktestRun.fingerprint(
                label, {}, {}, self.bars, "2024-01-01", "2024-03-01", 10_000.0
            ),
            label=label,
            created_at=utc_now(),
            initial_capital=10_000.0,
            strategy_family=label,
            strategy_params={},
            policy={"risk_per_trade": 0.02},
            universe_size=len(self.bars),
            window_start="2024-01-01",
            window_end="2024-03-01",
        )
        self.store.open_run(run, submitted_by="tests")
        evaluation = LongOnlyPortfolioBacktester(CostModel(0.0, 0.0), _policy()).run(
            self.bars, strategy, 10_000.0
        )
        self.store.complete_run(run.backtest_id, evaluation, evaluation.ledger)
        return run.backtest_id, evaluation

    def test_a_run_round_trips(self):
        backtest_id, evaluation = self._run("always", _AlwaysLong)
        stored = self.store.run(backtest_id)
        self.assertEqual(stored["status"], "complete")
        self.assertAlmostEqual(stored["return_pct"], evaluation.return_pct)
        self.assertAlmostEqual(stored["final_equity"], evaluation.final_equity)
        self.assertEqual(stored["submitted_by"], "tests")
        self.assertEqual(
            len(self.store.orders(backtest_id)), len(evaluation.ledger.orders)
        )
        self.assertEqual(
            len(self.store.equity(backtest_id)), len(evaluation.equity_curve)
        )

    def test_two_runs_do_not_overwrite_each_other(self):
        """The whole reason the id exists."""
        first, first_eval = self._run("always", _AlwaysLong)
        second, second_eval = self._run("choppy", _Choppy)
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.store.runs()), 2)
        self.assertEqual(len(self.store.orders(first)), len(first_eval.ledger.orders))
        self.assertEqual(len(self.store.orders(second)), len(second_eval.ledger.orders))
        self.assertNotEqual(
            self.store.run(first)["return_pct"], self.store.run(second)["return_pct"]
        )

    def test_rerunning_an_id_replaces_its_records(self):
        """Re-running the same configuration must not interleave two histories."""
        backtest_id, evaluation = self._run("always", _AlwaysLong)
        expected = len(evaluation.ledger.orders)
        again, _ = self._run("always", _AlwaysLong)
        self.assertEqual(backtest_id, again)
        self.assertEqual(len(self.store.orders(backtest_id)), expected)
        self.assertEqual(len(self.store.runs()), 1)

    def test_a_failed_run_leaves_a_trace(self):
        run = BacktestRun(
            backtest_id="deadbeefdeadbeef",
            label="broken",
            created_at=utc_now(),
            initial_capital=10_000.0,
            strategy_family="broken",
            strategy_params={},
            policy={},
            universe_size=1,
            window_start=None,
            window_end=None,
        )
        self.store.open_run(run)
        self.store.fail_run(run.backtest_id, "provider timed out")
        stored = self.store.run(run.backtest_id)
        self.assertEqual(stored["status"], "failed")
        self.assertIn("timed out", stored["abort_reason"])

    def test_an_orphan_order_is_refused(self):
        """Foreign keys are on, so nothing can hang off an id that never ran."""
        with self.assertRaises(sqlite3.IntegrityError):
            with sqlite3.connect(self.path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute(
                    "INSERT INTO backtest_orders (backtest_id, sequence, timestamp, "
                    "symbol, side, quantity, price, notional, fee, reason, cash_after) "
                    "VALUES ('ghost',1,'2024-01-01','AAA','BUY',1,1,1,0,'ENTRY',0)"
                )


if __name__ == "__main__":
    unittest.main()
