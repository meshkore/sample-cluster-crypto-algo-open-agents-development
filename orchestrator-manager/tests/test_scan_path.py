"""The search must screen on the equity path, not only on the average trade.

Written because the fast search and the promotion rule were measuring different
things. The search ranked candidates by mean return per trade; the rule that
decides the record requires surviving eight years without breaching the 25%
drawdown mandate. A mean has no chronology, so the search could not see the
clause that had just disqualified all five systems in the laboratory -- and kept
proposing candidates the rule would reject.

Two defects are pinned here:

- `test_a_run_that_breaches_the_mandate_stops_there` and its neighbours: the book
  aborts at the mandate and everything after it is not counted as evidence.
- `test_the_ledger_is_where_the_cycle_counter_lives`: the supervisor restarts the
  process every six hours, so a counter held in a process variable resets to zero
  and the search re-scores the same grid for ever. Nine cycles were logged before
  this, all of them 0, 1 or 2.

Sabotage-verified: removing the abort in `walk` makes the breach tests report a
recovered equity curve; returning 0 from `resume_from` makes the resume test fail
with exactly the repetition seen in the real ledger.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "hypothesis_scan", ROOT / "orchestrator-manager" / "scripts" / "hypothesis_scan.py"
)
scan = importlib.util.module_from_spec(_spec)
# Registered before execution because a frozen dataclass looks its own module up
# in `sys.modules` while it is being built, and finds nothing if the module is
# still only a local variable.
sys.modules["hypothesis_scan"] = scan
_spec.loader.exec_module(scan)


def _when(*days: str) -> np.ndarray:
    return np.array([f"{d}T00:00:00" for d in days], dtype="datetime64[s]")


def _book(entries, exits, rets, dips=None, vols=None, regimes=None) -> "scan.Book":
    """A trade book with the columns a test does not care about filled in.

    Dips default to zero -- no trade ever touches a stop unless the test says so
    -- volatility to NaN, which `walk` sizes as normal rather than dropping, and
    the regime to zero, which every gate lets through.
    """
    n = len(rets)
    return scan.Book(
        entry=entries,
        exit_at=exits,
        ret=np.asarray(rets, dtype=float),
        dip=np.zeros(n) if dips is None else np.asarray(dips, dtype=float),
        vol=np.full(n, np.nan) if vols is None else np.asarray(vols, dtype=float),
        regime=np.zeros(n) if regimes is None else np.asarray(regimes, dtype=float),
    )


class TheBookWalksInOrder(unittest.TestCase):
    def test_one_trade_compounds_a_third_of_the_book(self):
        """Three slots, so a single position is a third of capital. A +30% trade
        on a third of the book is +10%, not +30%."""
        result = scan.walk(
            _book(_when("2020-01-01"), _when("2020-01-05"), np.array([0.30]))
        )

        self.assertAlmostEqual(result.return_pct, 0.10, places=6)
        self.assertEqual(result.taken, 1)
        self.assertEqual(result.skipped, 0)

    def test_a_fourth_concurrent_signal_finds_no_slot(self):
        """The book is full, so the signal is discarded -- and counted. An
        uncounted discard would report the path of a strategy nobody ran."""
        entries = _when("2020-01-01", "2020-01-01", "2020-01-01", "2020-01-01")
        exits = _when("2020-02-01", "2020-02-01", "2020-02-01", "2020-02-01")
        result = scan.walk(_book(entries, exits, np.array([0.1, 0.1, 0.1, 5.0])))

        self.assertEqual(result.taken, 3)
        self.assertEqual(result.skipped, 1)
        self.assertAlmostEqual(result.return_pct, 0.10, places=6)

    def test_a_slot_frees_when_its_position_exits(self):
        entries = _when("2020-01-01", "2020-01-02", "2020-01-03", "2020-03-01")
        exits = _when("2020-02-01", "2020-02-02", "2020-02-03", "2020-04-01")
        result = scan.walk(_book(entries, exits, np.array([0.0, 0.0, 0.0, 0.30])))

        self.assertEqual(result.taken, 4, "the fourth signal arrives after an exit")
        self.assertEqual(result.skipped, 0)

    def test_trades_are_walked_by_entry_date_not_input_order(self):
        """The basket is concatenated symbol by symbol, so the arrays arrive in
        symbol order. Walking them that way would let a 2024 trade occupy the slot
        a 2019 trade should have had."""
        entries = _when("2021-01-01", "2019-01-01")
        exits = _when("2021-02-01", "2019-02-01")
        result = scan.walk(_book(entries, exits, np.array([0.30, 0.30])))

        self.assertEqual(str(result.last_trade_at)[:10], "2021-02-01")


class TheBookIsMarkedToMarket(unittest.TestCase):
    """A drawdown measured only on closed trades is not the one the mandate means.

    `money` maximises training return SUBJECT TO enduring, so it always selects
    the largest stake that just barely survives -- exactly where an understated
    drawdown does the most damage. Every top row of one cycle sat between 19% and
    25% against a 25% mandate, one reporting +15,945%. The search was choosing
    systems that exploit the flaw in the instrument, not a property of the market.
    """

    def test_an_open_position_deep_underwater_counts_against_the_mandate(self):
        """THE test. One trade that falls 90% before recovering to break even
        breached the mandate on the way, whatever the closing statement says."""
        result = scan.walk(
            _book(_when("2020-01-01"), _when("2020-06-01"), [0.0], dips=[-0.90])
        )

        self.assertIsNotNone(result.breached_at)
        self.assertFalse(result.endures)
        self.assertGreaterEqual(result.max_drawdown, scan.MANDATE)

    def test_marking_on_exits_alone_would_have_called_that_flat(self):
        """The counterfactual, so the test above cannot pass for another reason:
        the trade closes at exactly zero, so realised equity never moves."""
        result = scan.walk(
            _book(_when("2020-01-01"), _when("2020-06-01"), [0.0], dips=[-0.90])
        )

        self.assertAlmostEqual(result.return_pct, 0.0, places=6)

    def test_a_stop_bounds_how_far_a_position_can_be_marked_down(self):
        """A position with a stop leaves at the stop, so it cannot be carried
        below it -- otherwise the stop would protect the return and not the
        drawdown, which is the wrong way round."""
        book = _book(_when("2020-01-01"), _when("2020-06-01"), [0.0], dips=[-0.90])

        self.assertIsNone(scan.walk(book, stop=0.05).breached_at)
        self.assertIsNotNone(scan.walk(book).breached_at)

    def test_concurrent_positions_are_marked_together(self):
        """Three positions each 20% down is a book 20% down, not three separate
        small dips. Correlated falls are the normal case in this basket."""
        entries = _when("2020-01-01", "2020-01-02", "2020-01-03")
        exits = _when("2020-06-01", "2020-06-02", "2020-06-03")
        result = scan.walk(_book(entries, exits, [0.0, 0.0, 0.0], dips=[-0.3] * 3))

        self.assertGreaterEqual(result.max_drawdown, 0.25)
        self.assertIsNotNone(result.breached_at)


class TheMandateEndsTheRun(unittest.TestCase):
    def test_a_run_that_breaches_the_mandate_stops_there(self):
        """THE test. A rule that loses a quarter of the book has aborted, and the
        years after the abort are not evidence it earned -- they are the years it
        was not there for. Announcing a system on those years is what happened."""
        entries = _when("2021-01-01", "2023-01-01")
        exits = _when("2021-07-19", "2023-06-01")
        result = scan.walk(_book(entries, exits, np.array([-0.80, 10.0])))

        self.assertEqual(str(result.breached_at)[:10], "2021-07-19")
        self.assertFalse(result.endures)
        self.assertLess(result.return_pct, 0.0, "the 2023 recovery is not counted")

    def test_a_drawdown_just_under_the_mandate_survives(self):
        """The edge, from the other side, so the abort is a threshold rather than
        a direction."""
        entries = _when("2021-01-01", "2025-12-01")
        exits = _when("2021-07-19", "2025-12-15")
        result = scan.walk(_book(entries, exits, np.array([-0.70, 0.0])))

        self.assertIsNone(result.breached_at)
        self.assertLess(result.max_drawdown, scan.MANDATE)
        self.assertTrue(result.endures)

    def test_going_quiet_years_early_is_not_surviving_either(self):
        """Generation 5 finished the era; the systems that scored higher stopped
        in 2021 and 2022. Both failures have to be visible or the search will keep
        offering the second kind."""
        result = scan.walk(
            _book(_when("2022-01-01"), _when("2022-06-01"), np.array([0.10]))
        )

        self.assertIsNone(result.breached_at, "it did not breach -- it just stopped")
        self.assertFalse(result.endures)

    def test_a_candidate_with_no_trades_at_all_does_not_endure(self):
        """An empty book has no drawdown, and a rule that reads `not breached` as
        `survived` would rank it top."""
        empty = np.array([], dtype="datetime64[s]")
        result = scan.walk(_book(empty, empty, np.array([], dtype=float)))

        self.assertFalse(result.endures)
        self.assertEqual(result.taken, 0)

    def test_the_grace_window_matches_the_promotion_rule(self):
        """One definition of surviving the era, imported, not restated. If these
        two ever disagree the search proposes what the rule rejects."""
        from quantlab_manager.promotion import RESEARCH_ENDS, SURVIVAL_GRACE_DAYS

        self.assertEqual(scan.RESEARCH_ENDS, RESEARCH_ENDS)
        self.assertEqual(scan.SURVIVAL_GRACE_DAYS, SURVIVAL_GRACE_DAYS)


class SizingIsSearched(unittest.TestCase):
    """Because the unsized version rejected everything for the same reason.

    Fifty-one entry rules paid in both eras and all fifty-one breached the
    mandate, most of them in the same three months of early 2018. When every
    entry rule dies in one window, sizing is the variable.
    """

    def test_a_smaller_stake_can_carry_a_book_a_full_stake_cannot(self):
        entries = _when("2018-01-01", "2025-12-01")
        exits = _when("2018-01-10", "2025-12-10")

        full = scan.walk(_book(entries, exits, np.array([-0.90, 0.0])))
        small = scan.walk(_book(entries, exits, np.array([-0.90, 0.0])), stake=0.08)

        self.assertFalse(full.endures, "a third of the book on a -90% trade")
        self.assertTrue(small.endures)

    def test_the_stop_fires_on_the_dip_and_costs_the_round_trip(self):
        result = scan.walk(
            _book(_when("2020-01-01"), _when("2020-01-10"), [-0.90], dips=[-0.90]),
            stop=0.10,
        )

        self.assertAlmostEqual(result.return_pct, (-0.10 - scan.ROUND_TRIP) / 3, 6)

    def test_a_winner_that_fell_through_the_stop_is_stopped_out(self):
        """THE hindsight test. Applying the stop to the FINAL return truncates
        every loser and keeps every winner that dipped through the stop on the way
        up. That version reported +167,505% over the research era."""
        result = scan.walk(
            _book(_when("2020-01-01"), _when("2020-01-10"), [+0.60], dips=[-0.20]),
            stop=0.10,
        )

        self.assertLess(result.return_pct, 0.0, "it was out before the +60%")

    def test_a_winner_that_never_dipped_keeps_its_gain(self):
        result = scan.walk(
            _book(_when("2020-01-01"), _when("2020-01-10"), [+0.60], dips=[-0.02]),
            stop=0.10,
        )

        self.assertAlmostEqual(result.return_pct, 0.20, places=6)

    def test_no_stop_is_in_the_grid_so_a_stop_has_to_earn_its_place(self):
        self.assertIn(None, scan.STOPS)

    def test_no_gate_is_in_the_grid_so_the_gate_has_to_earn_its_place(self):
        self.assertIn(None, scan.GATES)

    def test_a_gate_refuses_the_trades_taken_in_a_deep_drawdown(self):
        """The mechanism itself: the market was 60% off its peak, so the book
        stands aside and never takes the loss."""
        entries = _when("2022-01-01", "2022-06-01")
        exits = _when("2022-02-01", "2022-07-01")
        book = _book(entries, exits, [-0.50, 0.10], regimes=[0.60, 0.05])

        ungated = scan.walk(book)
        gated = scan.walk(book.where(book.regime <= 0.40))

        self.assertLess(ungated.return_pct, 0.0)
        self.assertGreater(gated.return_pct, 0.0)

    def test_a_gate_cannot_win_by_refusing_almost_everything(self):
        """A tight gate reaches zero drawdown trivially by taking three trades.
        Without a floor on the gated book that is what the search would pick, and
        the record would be a strategy with no evidence behind it."""
        n = 200
        # Spread evenly across the research era so the ungated book reaches the
        # end of it and can endure at all.
        entries = np.datetime64("2018-01-01T00:00:00", "s") + np.linspace(
            0, 2890, n
        ).astype(int) * np.timedelta64(1, "D")
        exits = entries + np.timedelta64(5, "D")
        # The five winners are SPREAD ACROSS the era, so the gated book of just
        # those five reaches 2025 and endures. Bunch them at the start and the
        # survival clause rejects the gate for you, and this test passes without
        # the floor doing any work -- which is how it first passed.
        winners = np.zeros(n, dtype=bool)
        winners[[0, 50, 100, 150, n - 1]] = True
        rets = np.where(winners, 0.50, -0.005)
        regimes = np.where(winners, 0.05, 0.60)
        rule, _ = scan.money(_book(entries, exits, rets, regimes=regimes))

        self.assertIsNotNone(rule)
        # EVERY gate here keeps only those five trades, so the right answer is no
        # gate at all. Naming particular thresholds instead let the search win
        # with a wider one that kept exactly the same five.
        self.assertIsNone(rule["gate"], "a gate kept only five trades and won")

    def test_flat_sizing_is_in_the_grid_so_volatility_management_must_earn_it(self):
        self.assertIn(None, scan.TARGETS)

    def test_a_calm_trade_is_sized_up_and_a_wild_one_down(self):
        """Volatility-managed sizing: the same signal, the same return, twice the
        position when the tape was half as volatile."""
        calm = scan.walk(
            _book(_when("2020-01-01"), _when("2020-01-10"), [0.30], vols=[0.005]),
            target_vol=0.010,
        )
        wild = scan.walk(
            _book(_when("2020-01-01"), _when("2020-01-10"), [0.30], vols=[0.020]),
            target_vol=0.010,
        )

        self.assertGreater(calm.return_pct, wild.return_pct)
        self.assertAlmostEqual(calm.return_pct / wild.return_pct, 4.0, places=6)

    def test_the_scale_is_bounded_so_a_calm_tape_cannot_lever_the_book(self):
        """An unbounded inverse-volatility rule sizes on the reciprocal of a small
        number, which is where that idea usually goes wrong."""
        result = scan.walk(
            _book(_when("2020-01-01"), _when("2020-01-10"), [0.30], vols=[1e-9]),
            target_vol=0.010,
        )

        self.assertAlmostEqual(result.return_pct, 0.30 * scan.VOL_CAP / 3, places=6)

    def test_an_unmeasurable_volatility_sizes_normally_rather_than_dropping(self):
        """Dropping it would make the volatility window a second, invisible entry
        filter, and the trade count would silently stop matching the signal."""
        result = scan.walk(
            _book(_when("2020-01-01"), _when("2020-01-10"), [0.30], vols=[np.nan]),
            target_vol=0.010,
        )

        self.assertEqual(result.taken, 1)
        self.assertAlmostEqual(result.return_pct, 0.10, places=6)

    def test_the_volatility_window_looks_only_backwards(self):
        """A position size that knows the volatility of the move it is about to
        take is not a position size, it is a forecast."""
        tape = scan.load("research", "BTCUSDT")
        if tape is None:
            self.skipTest("research tape not present in this checkout")

        window = 5 * scan.BARS_PER_DAY
        vol = tape.trailing_vol(window)
        self.assertTrue(np.all(np.isnan(vol[:window])))
        self.assertTrue(np.isfinite(vol[window + 1]))

    def test_money_returns_the_best_enduring_configuration(self):
        entries = _when("2018-01-01", "2025-12-01")
        exits = _when("2018-01-10", "2025-12-10")
        rule, walked = scan.money(
            _book(entries, exits, [-0.90, 0.50], dips=[-0.90, 0.0])
        )

        self.assertIsNotNone(rule)
        self.assertTrue(walked.endures)

    def test_nothing_enduring_is_reported_as_nothing_not_as_the_least_bad(self):
        """A search that always returns its best row turns `no candidate` into a
        candidate, which is how a laboratory ends up promoting a coin flip."""
        entries = _when("2018-01-01")
        exits = _when("2018-01-10")
        rule, walked = scan.money(_book(entries, exits, [-0.99], dips=[-0.99]))

        self.assertIsNone(rule)
        self.assertIsNone(walked)

    def test_the_sealed_era_never_chooses_the_sizing(self):
        """2026 is the forward evaluation. `money` is handed training trades and
        has no argument through which the sealed era could reach it -- checked on
        the signature, because a comment saying so would not stop the next edit."""
        import inspect

        self.assertEqual(list(inspect.signature(scan.money).parameters), ["book"])


class TheSealedTapeIsWarmedButNotTraded(unittest.TestCase):
    """The sealed file begins on 2026-01-01 with nothing in front of it.

    A trailing mean over 30 days therefore had no value until the end of January,
    and one over 90 days none until April, so candidates with long trend windows
    sat out the start of a falling year because their indicator was cold. It
    scored as skill: rank correlation +0.366 between trend length and the 2026
    result. Warm-up history fixes it, and must never itself be tradeable.
    """

    def test_the_warm_up_history_is_not_tradeable(self):
        tape = scan.load("forward", "BTCUSDT", warm=True)
        if tape is None:
            self.skipTest("sealed tape not present in this checkout")

        first = tape.stamp[tape.tradeable][0]
        self.assertEqual(str(first)[:10], scan.FORWARD_STARTS)
        self.assertLess(
            str(tape.stamp[0])[:10],
            scan.FORWARD_STARTS,
            "there is history in front of the first tradeable bar",
        )

    def test_a_long_trend_window_is_warm_on_the_first_trading_day(self):
        """The point of the warm-up: the widest window in the grid has a value on
        2026-01-01, so windows of different lengths are comparable."""
        tape = scan.load("forward", "BTCUSDT", warm=True)
        if tape is None:
            self.skipTest("sealed tape not present in this checkout")

        trail = tape.trailing_mean(90 * scan.BARS_PER_DAY)
        opening = np.flatnonzero(tape.tradeable)[0]
        self.assertTrue(np.isfinite(trail[opening]))

    def test_an_unwarmed_tape_is_tradeable_throughout(self):
        tape = scan.load("research", "BTCUSDT")
        if tape is None:
            self.skipTest("research tape not present in this checkout")

        self.assertTrue(tape.tradeable.all())

    def test_no_entry_is_taken_before_the_sealed_era_opens(self):
        """The load-bearing one. Warm-up bars feeding the indicators is correct;
        warm-up bars producing TRADES would be the research era leaking into the
        sealed result, which is the opposite of what this era is for."""
        tape = scan.load("forward", "BTCUSDT", warm=True)
        if tape is None:
            self.skipTest("sealed tape not present in this checkout")

        index, _ = scan._entries(tape, scan.Candidate(4, 0.015, 3, 30))
        opens = np.flatnonzero(tape.tradeable)[0]
        self.assertTrue((index >= opens).all(), "a trade opened in the warm-up")


class TheSealedYearNeverSelects(unittest.TestCase):
    """2026 is a locked forward evaluation and never feedback -- and a filter is
    feedback however quietly it is spelled.

    `survives` used to require the sealed mean to be positive. Reading the best
    2026 figure off a shortlist that 2026 helped choose reports a margin over the
    incumbent that is partly the selection.
    """

    def test_a_candidate_losing_2026_still_reaches_the_shortlist(self):
        training = {"n": 3000, "mean_net": 0.014, "t": 6.0}
        losing = {"n": 30, "mean_net": -0.02}

        self.assertTrue(scan.survives(training, losing))

    def test_the_sealed_era_is_still_asked_for_a_minimum_SAMPLE(self):
        """Sample size is a statement about how much evidence exists, not about
        what it says. Four trades cannot be compared with thirty."""
        training = {"n": 3000, "mean_net": 0.014, "t": 6.0}

        self.assertFalse(scan.survives(training, {"n": 4, "mean_net": 0.05}))

    def test_the_sealed_book_needs_a_sample_the_sealed_signal_does_not_supply(self):
        """`survives` counts SIGNALS, and then the gate and the three slots throw
        most of them away. The first cycle after the gate went in reported its top
        candidates on 2, 7, 7, 6 and one sealed trade, every one of which had
        passed the fifteen-signal clause upstream."""
        self.assertGreaterEqual(scan.MINIMUM_SEALED_TRADES, 15)

    def test_a_weak_research_era_is_still_refused(self):
        """Dropping the sealed clause must not turn the screen into a sieve."""
        self.assertFalse(
            scan.survives({"n": 3000, "mean_net": 0.014, "t": 1.2}, {"n": 30})
        )
        self.assertFalse(
            scan.survives({"n": 3000, "mean_net": -0.01, "t": 6.0}, {"n": 30})
        )


class TheSearchRemembersWhereItGotTo(unittest.TestCase):
    def test_the_ledger_is_where_the_cycle_counter_lives(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Path(folder) / "ledger.jsonl"
            ledger.write_text(
                "\n".join(
                    json.dumps({"cycle": c, "survivors": 0}) for c in (0, 1, 2, 0, 1)
                )
                + "\n"
            )

            self.assertEqual(scan.resume_from(ledger), 3)

    def test_every_row_records_what_its_numbers_mean(self):
        """The ledger is this search's whole memory, and the screen has changed
        three times in two days -- a per-trade mean, then an equity path marked on
        exits, then one marked to market. Rows whose semantics changed silently
        under them are worse than no rows, because they get compared."""
        self.assertGreaterEqual(scan.SCREEN_VERSION, 3)

    def test_an_absent_ledger_starts_at_the_beginning(self):
        self.assertEqual(scan.resume_from(Path("/nonexistent/ledger.jsonl")), 0)

    def test_a_truncated_last_line_does_not_reset_the_search(self):
        """The ledger is appended to by a loop that can be killed mid-write, and
        a half-written line must not send the search back to cycle 0."""
        with tempfile.TemporaryDirectory() as folder:
            ledger = Path(folder) / "ledger.jsonl"
            ledger.write_text(json.dumps({"cycle": 7}) + '\n{"cycle": 8, "surviv')

            self.assertEqual(scan.resume_from(ledger), 8)


class TheGridStopsGrowing(unittest.TestCase):
    def test_the_axes_widen_with_the_cycle(self):
        early = scan.axes(0)
        later = scan.axes(4)

        self.assertGreater(len(later[1]), len(early[1]), "holds widen")
        self.assertGreater(len(later[2]), len(early[2]), "trends widen")

    def test_a_cycle_can_always_finish(self):
        """Unbounded growth means a cycle eventually outlives the six-hour window
        and the ledger stops gaining lines at all."""
        thresholds, holds, trends, saturated = scan.axes(500)

        self.assertTrue(saturated)
        self.assertLessEqual(24 * len(thresholds) * len(holds) * len(trends), 30_000)

    def test_saturation_is_reported_not_hidden(self):
        """Once the space is covered, further cycles are re-scans. A search that
        does not say so reads as continuing progress."""
        self.assertFalse(scan.axes(0)[3])
        self.assertTrue(scan.axes(500)[3])


if __name__ == "__main__":
    unittest.main()
