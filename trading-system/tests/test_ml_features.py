"""Features that cannot see the future and cannot see which asset they are on.

Both failures produce a model that scores well in training and is worthless
afterwards, and neither shows up in an accuracy table. Every test names the
mistake it exists to catch.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import numpy as np

from quantlab_ml.features import (
    _trailing_mean,
    calendar,
    cross_sectional_rank,
    scale_free,
    session_shape,
)


def _stamps(n: int, start_hour: int = 0) -> list[datetime]:
    base = datetime(2021, 3, 1, start_hour, tzinfo=timezone.utc)
    return [base + timedelta(minutes=5 * i) for i in range(n)]


class ScaleFreeTest(unittest.TestCase):
    def test_the_same_market_on_two_price_scales_gives_identical_features(self):
        """The level leak, stated as an equality. A model fed raw `sma_200`
        learns which asset it is looking at; these two series are the same market
        priced in different units and must be indistinguishable."""
        n = 400
        rng = np.random.default_rng(7)
        steps = rng.normal(0, 0.002, n)
        cheap = 60.0 * np.exp(np.cumsum(steps))
        dear = 60_000.0 * np.exp(np.cumsum(steps))
        sigma = np.full(n, 0.002)

        a = scale_free(
            {"sma_20": cheap * 0.99, "volume": np.full(n, 10.0)}, cheap, sigma
        )
        b = scale_free(
            {"sma_20": dear * 0.99, "volume": np.full(n, 10_000.0)}, dear, sigma
        )
        for key in a:
            np.testing.assert_allclose(
                a[key][50:],
                b[key][50:],
                rtol=1e-9,
                atol=1e-9,
                err_msg=f"{key} depends on the price level",
            )

    def test_an_unclassified_column_is_dropped_rather_than_passed_through(self):
        n = 50
        out = scale_free(
            {"some_new_indicator": np.arange(n, dtype=float)},
            np.full(n, 100.0),
            np.full(n, 0.01),
        )
        self.assertNotIn("some_new_indicator", out)
        self.assertEqual(out, {})

    def test_features_never_read_a_bar_after_the_one_they_describe(self):
        """Sabotage: a centred rolling mean, or normalising by the full-series
        mean, passes every other test here and leaks the future everywhere."""
        n = 600
        rng = np.random.default_rng(3)
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
        volume = rng.lognormal(0, 1, n)
        sigma = np.full(n, 0.002)
        columns = {
            "sma_20": close * 0.995,
            "volume": volume,
            "rsi_14": rng.uniform(0, 100, n),
        }

        full = scale_free(columns, close, sigma)
        cut = 400
        truncated = scale_free(
            {k: v[:cut] for k, v in columns.items()}, close[:cut], sigma[:cut]
        )
        for key in full:
            np.testing.assert_allclose(
                full[key][:cut],
                truncated[key],
                rtol=1e-9,
                equal_nan=True,
                err_msg=f"{key} changed when later bars were removed",
            )

    def test_the_trailing_mean_is_causal(self):
        values = np.arange(10, dtype=float)
        out = _trailing_mean(values, 3)
        self.assertAlmostEqual(out[0], 0.0)
        self.assertAlmostEqual(out[2], 1.0)
        self.assertAlmostEqual(out[9], 8.0)


class CalendarTest(unittest.TestCase):
    def test_midnight_is_adjacent_to_the_hour_before_it(self):
        """An integer hour makes 23:00 maximally distant from 00:00 and a tree
        then needs two splits to express one fact about the night."""
        out = calendar(
            [datetime(2021, 1, 1, h, tzinfo=timezone.utc) for h in (23, 0, 12)]
        )
        late = np.array([out["hour_sin"][0], out["hour_cos"][0]])
        midnight = np.array([out["hour_sin"][1], out["hour_cos"][1]])
        noon = np.array([out["hour_sin"][2], out["hour_cos"][2]])
        self.assertLess(
            np.linalg.norm(late - midnight),
            np.linalg.norm(late - noon),
            "23:00 should sit closer to midnight than to noon",
        )


class SessionShapeTest(unittest.TestCase):
    def test_the_day_return_resets_at_the_utc_boundary(self):
        n = 576  # two whole days at five minutes
        close = np.full(n, 100.0)
        close[288:] = 110.0  # a jump exactly on the day boundary
        stamps = _stamps(n)
        out = session_shape(close, stamps, np.full(n, 0.01))
        self.assertAlmostEqual(out["day_return_sigma"][287], 0.0, places=9)
        self.assertAlmostEqual(
            out["day_return_sigma"][288],
            0.0,
            places=9,
            msg="the first bar of a day must open its own session",
        )

    def test_the_day_return_is_measured_in_volatility_units(self):
        """The sealed window's lesson: the same 3% move is a large event in a
        quiet regime and an ordinary one in a violent regime."""
        n = 100
        close = np.full(n, 100.0)
        close[50:] = 103.0
        stamps = _stamps(n)
        quiet = session_shape(close, stamps, np.full(n, 0.005))
        violent = session_shape(close, stamps, np.full(n, 0.05))
        self.assertGreater(
            quiet["day_return_sigma"][60], violent["day_return_sigma"][60]
        )

    def test_session_shape_never_reads_a_later_bar(self):
        n = 500
        rng = np.random.default_rng(11)
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
        stamps = _stamps(n)
        sigma = np.full(n, 0.002)
        full = session_shape(close, stamps, sigma)
        cut = 300
        truncated = session_shape(close[:cut], stamps[:cut], sigma[:cut])
        for key in full:
            np.testing.assert_allclose(
                full[key][:cut],
                truncated[key],
                rtol=1e-9,
                equal_nan=True,
                err_msg=f"{key} used a bar from the future",
            )


class CrossSectionTest(unittest.TestCase):
    def test_the_rank_separates_moving_alone_from_moving_with_everything(self):
        """The whole reason this family exists: per symbol the number is
        identical, and the two situations are different events."""
        alone = cross_sectional_rank(
            {"A": np.array([0.02]), "B": np.array([0.0]), "C": np.array([0.0])}
        )
        together = cross_sectional_rank(
            {"A": np.array([0.02]), "B": np.array([0.02]), "C": np.array([0.02])}
        )
        self.assertEqual(alone["A"][0], 1.0)
        self.assertLess(together["A"][0], 1.0)

    def test_one_violent_asset_does_not_move_everyone_elses_feature(self):
        """Why ranks rather than z-scores."""
        calm = cross_sectional_rank(
            {"A": np.array([0.01]), "B": np.array([0.02]), "C": np.array([0.03])}
        )
        wild = cross_sectional_rank(
            {"A": np.array([0.01]), "B": np.array([0.02]), "C": np.array([9.99])}
        )
        self.assertEqual(calm["A"][0], wild["A"][0])
        self.assertEqual(calm["B"][0], wild["B"][0])

    def test_a_bar_where_almost_nothing_is_priced_yields_no_rank(self):
        out = cross_sectional_rank({"A": np.array([0.01]), "B": np.array([np.nan])})
        self.assertTrue(np.isnan(out["A"][0]))


if __name__ == "__main__":
    unittest.main()
