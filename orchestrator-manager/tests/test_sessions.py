"""Persisting a driven session, and reconstructing trades from the order log.

The session records fills; a trade is a pairing, and the pairing happens here.
These tests exist because that reconstruction is exactly the kind of quiet
arithmetic that produces a plausible wrong number.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantlab_backtester.backtest import CostModel
from quantlab_backtester.ledger import BacktestRun
from quantlab_backtester.models import Bar, utc_now
from quantlab_manager.sessions import open_database, regime_timeline, run_session
from quantlab_trading.runner import Decision

UTC = timezone.utc


def _bars(closes):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Bar(
            timestamp=start + timedelta(days=i),
            open=c,
            high=c * 1.01,
            low=c * 0.99,
            close=c,
            volume=5_000_000.0,
        )
        for i, c in enumerate(closes)
    ]


def _run(label, universe, capital=10_000.0):
    return BacktestRun(
        backtest_id=BacktestRun.fingerprint(
            label, {}, {}, universe, None, None, capital
        ),
        label=label,
        created_at=utc_now(),
        initial_capital=capital,
        strategy_family=label,
        strategy_params={},
        policy={},
        universe_size=len(universe),
        window_start=None,
        window_end=None,
    )


class _BuyThenSell:
    """Buys on bar 1, sells on bar 5. One clean round trip to check arithmetic."""

    def decide(self, tick):
        decision = Decision()
        if tick["sequence"] == 1:
            decision.buy("AAA", 1000.0, "ENTRY", "test entry")
        elif tick["sequence"] == 5 and tick["account"]["positions"]:
            decision.sell("AAA", "EXIT", "test exit")
        else:
            decision.note = "waiting"
        return decision


class SessionPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.store = open_database(Path(self.tmp.name) / "lab.db")
        self.bars = {"AAA": _bars([100.0] * 4 + [200.0] * 8)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_round_trip_is_reconstructed_from_the_orders(self):
        run = _run("pairing", self.bars)
        summary = run_session(_BuyThenSell(), run, self.bars, store=self.store)
        self.assertEqual(summary["status"], "complete")

        trades = self.store.trades(run.backtest_id)
        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade["symbol"], "AAA")
        self.assertAlmostEqual(trade["entry_price"], 100.0)
        self.assertAlmostEqual(trade["exit_price"], 200.0)
        # Bought 1000 at 100, sold the same quantity at 200: the position
        # doubled, so PnL must be about +1000 and +100%.
        self.assertAlmostEqual(trade["pnl"], 1000.0, places=6)
        self.assertAlmostEqual(trade["pnl_pct"], 1.0, places=6)

    def test_an_open_position_is_not_counted_as_a_trade(self):
        """An unclosed position has no realised PnL. Inventing one is how a run
        flatters itself, so the pairing drops it."""

        class _BuyOnly:
            def decide(self, tick):
                decision = Decision()
                if tick["sequence"] == 1:
                    decision.buy("AAA", 1000.0, "ENTRY")
                return decision

        run = _run("open", self.bars)
        run_session(_BuyOnly(), run, self.bars, store=self.store)
        self.assertEqual(self.store.trades(run.backtest_id), [])
        self.assertEqual(self.store.run(run.backtest_id)["trades"], 0)
        # The buy is still on record even though no trade closed.
        self.assertEqual(len(self.store.orders(run.backtest_id)), 1)

    def test_decisions_are_recorded_including_doing_nothing(self):
        """A blank stretch on a chart must be distinguishable from a crash."""
        run = _run("narration", self.bars)
        run_session(_BuyThenSell(), run, self.bars, store=self.store)
        decisions = self.store.decisions(run.backtest_id)
        self.assertTrue(decisions)
        self.assertTrue(any(d["note"] == "waiting" for d in decisions))
        self.assertTrue(any(d["orders"] for d in decisions))
        acted = next(d for d in decisions if d["orders"])
        self.assertEqual(acted["orders"][0]["rationale"], "test entry")

    def test_equity_and_stats_land_on_the_run_row(self):
        run = _run("stats", self.bars)
        summary = run_session(
            _BuyThenSell(), run, self.bars, store=self.store, costs=CostModel(0.0, 0.0)
        )
        row = self.store.run(run.backtest_id)
        self.assertAlmostEqual(row["final_equity"], summary["final_equity"])
        self.assertEqual(row["wins"], 1)
        self.assertEqual(row["losses"], 0)
        self.assertAlmostEqual(row["win_rate"], 1.0)
        self.assertEqual(len(self.store.equity(run.backtest_id)), 12)

    def test_a_brain_that_stops_is_recorded_as_stopped(self):
        class _Quitter:
            def decide(self, tick):
                decision = Decision()
                if tick["sequence"] >= 3:
                    decision.stop = "mandate breached"
                return decision

        run = _run("stopped", self.bars)
        summary = run_session(_Quitter(), run, self.bars, store=self.store)
        self.assertEqual(summary["status"], "stopped")
        row = self.store.run(run.backtest_id)
        self.assertEqual(row["status"], "stopped")
        self.assertEqual(row["aborted"], 1)
        self.assertIn("mandate", row["abort_reason"])

    def test_a_crashing_brain_leaves_a_failed_row_and_re_raises(self):
        """A run that dies must not vanish. The row says which one it was."""

        class _Broken:
            def decide(self, tick):
                raise ZeroDivisionError("boom")

        run = _run("broken", self.bars)
        with self.assertRaises(ZeroDivisionError):
            run_session(_Broken(), run, self.bars, store=self.store)
        row = self.store.run(run.backtest_id)
        self.assertEqual(row["status"], "failed")
        self.assertIn("ZeroDivisionError", row["abort_reason"])


class BacktestCliTest(unittest.TestCase):
    def test_the_2026_lock_is_enforced_by_default(self):
        """The forward window is the only untouched evidence the project has and
        it cannot be un-seen, so the CLI caps the window unless told otherwise."""
        from quantlab_manager import backtest_cli

        parser_args = backtest_cli.main.__doc__  # keeps the import honest
        self.assertIsNone(parser_args)
        self.assertEqual(backtest_cli.LOCK.year, 2026)
        self.assertIn("mandate", backtest_cli.BRAINS)


if __name__ == "__main__":
    unittest.main()


class UniverseSelectionTest(unittest.TestCase):
    """Selection has to exclude what cannot trend and be honest about bias."""

    def test_stablecoins_are_excluded_by_base_asset(self):
        from quantlab_manager.universes import STABLE_BASES, _base

        self.assertEqual(_base("BTCUSDT"), "BTC")
        self.assertEqual(_base("USDCUSDT"), "USDC")
        self.assertEqual(_base("FDUSDUSDT"), "FDUSD")
        for stable in ("USDC", "FDUSD", "TUSD", "DAI"):
            self.assertIn(stable, STABLE_BASES)
        # a long-only trend system holding a stablecoin is holding cash with
        # extra steps, and turnover would rank them near the top
        self.assertNotIn("BTC", STABLE_BASES)
        self.assertNotIn("SOL", STABLE_BASES)

    def test_the_survivorship_caveat_is_carried_with_the_selection(self):
        """Today's leaders backtested through history flatter the past. The
        selection must say so rather than leave a reader to infer it."""
        from quantlab_manager.universes import select_universe

        class _Settings:
            database_path = "does-not-exist.db"

        with self.assertRaises(Exception):
            select_universe(_Settings(), size=5)


class TestTheRegimeTimeline(unittest.TestCase):
    """The detected major trend, on its way to a chart.

    A regime is a step function, so the wire format is the CHANGES. Sending one
    entry per bar would be a 600 KB payload every fifteen seconds for a run
    loaded from 2017, saying the same word three thousand times.
    """

    def _note(self, when, note):
        return {"timestamp": f"2020-01-{when:02d}T00:00:00+00:00", "note": note}

    def test_it_records_a_change_and_not_a_repetition(self):
        found = regime_timeline(
            [
                self._note(1, "BULL · depth 0% · age 1 · held 0"),
                self._note(2, "BULL · depth 0% · age 2 · held 1"),
                self._note(3, "BEAR · depth 12% · age 0 · held 1"),
                self._note(4, "BEAR · depth 14% · age 1 · held 0"),
                self._note(5, "BULL · depth 0% · age 0 · held 0"),
            ]
        )
        self.assertEqual([x["label"] for x in found], ["BULL", "BEAR", "BULL"])
        self.assertTrue(found[1]["timestamp"].startswith("2020-01-03"))

    def test_a_bar_that_traded_still_carries_its_regime(self):
        """The brain appends the order count to the same note, so the label has
        to survive being followed by more text."""
        found = regime_timeline(
            [self._note(1, "BEAR · depth 30% · age 9 · held 2 · 3 orders")]
        )
        self.assertEqual([x["label"] for x in found], ["BEAR"])

    def test_runs_recorded_before_the_contract_are_still_read(self):
        """Most of the archive wrote the warm-up label as prose. Those labels
        are perfectly good and greying them out would blank the training half of
        every historical run."""
        found = regime_timeline(
            [
                self._note(
                    1,
                    "warming the detector: 1 bars observed, market UNKNOWN, trading opens 2019-06-01",
                ),
                self._note(
                    2,
                    "warming the detector: 90 bars observed, market BEAR, trading opens 2019-06-01",
                ),
            ]
        )
        self.assertEqual([x["label"] for x in found], ["UNKNOWN", "BEAR"])

    def test_notes_that_name_no_regime_are_skipped_rather_than_guessed(self):
        found = regime_timeline(
            [
                self._note(1, ""),
                self._note(2, "aborted: drawdown mandate breached"),
                self._note(3, "BULL · depth 0% · age 0 · held 0"),
            ]
        )
        self.assertEqual([x["label"] for x in found], ["BULL"])

    def test_an_empty_record_is_an_empty_timeline(self):
        self.assertEqual(regime_timeline([]), [])
        self.assertEqual(regime_timeline(None), [])
