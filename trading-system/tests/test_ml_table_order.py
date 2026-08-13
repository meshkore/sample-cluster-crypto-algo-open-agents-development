"""The observation table is on one clock, so that a fold is a slice of history.

Written after finding that it was not. `dataset.build` assembles the table one
symbol at a time, so it ran BNB 2017-2025, then BTC 2017-2025, then ETH -- time
jumped backwards at every symbol boundary. `splits.purged_walk_forward` slices by
POSITION, which on that table made a "fold" a slice of the SYMBOL LIST: the model
trained on BNB through 2025 and was tested on BTC from 2017, and the purge
compared row indices that had never been on a shared clock.

Nothing said so. The run reported six of six folds positive at +0.49% net per
trade over 578,008 trades, which is the shape of a real result, and the number
that should have raised an eyebrow -- a `mean_t_star` of -1.05 beside a positive
mean -- was blamed on a separate thinning bug and fixed without curing this.

The load-bearing test is `test_a_fold_trains_only_on_the_past`. Every other
assertion here is a property of the sort; that one is the property the walk-
forward exists to provide, and it was false.

Sabotage-verified: removing the `[order]` reindexing in `dataset.build` turns
three of these red, including the load-bearing one.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import numpy as np

from quantlab_backtester.models import Bar
from quantlab_ml import dataset as md
from quantlab_ml.labels import Barriers
from quantlab_ml.splits import purged_walk_forward

UTC = timezone.utc
STEP = timedelta(minutes=5)
BARRIERS = Barriers(target=2.0, stop=1.0, horizon=24)


def _bars(start: datetime, count: int, seed: int) -> list[Bar]:
    """A random walk on a 5-minute grid. Prices only have to move."""
    rng = np.random.default_rng(seed)
    price = 100.0
    out: list[Bar] = []
    for i in range(count):
        price *= float(np.exp(rng.normal(0.0, 0.004)))
        out.append(
            Bar(
                timestamp=start + i * STEP,
                open=price,
                high=price * 1.002,
                low=price * 0.998,
                close=price,
                volume=1_000.0 + i,
            )
        )
    return out


def _table(count: int = 1400):
    """Two symbols that START ON DIFFERENT DATES, which is the whole point.

    With a shared start the symbol-major bug is invisible in a monotonicity check
    -- each block covers the same span, so the boundary looks like a reset rather
    than a jump. AAA begins two days before BBB, exactly as SOL has no 2018.
    """
    origin = datetime(2020, 1, 1, tzinfo=UTC)
    bars = {
        "AAA": _bars(origin, count, seed=1),
        "BBB": _bars(origin + timedelta(days=2), count, seed=2),
    }
    return bars, md.build(bars, BARRIERS, volatility_span=48)


class TheTableIsOnOneClock(unittest.TestCase):
    def test_the_rows_are_sorted_by_timestamp(self):
        _, observations = _table()
        stamps = observations.timestamps
        self.assertTrue(
            all(stamps[i] <= stamps[i + 1] for i in range(len(stamps) - 1)),
            "the table must be one timeline, not one block per symbol",
        )

    def test_both_symbols_are_interleaved_rather_than_blocked(self):
        """A guard against passing the sort test by dropping a symbol."""
        _, observations = _table()
        symbols = observations.symbols
        changes = int((symbols[1:] != symbols[:-1]).sum())
        self.assertGreater(
            changes, 10, "a sorted two-symbol table must alternate, not block"
        )

    def test_a_fold_trains_only_on_the_past(self):
        """THE load-bearing test: what a walk-forward is supposed to mean.

        Before the sort this failed by a wide margin -- fold 0's training block
        was one symbol's entire history, including bars years after the test
        block it was scored on.
        """
        _, observations = _table()
        folds = purged_walk_forward(
            observations.ends_at, folds=3, embargo=10, minimum_train=400
        )
        self.assertTrue(folds)
        stamps = observations.timestamps
        for fold in folds:
            latest_train = max(stamps[i] for i in fold.train)
            earliest_test = min(stamps[i] for i in fold.test)
            self.assertLess(
                latest_train,
                earliest_test,
                f"fold {fold.index} trains on bars later than it tests on",
            )

    def test_a_label_resolves_on_a_later_bar_of_the_same_symbol(self):
        """`ends_at` is rebased twice by the sort, and either half can be wrong:
        a row could end up pointing at another symbol, or at its own past."""
        _, observations = _table()
        ends = observations.ends_at
        stamps, symbols = observations.timestamps, observations.symbols
        self.assertEqual(int((symbols[ends] != symbols).sum()), 0)
        self.assertEqual(int((ends < np.arange(len(ends))).sum()), 0)
        self.assertTrue(all(stamps[ends[i]] >= stamps[i] for i in range(len(ends))))

    def test_the_purge_actually_removes_something(self):
        """A purge that drops nothing would satisfy every test above and leave
        overlapping labels straddling the boundary."""
        _, observations = _table()
        folds = purged_walk_forward(
            observations.ends_at, folds=3, embargo=10, minimum_train=400
        )
        self.assertTrue(any(fold.purged > 0 for fold in folds))


class TheVolatilityIsAlignedRowByRow(unittest.TestCase):
    def test_every_row_gets_its_own_bar_volatility(self):
        bars, observations = _table()
        sigma = md.barrier_sigma(observations, bars, horizon=BARRIERS.horizon, span=48)
        self.assertEqual(len(sigma), len(observations.y))
        self.assertTrue(np.isfinite(sigma).all(), "no row may be left unpriced")
        self.assertGreater(float(np.nanmedian(sigma)), 0.0)

    def test_a_row_whose_bar_is_absent_is_left_unpriced_rather_than_guessed(self):
        """The old construction concatenated one array per symbol and could only
        be correct while the table was symbol-major. A silent misalignment prices
        every trade against another row's volatility, and nothing reads wrong."""
        bars, observations = _table()
        sigma = md.barrier_sigma(
            observations, {"AAA": bars["AAA"]}, horizon=BARRIERS.horizon, span=48
        )
        absent = observations.symbols == "BBB"
        self.assertTrue(np.isnan(sigma[absent]).all())
        self.assertTrue(np.isfinite(sigma[~absent]).all())

    def test_the_scaling_matches_the_barriers(self):
        """sqrt(horizon), the same factor `triple_barrier` placed them with. At
        five minutes over 864 bars a mismatch is a factor of 29 and the filter
        silently refuses every trade."""
        bars, observations = _table()
        one = md.barrier_sigma(observations, bars, horizon=1, span=48)
        many = md.barrier_sigma(observations, bars, horizon=100, span=48)
        np.testing.assert_allclose(many, one * 10.0, rtol=1e-9)


if __name__ == "__main__":
    unittest.main()
