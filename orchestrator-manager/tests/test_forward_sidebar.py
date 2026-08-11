from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from quantlab_backtester.models import utc_now
from quantlab_manager.sessions import open_database


class ForwardSidebarBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.store = open_database(Path(self.tmp.name) / "lab.db")

    def tearDown(self):
        self.tmp.cleanup()

    def _insert(self, backtest_id, start, end, trade_from, result, trades):
        with self.store._connect() as connection:
            connection.execute(
                """INSERT INTO backtest_runs (
                     backtest_id, label, created_at, status, submitted_by,
                     strategy_family, strategy_params_json, policy_json,
                     universe_size, window_start, window_end, initial_capital,
                     return_pct, trades, updated_at
                   ) VALUES (?,?,?,'complete','test','four-module',?,'{}',
                             100,?,?,100000.0,?,?,?)""",
                (
                    backtest_id,
                    backtest_id,
                    utc_now(),
                    json.dumps({"trade_from": trade_from}),
                    start,
                    end,
                    result,
                    trades,
                    utc_now(),
                ),
            )

    def test_a_validation_ending_at_the_lock_is_not_forward_evidence(self):
        self._insert("validation", "2021-01-01", "2026-01-01", "2022-01-01", 0.50, 20)
        self._insert("forward", "2025-01-01", "2026-12-31", "2026-01-01", -0.05, 10)

        self.assertEqual(self.store.sidebar()["best_2026"]["backtest_id"], "forward")


if __name__ == "__main__":
    unittest.main()
