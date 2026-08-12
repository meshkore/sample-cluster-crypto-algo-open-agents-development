"""The labels and the splits, sabotage-verified.

Every test here fails under a specific plausible mistake, and the mistake is
named in the docstring. A test that passes under the bug it was written for is
worse than no test: it certifies the bug.
"""

from __future__ import annotations

import unittest

import numpy as np

from quantlab_ml.labels import (
    Barriers,
    net_of_costs,
    realised_volatility,
    triple_barrier,
)
from quantlab_ml.splits import purged_walk_forward, thin_to_independent


def _per_bar_vol(effective: float, horizon: int) -> float:
    """The one-bar volatility that produces `effective` width over `horizon` bars.

    Barriers sit at `multiple * sigma * sqrt(horizon)`, because a position held
    for H bars is exposed to H bars of volatility. Tests state the effective
    width they mean and convert here, so a change to that scaling fails loudly
    instead of quietly moving every fixture underneath them.
    """
    return effective / np.sqrt(horizon)


class TripleBarrierTest(unittest.TestCase):
    def test_the_target_is_labelled_when_it_is_reached_first(self):
        close = np.full(50, 100.0)
        high, low = close.copy(), close.copy()
        high[5] = 130.0  # a decisive move up on bar 5
        volatility = np.full(50, _per_bar_vol(0.10, 20))
        volatility[:1] = np.nan
        out = triple_barrier(high, low, close, volatility, Barriers(2.0, 1.0, 20))
        self.assertEqual(out["label"][1], 1)
        self.assertEqual(out["ends_at"][1], 5)

    def test_the_stop_is_labelled_when_it_is_reached_first(self):
        close = np.full(50, 100.0)
        high, low = close.copy(), close.copy()
        low[3] = 70.0
        volatility = np.full(50, _per_bar_vol(0.10, 20))
        volatility[:1] = np.nan
        out = triple_barrier(high, low, close, volatility, Barriers(2.0, 1.0, 20))
        self.assertEqual(out["label"][1], -1)
        self.assertEqual(out["ends_at"][1], 3)

    def test_the_stop_wins_a_bar_that_spans_both_barriers(self):
        """The stated pessimistic assumption. Reversing the two checks -- the
        single most natural way to write this function -- flips this label and
        makes every violent bar in the dataset look like a winner."""
        close = np.full(20, 100.0)
        high, low = close.copy(), close.copy()
        high[2], low[2] = 130.0, 70.0
        volatility = np.full(20, _per_bar_vol(0.10, 10))
        volatility[:1] = np.nan
        out = triple_barrier(high, low, close, volatility, Barriers(2.0, 1.0, 10))
        self.assertEqual(
            out["label"][1], -1, "an ambiguous bar was read optimistically"
        )

    def test_barriers_scale_with_volatility_rather_than_being_fixed(self):
        """The sealed window's lesson as a test: the same 5% move must resolve
        differently in a quiet regime and a violent one. A fixed-percentage
        barrier passes every other test in this file and fails this one."""
        close = np.full(40, 100.0)
        high, low = close.copy(), close.copy()
        high[4] = 105.0
        quiet = np.full(40, _per_bar_vol(0.01, 20))
        violent = np.full(40, _per_bar_vol(0.10, 20))
        quiet[:1] = violent[:1] = np.nan
        hit = triple_barrier(high, low, close, quiet, Barriers(2.0, 1.0, 20))
        missed = triple_barrier(high, low, close, violent, Barriers(2.0, 1.0, 20))
        self.assertEqual(hit["label"][1], 1, "a 5% move should clear a 2% barrier")
        self.assertEqual(missed["label"][1], 0, "a 5% move should not clear a 20% one")

    def test_the_horizon_resolves_a_bar_that_touches_nothing(self):
        close = np.full(30, 100.0)
        volatility = np.full(30, _per_bar_vol(0.05, 10))
        volatility[:1] = np.nan
        out = triple_barrier(close, close, close, volatility, Barriers(2.0, 1.0, 10))
        self.assertEqual(out["label"][1], 0)
        self.assertEqual(out["ends_at"][1], 11)
        self.assertTrue(out["touched"][1])

    def test_a_series_ending_early_is_marked_unresolved(self):
        """Otherwise the last horizon of every dataset is labelled flat, and the
        model learns that markets go quiet at the end of the file."""
        close = np.full(30, 100.0)
        volatility = np.full(30, _per_bar_vol(0.05, 10))
        volatility[:1] = np.nan
        out = triple_barrier(close, close, close, volatility, Barriers(2.0, 1.0, 10))
        self.assertFalse(out["touched"][25], "a truncated window was reported resolved")

    def test_volatility_never_reads_a_future_bar(self):
        """Sabotage: a centred or two-pass estimator passes every other test here
        and leaks the future into every label built on it."""
        rng = np.random.default_rng(0)
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, 600)))
        full = realised_volatility(close, span=50)
        truncated = realised_volatility(close[:400], span=50)
        np.testing.assert_allclose(full[:400], truncated, rtol=1e-12, equal_nan=True)

    def test_the_barrier_widens_with_the_square_root_of_the_horizon(self):
        """A position held H bars is exposed to H bars of volatility, so the
        barrier has to grow as sqrt(H). Without this the barriers are set from a
        ONE-BAR sigma: at five minutes that is a 0.4% target against a 0.30%
        round trip, the toll eats three quarters of the prize, and the cost
        filter correctly refuses almost everything -- measured, eight trades
        taken out of 319,000 test rows."""
        n = 400
        close = np.full(n, 100.0)
        high, low = close.copy(), close.copy()
        high[3] = 108.0  # +8%
        sigma = np.full(n, 0.01)  # one bar
        sigma[:1] = np.nan
        # 2 sigma over 4 bars = 2 * 0.01 * 2 = 4%: an 8% move clears it.
        short = triple_barrier(high, low, close, sigma, Barriers(2.0, 1.0, 4))
        # 2 sigma over 100 bars = 2 * 0.01 * 10 = 20%: the same move does not.
        long = triple_barrier(high, low, close, sigma, Barriers(2.0, 1.0, 100))
        self.assertEqual(short["label"][1], 1)
        self.assertEqual(
            long["label"][1], 0, "the barrier did not widen with the horizon"
        )

    def test_costs_come_off_the_label(self):
        np.testing.assert_allclose(net_of_costs(np.array([0.01])), np.array([0.007]))


