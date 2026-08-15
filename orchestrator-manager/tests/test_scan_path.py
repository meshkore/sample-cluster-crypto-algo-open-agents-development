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

from quantlab_manager import quality

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


def _book(
    entries, exits, rets, dips=None, vols=None, regimes=None, marks=None
) -> "scan.Book":
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
        marks=(
            tuple(np.array([], dtype=float) for _ in range(n))
            if marks is None
            else tuple(np.asarray(path, dtype=float) for path in marks)
        ),
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

    def test_the_quality_path_sees_a_slow_bleed_while_the_trade_is_open(self):
        """THE regression for screen/engine disagreement.

        Entry-only and exit-only marking calls this a flat account. A regular
        calendar must show the holder losing money between those two events,
        even when the trade eventually recovers and closes flat.
        """
        result = scan.walk(
            _book(
                _when("2020-01-01"),
                _when("2020-04-01"),
                [0.0],
                marks=[[0.0, -0.05, -0.10, -0.15, -0.10, -0.05, 0.0]],
            )
        )

        equity = [value for _, value in result.path]
        self.assertLess(min(equity), equity[0])
        self.assertGreater(result.judged().ulcer_index, 0.0)

    def test_the_marked_curve_ends_exactly_where_the_walk_says_it_ended(self):
        """Two numbers describing one account must not need a tolerance to agree.

        The marked calendar rebuilds equity day by day while `return_pct`
        accumulates it trade by trade, and nothing forces the two to meet. They
        did not: measured across sixteen real walks the gap ran to eight parts in
        ten thousand, always in the same direction, because the curve opened on
        the first ENTRY -- a day that already carries that position's round trip,
        so the baseline every later ratio divides by was below the opening
        capital. The curve now opens on the day before, at exactly 1.0.
        """
        result = scan.walk(
            _book(
                _when("2020-01-01", "2020-02-01"),
                _when("2020-01-11", "2020-02-11"),
                [0.10, -0.04],
                marks=[[0.0, 0.03, 0.06], [0.0, -0.02, -0.03]],
            ),
            stake=0.2,
        )

        self.assertIsNone(result.breached_at)
        self.assertAlmostEqual(result.path[0][1], 1.0, places=12, msg="opens at par")
        self.assertAlmostEqual(
            result.judged().final_return, result.return_pct, places=12
        )

    def test_a_breached_walk_cannot_score_however_its_path_is_built(self):
        """A breach returns the raw event path, which does NOT end where
        `return_pct` says -- the last point is marked equity including unrealised
        losses, the return is realised only. That mismatch is harmless because
        such a walk can never score: it stops at the moment it is 25% below its
        peak, so its worst-entry return is about -25%, and the `unlucky` term
        floors at -10%. Structural, not luck -- verified across every breached
        walk in a 48-configuration sweep of the real tapes, all exactly 0.0.
        """
        result = scan.walk(
            _book(
                _when("2020-01-01", "2020-02-01", "2020-03-01"),
                _when("2020-01-15", "2020-02-15", "2020-03-15"),
                [-0.30, -0.30, 0.50],
            ),
            stake=1.0,
        )

        self.assertIsNotNone(result.breached_at)
        self.assertEqual(result.judged().score, 0.0)


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

    def test_the_gate_is_a_prior_and_not_a_fitted_parameter(self):
        """Fitting it per candidate was measured to be harmful: the objective is
        return SUBJECT TO a drawdown mandate, and a tight gate satisfies the
        mandate by refusing to trade. Of 1,110 systems fitted that way, 96 kept
        enough sealed trades to judge."""
        self.assertFalse(hasattr(scan, "GATES"), "the gate is applied, not searched")
        self.assertIsInstance(scan.MARKET_GATE, float)

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

    def test_a_gate_that_leaves_too_few_trades_reports_nothing(self):
        """A book the gate reduces to a handful is refused outright rather than
        returned with a flattering figure.

        The gate reaches zero drawdown trivially by taking five trades, and the
        record would then be a strategy with no evidence behind it. `None` is the
        honest answer: this entry rule cannot be run under the prior.
        """
        n = 200
        # Spread evenly across the research era so the book reaches the end of it
        # and cannot be rejected by the survival clause instead of the floor.
        entries = np.datetime64("2018-01-01T00:00:00", "s") + np.linspace(
            0, 2890, n
        ).astype(int) * np.timedelta64(1, "D")
        exits = entries + np.timedelta64(5, "D")
        survives_gate = np.zeros(n, dtype=bool)
        survives_gate[[0, 50, 100, 150, n - 1]] = True
        rets = np.where(survives_gate, 0.50, -0.005)
        # Everything else is taken while the market is 60% down, so the prior
        # refuses it and five trades remain.
        regimes = np.where(survives_gate, 0.05, 0.60)

        rule, walked = scan.money(_book(entries, exits, rets, regimes=regimes))

        self.assertIsNone(rule, "five trades were enough to be reported")
        self.assertIsNone(walked)

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

    def _spread(self, n, rets, dips=None, regimes=None):
        """A book of `n` trades spread across the whole research era.

        Trades must reach the end of the era or `endures` rejects them before any
        of the sizing logic is reached, and there must be at least
        `MINIMUM_TRADES` of them or the gated book is refused for thinness.
        """
        entries = np.datetime64("2018-01-01T00:00:00", "s") + np.linspace(
            0, 2890, n
        ).astype(int) * np.timedelta64(1, "D")
        return _book(
            entries, entries + np.timedelta64(5, "D"), rets, dips, None, regimes
        )

    def test_money_returns_the_best_enduring_configuration(self):
        n = 60
        rets = np.where(np.arange(n) % 2 == 0, 0.20, -0.05)

        rule, walked = scan.money(self._spread(n, rets))

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


