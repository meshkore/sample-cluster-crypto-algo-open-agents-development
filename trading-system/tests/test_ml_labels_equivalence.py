"""The fast label path must equal the readable one exactly, not approximately.

`triple_barrier` was 37% of the time spent building an observation table -- a
nested Python loop over 3.97 million rows by up to 864 bars each -- so it is now
vectorised with sliding windows. Every number this laboratory has ever published
rests on those labels, so "faster and almost the same" would be worse than slow:
a label set that is 0.1% different is a different experiment reported under the
old name.

`labels._reference` is the nested loop, kept in the module as the definition of
the rule. These tests are the equivalence proof, on random data across the
regimes that exercise each branch: barriers so tight everything stops, so wide
everything times out, and in between where the race is actually close.

Sabotage-verified: flipping `first_down <= first_up` to `<` in `_vectorised`
turns the tie test red, and off-by-one errors in the window offset turn the
`ends_at` comparison red.
"""

from __future__ import annotations

import unittest

import numpy as np

from quantlab_ml.labels import Barriers, _reference, _vectorised, triple_barrier


def _series(n: int, seed: int, drift: float = 0.0, sigma: float = 0.004):
    """A random walk with intrabar range, which is what the barriers scan."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(drift, sigma, n)))
    span = np.abs(rng.normal(0.0, sigma, n)) * close
    return close + span, close - span, close


def _volatility(n: int, seed: int, sigma: float = 0.004):
    rng = np.random.default_rng(seed + 1)
    return np.abs(rng.normal(sigma, sigma / 4, n))


class TheFastPathIsTheSamePath(unittest.TestCase):
    def _compare(self, barriers, n=3_000, seed=7, **kwargs):
        high, low, close = _series(n, seed, **kwargs)
        volatility = _volatility(n, seed)
        fast = _vectorised(high, low, close, volatility, barriers)
        slow = _reference(high, low, close, volatility, barriers)
        for key in ("label", "ends_at", "touched"):
            np.testing.assert_array_equal(
                fast[key], slow[key], err_msg=f"{key} differs from the reference"
            )
        np.testing.assert_allclose(fast["ret"], slow["ret"], rtol=0, atol=0)
        return fast

    def test_the_default_barriers_agree(self):
        outcome = self._compare(Barriers(2.0, 1.0, 864))
        # A guard against agreeing because neither resolved anything.
        self.assertGreater(int((outcome["label"] != 0).sum()), 0)

    def test_a_short_horizon_agrees(self):
        """Short horizons make the tail fall-back a large fraction of the rows,
        which is where the two implementations are stitched together."""
        self._compare(Barriers(2.0, 1.0, 24))

    def test_tight_barriers_that_almost_always_resolve_agree(self):
        outcome = self._compare(Barriers(0.05, 0.05, 100))
        resolved = int((outcome["label"] != 0).sum())
        self.assertGreater(resolved, len(outcome["label"]) // 2)

    def test_wide_barriers_that_almost_always_time_out_agree(self):
        outcome = self._compare(Barriers(50.0, 50.0, 100))
        self.assertGreater(int((outcome["label"] == 0).sum()), 0)

    def test_a_trending_series_agrees(self):
        """Drift makes the target win far more often than the stop, so the two
        resolving branches are exercised unevenly rather than symmetrically."""
        self._compare(Barriers(2.0, 1.0, 200), drift=0.0008)
        self._compare(Barriers(2.0, 1.0, 200), drift=-0.0008)

    def test_the_stop_still_wins_a_bar_that_spans_both_barriers(self):
        """The one assumption in the rule that OHLC cannot settle, and the one a
        vectorised rewrite is most likely to invert. `first_down <= first_up`."""
        close = np.array([100.0, 100.0, 100.0])
        high = np.array([100.0, 130.0, 100.0])
        low = np.array([100.0, 70.0, 100.0])
        volatility = np.array([0.1, 0.1, 0.1])
        barriers = Barriers(1.0, 1.0, 1)

        fast = _vectorised(high, low, close, volatility, barriers)
        slow = _reference(high, low, close, volatility, barriers)

        self.assertEqual(int(fast["label"][0]), -1)
        np.testing.assert_array_equal(fast["label"], slow["label"])

    def test_rows_with_no_usable_volatility_agree(self):
        """NaN and zero volatility rows are skipped and must stay skipped: the
        vectorised path masks them out of its blocks, and a mask that is off by
        one row would label a bar the reference never touched."""
        n = 500
        high, low, close = _series(n, seed=3)
        volatility = _volatility(n, seed=3)
        volatility[::7] = np.nan
        volatility[3::11] = 0.0
        barriers = Barriers(2.0, 1.0, 50)

        fast = _vectorised(high, low, close, volatility, barriers)
        slow = _reference(high, low, close, volatility, barriers)

        np.testing.assert_array_equal(fast["ends_at"], slow["ends_at"])
        np.testing.assert_array_equal(fast["label"], slow["label"])
        self.assertTrue((fast["ends_at"][np.isnan(volatility)] == -1).all())

    def test_a_series_shorter_than_the_horizon_agrees(self):
        """Every row is then a tail row and the block loop must do nothing."""
        n = 40
        high, low, close = _series(n, seed=5)
        volatility = _volatility(n, seed=5)
        barriers = Barriers(2.0, 1.0, 200)

        fast = _vectorised(high, low, close, volatility, barriers)
        slow = _reference(high, low, close, volatility, barriers)

        np.testing.assert_array_equal(fast["label"], slow["label"])
        np.testing.assert_array_equal(fast["touched"], slow["touched"])
        # A price barrier can still be hit inside the 39 bars that exist, so
        # `touched` is not uniformly False. What cannot happen is the HORIZON
        # resolving: no row has 200 bars of future, so every timed-out row here
        # must be marked unresolved rather than neutral.
        timed_out = fast["label"] == 0
        self.assertTrue(timed_out.any())
        self.assertFalse(fast["touched"][timed_out].any())

    def test_an_empty_series_is_not_an_error(self):
        empty = np.array([], dtype=float)
        outcome = _vectorised(empty, empty, empty, empty, Barriers())

        self.assertEqual(len(outcome["label"]), 0)

    def test_a_block_boundary_is_not_a_seam(self):
        """The block size is an implementation detail and must not be visible in
        the output. Sabotage: an off-by-one in the block range shows up here and
        almost nowhere else."""
        from quantlab_ml import labels

        n = 2_000
        high, low, close = _series(n, seed=11)
        volatility = _volatility(n, seed=11)
        barriers = Barriers(2.0, 1.0, 60)
        original = labels.BLOCK
        try:
            labels.BLOCK = 97  # a size that divides nothing evenly
            fast = _vectorised(high, low, close, volatility, barriers)
        finally:
            labels.BLOCK = original
        slow = _reference(high, low, close, volatility, barriers)

        np.testing.assert_array_equal(fast["ends_at"], slow["ends_at"])
        np.testing.assert_array_equal(fast["label"], slow["label"])

    def test_the_public_entry_point_is_the_fast_path(self):
        """A speedup nobody calls is not a speedup."""
        n = 800
        high, low, close = _series(n, seed=13)
        volatility = _volatility(n, seed=13)
        barriers = Barriers(2.0, 1.0, 50)

        public = triple_barrier(high, low, close, volatility, barriers)
        fast = _vectorised(high, low, close, volatility, barriers)

        np.testing.assert_array_equal(public["ends_at"], fast["ends_at"])


if __name__ == "__main__":
    unittest.main()