class PurgedWalkForwardTest(unittest.TestCase):
    def _ends(self, n: int, horizon: int) -> np.ndarray:
        return np.minimum(np.arange(n) + horizon, n - 1)

    def test_no_training_label_resolves_inside_its_test_block(self):
        """The overlap leak. Without the purge this assertion fails on every
        fold, and nothing else in a normal metrics table would show it."""
        n, horizon = 60_000, 864
        ends = self._ends(n, horizon)
        for fold in purged_walk_forward(ends, folds=4, embargo=0, minimum_train=20_000):
            self.assertLess(
                ends[fold.train].max(),
                fold.test.min(),
                f"fold {fold.index} trained on a label decided inside its test block",
            )

    def test_the_embargo_leaves_a_gap_before_each_test_block(self):
        n = 60_000
        ends = self._ends(n, 864)
        for fold in purged_walk_forward(
            ends, folds=4, embargo=864, minimum_train=20_000
        ):
            self.assertLessEqual(
                fold.train.max(),
                fold.test.min() - 864,
                "training ran up to the edge of the test block",
            )

    def test_the_embargo_only_adds_to_the_purge_when_it_exceeds_the_horizon(self):
        """Measured rather than assumed, because the first version of this test
        asserted the embargo always drops rows and it does not.

        With `embargo <= horizon` the purge has already removed every row in the
        band -- any observation within one horizon of the test block resolves
        inside it by construction -- so the embargo counts zero and the gap is
        still correct. It bites only when it reaches further back than the label
        does, which is the case worth having a knob for."""
        ends = self._ends(60_000, 864)
        same = purged_walk_forward(ends, folds=4, embargo=864, minimum_train=20_000)
        self.assertTrue(
            all(f.embargoed == 0 for f in same),
            "an embargo inside the horizon should be subsumed by the purge",
        )
        wider = purged_walk_forward(ends, folds=4, embargo=5_000, minimum_train=20_000)
        self.assertTrue(all(f.embargoed > 0 for f in wider))
        for fold in wider:
            self.assertLessEqual(fold.train.max(), fold.test.min() - 5_000)

    def test_training_never_contains_a_bar_after_its_test_block(self):
        """Walk-forward, not K-fold. Shuffling passes every accuracy check and
        answers a question nobody can trade."""
        ends = self._ends(60_000, 864)
        for fold in purged_walk_forward(ends, folds=4, minimum_train=20_000):
            self.assertTrue((fold.train < fold.test.min()).all())

    def test_folds_do_not_overlap_and_cover_the_tail(self):
        ends = self._ends(60_000, 864)
        folds = purged_walk_forward(ends, folds=4, minimum_train=20_000)
        covered = np.concatenate([f.test for f in folds])
        self.assertEqual(len(covered), len(set(covered.tolist())))
        self.assertEqual(covered.max(), 59_999)

    def test_thinning_leaves_no_two_overlapping_windows(self):
        ends = self._ends(5_000, 100)
        kept = thin_to_independent(ends)
        for a, b in zip(kept, kept[1:]):
            self.assertGreater(b, ends[a], "two kept observations share a window")

    def test_an_impossible_configuration_raises_rather_than_returning_junk(self):
        with self.assertRaises(ValueError):
            purged_walk_forward(self._ends(100, 10), folds=6, minimum_train=20_000)


if __name__ == "__main__":
    unittest.main()
