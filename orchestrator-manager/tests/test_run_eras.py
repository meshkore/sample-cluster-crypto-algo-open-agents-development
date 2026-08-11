"""Which era a run's result belongs to, and which two runs are one hypothesis.

Both questions used to be answered by reading a string. The era was inferred
from `window_end`, which is the date a run stopped LOADING and says nothing
about the years it was scored on; the pairing was a label suffix, which worked
only for runs the loop launched itself. Each was wrong in the archive, and each
was wrong in a way that showed on the public page.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from quantlab_backtester.models import utc_now
from quantlab_manager.backtests import describe, era_of, pair_key, traded_from
from quantlab_manager.sessions import open_database


def _run(**over):
    row = {
        "backtest_id": "x",
        "label": "x",
        "strategy_family": "four-module",
        "window_start": "2017-08-17",
        "window_end": "2025-12-31",
        "strategy_params_json": json.dumps({"trade_from": "2018-01-01", "bull": 3}),
    }
    row.update(over)
    return row


class TestWhichEraAResultBelongsTo(unittest.TestCase):
    def test_the_era_is_where_trading_started_not_where_loading_did(self):
        # The whole point. A 2026 run loads from 2017 so the detector inherits
        # the market cycle rather than guessing which phase January opened in.
        forward = _run(
            window_start="2017-08-17",
            window_end="2026-12-31",
            strategy_params_json=json.dumps({"trade_from": "2026-01-01"}),
        )
        self.assertEqual(era_of(forward), "2026")
        self.assertEqual(traded_from(forward), "2026-01-01")

    def test_a_run_ending_at_the_lock_is_training(self):
        # `blackmac-codex-vrsi-v3-validation`, which the edge crowned as the
        # best result in 2026 on a return earned between 2022 and 2025.
        row = _run(
            window_start="2021-01-01",
            window_end="2026-01-01",
            strategy_params_json=json.dumps({"trade_from": "2022-01-01"}),
        )
        self.assertEqual(era_of(row), "training")

    def test_a_run_with_no_trade_from_falls_back_to_its_window(self):
        row = _run(strategy_params_json="{}", window_start="2026-01-01")
        self.assertEqual(era_of(row), "2026")

    def test_unreadable_parameters_are_training_rather_than_a_crash(self):
        # Never let a malformed row promote itself into the sealed window.
        row = _run(strategy_params_json="{not json")
        self.assertEqual(era_of(row), "training")


class TestWhichTwoRunsAreOneHypothesis(unittest.TestCase):
    def test_the_same_genome_over_two_eras_is_one_pair(self):
        genome = {"bull": 3, "bear": 7}
        training = _run(
            label="loop-085-sideways-training",
            strategy_params_json=json.dumps({**genome, "trade_from": "2018-01-01"}),
        )
        forward = _run(
            label="loop-085-sideways-2026",
            strategy_params_json=json.dumps({**genome, "trade_from": "2026-01-01"}),
        )
        self.assertEqual(pair_key(training), pair_key(forward))

    def test_key_order_in_the_stored_json_does_not_change_the_key(self):
        a = _run(strategy_params_json=json.dumps({"bull": 3, "bear": 7}))
        b = _run(strategy_params_json=json.dumps({"bear": 7, "bull": 3}))
        self.assertEqual(pair_key(a), pair_key(b))

    def test_a_different_genome_is_a_different_hypothesis(self):
        a = _run(strategy_params_json=json.dumps({"bull": 3}))
        b = _run(strategy_params_json=json.dumps({"bull": 4}))
        self.assertNotEqual(pair_key(a), pair_key(b))

    def test_the_same_genome_under_a_different_strategy_is_not_a_pair(self):
        # Two agents can reach identical numbers meaning different things. The
        # archive has this: `codex-volume-rsi-regime-v2` and `-v3` sit next to
        # each other and are not two halves of anything.
        a = _run(strategy_family="codex-volume-rsi-regime-v2")
        b = _run(strategy_family="codex-volume-rsi-regime-v3")
        self.assertNotEqual(pair_key(a), pair_key(b))

    def test_labels_do_not_enter_into_it(self):
        # The old rule matched `-training` against `-2026` and so paired
        # nothing an agent submitted under its own naming.
        a = _run(label="whatever-the-agent-felt-like")
        b = _run(label="something-else-entirely")
        self.assertEqual(pair_key(a), pair_key(b))


class TestTheStoreHandsTheseToThePage(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.store = open_database(Path(self.tmp.name) / "lab.db")

    def tearDown(self):
        self.tmp.cleanup()

    def _insert(
        self, backtest_id, start, end, trade_from, result, trades, family="four-module"
    ):
        with self.store._connect() as connection:
            connection.execute(
                """INSERT INTO backtest_runs (
                     backtest_id, label, created_at, status, submitted_by,
                     strategy_family, strategy_params_json, policy_json,
                     universe_size, window_start, window_end, initial_capital,
                     return_pct, trades, updated_at
                   ) VALUES (?,?,?,'complete','test',?,?,'{}',
                             100,?,?,100000.0,?,?,?)""",
                (
                    backtest_id,
                    backtest_id,
                    utc_now(),
                    family,
                    json.dumps({"trade_from": trade_from, "bull": 3}),
                    start,
                    end,
                    result,
                    trades,
                    utc_now(),
                ),
            )

    def test_every_row_the_page_reads_carries_its_era_and_pair_key(self):
        self._insert("t", "2017-08-17", "2025-12-31", "2018-01-01", 0.4, 200)
        self._insert("f", "2017-08-17", "2026-12-31", "2026-01-01", 0.02, 20)
        rail = self.store.sidebar()
        rows = {r["backtest_id"]: r for r in rail["history"]}
        self.assertEqual(rows["t"]["era"], "training")
        self.assertEqual(rows["f"]["era"], "2026")
        # and the page can find one from the other without asking the server
        self.assertEqual(rows["t"]["pair_key"], rows["f"]["pair_key"])
        self.assertEqual(self.store.run("f")["era"], "2026")

    def test_the_champion_is_chosen_by_the_same_rule_the_page_displays(self):
        # A training run cannot be the best result in 2026 however well it did.
        self._insert("validation", "2021-01-01", "2026-01-01", "2022-01-01", 10.14, 117)
        self._insert("forward", "2017-08-17", "2026-12-31", "2026-01-01", 0.02, 9)
        best = self.store.sidebar()["best_2026"]
        self.assertEqual(best["backtest_id"], "forward")
        self.assertEqual(best["era"], "2026")

    def test_no_forward_run_leaves_the_champion_empty(self):
        self._insert("validation", "2021-01-01", "2026-01-01", "2022-01-01", 10.14, 117)
        self.assertIsNone(self.store.sidebar()["best_2026"])


class TestDescribeIsSafeOnWhateverItIsGiven(unittest.TestCase):
    def test_nothing_in_nothing_out(self):
        self.assertIsNone(describe(None))

    def test_a_row_missing_every_optional_column_still_gets_an_era(self):
        self.assertEqual(describe({})["era"], "training")


if __name__ == "__main__":
    unittest.main()