class TheShapeIsMeasuredAgainstTheCalendarNotTheTradeCount(unittest.TestCase):
    """Two of the six shape measures read the path as if its points were evenly
    spaced, and they are not: a busy fortnight holds more points than a quiet
    year. The calendar makes them answer how the ACCOUNT behaved over time
    rather than how the trades happened to be arranged.

    `test_a_flat_month_breaks_a_losing_streak_rather_than_extending_it` is here
    because the first version of this file asserted the opposite. The arena's
    first published system screened at 0.317 with a four-month losing streak and
    the engine scored it 0.000 on a seven-month one, and the tempting explanation
    -- that the screen could not see the months it had no trades in -- is not the
    cause. That gap is a model difference the screen cannot close: the engine
    revalues open positions every bar, the screen only marks at events.
    """

    def test_the_calendar_fills_the_gaps_between_events(self):
        path = (("2020-01-01T00:00:00", 1.0), ("2020-04-01T00:00:00", 0.9))
        stamps, equity = scan._calendar(path)

        self.assertEqual(len(stamps), 92, "January to April inclusive")
        self.assertEqual(stamps[0], "2020-01-01")
        self.assertEqual(stamps[-1], "2020-04-01")
        self.assertEqual(equity[0], 1.0)
        self.assertEqual(equity[-1], 0.9)

    def test_equity_is_carried_forward_and_never_interpolated(self):
        """Between events the marked value does not change in this model. A
        straight line drawn between two events would invent a curve nothing
        measured, and would smooth away the very drops being counted."""
        path = (("2020-01-01T00:00:00", 1.0), ("2020-03-01T00:00:00", 0.5))
        _, equity = scan._calendar(path)

        self.assertTrue(all(value == 1.0 for value in equity[:-1]))
        self.assertEqual(equity[-1], 0.5)

    def test_a_flat_month_breaks_a_losing_streak_rather_than_extending_it(self):
        """The correction. Carrying equity forward means a month with no trades
        returns exactly zero, and zero is not a loss."""
        path = tuple(
            (f"2020-{month:02d}-15T00:00:00", 1.0 - 0.02 * month)
            for month in (1, 2, 5, 8)
        )
        sparse = quality.judge([s for s, _ in path], [v for _, v in path])
        filled = quality.judge(*scan._calendar(path))

        self.assertEqual(sparse.longest_losing_months, 3, "three events, all down")
        self.assertLess(filled.longest_losing_months, sparse.longest_losing_months)

    def test_a_long_quiet_stretch_underwater_now_costs_what_it_should(self):
        """The ulcer index averages over points. On the raw path a year spent
        underwater with two trades in it weighs two points; on the calendar it
        weighs a year."""
        path = (
            ("2020-01-01T00:00:00", 1.0),
            ("2020-01-02T00:00:00", 0.8),
            ("2021-01-01T00:00:00", 0.8),
        )
        sparse = quality.ulcer([value for _, value in path])
        filled = quality.ulcer(scan._calendar(path)[1])

        self.assertGreater(filled, sparse)

    def test_the_last_event_of_a_day_wins(self):
        """Same convention `quality.monthly` uses for months, and the same one
        the mirror uses when it thins a published curve to one point per day."""
        path = (("2020-01-01T06:00:00", 1.0), ("2020-01-01T18:00:00", 1.5))
        stamps, equity = scan._calendar(path)

        self.assertEqual(stamps, ["2020-01-01"])
        self.assertEqual(equity, [1.5])

    def test_an_empty_path_is_empty_rather_than_a_crash(self):
        self.assertEqual(scan._calendar(()), ([], []))
