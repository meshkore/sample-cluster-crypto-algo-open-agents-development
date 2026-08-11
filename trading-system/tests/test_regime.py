"""The major-trend detector: composite, breadth, hysteresis, and causality.

The detector is the one piece whose output every other piece depends on, and it
is the easiest place in this laboratory to leak the future -- a top is obvious
in hindsight and invisible in real time. `test_a_label_never_changes_when_later_bars_arrive`
is the one that matters: it feeds a prefix, then the whole series, and demands
the prefix's labels come back identical.

All sabotage-verified; each test names the bug it was checked against.
"""

from datetime import datetime, timedelta, timezone
import unittest

from quantlab_trading.regime import (
    AssetDetector,
    MarketDetector,
    MarketRegime,
    RegimeParameters,
)

UTC = timezone.utc
START = datetime(2020, 1, 1, tzinfo=UTC)


def _feed(detector, series, above=None, symbol="BTCUSDT"):
    """Push a close series through the detector, one bar at a time."""
    labels = []
    for i, close in enumerate(series):
        flag = above[i] if above is not None else True
        labels.append(
            detector.observe(START + timedelta(days=i), {symbol: close}, {symbol: flag})
        )
    return labels


class TestComposite(unittest.TestCase):
    def test_a_late_listing_does_not_rebase_the_index(self):
        """Chaining returns, not averaging prices.

        Sabotage: averaging the closes instead of chaining their returns. The
        index then jumps the day the second asset appears -- a level change with
        no market event behind it -- and the test fails on the equality below.
        """
        detector = MarketDetector(reference=("BTCUSDT", "ETHUSDT"))
        detector.observe(START, {"BTCUSDT": 100.0}, {})
        detector.observe(START + timedelta(days=1), {"BTCUSDT": 110.0}, {})
        before = detector.index[-1]
        # ETH lists at a completely different price level and does not move.
        detector.observe(
            START + timedelta(days=2), {"BTCUSDT": 110.0, "ETHUSDT": 4000.0}, {}
        )
        self.assertAlmostEqual(detector.index[-1], before, places=9)
        # From here it contributes its returns like everyone else.
        detector.observe(
            START + timedelta(days=3), {"BTCUSDT": 110.0, "ETHUSDT": 4400.0}, {}
        )
        self.assertGreater(detector.index[-1], before)

    def test_breadth_ignores_assets_whose_average_has_not_filled(self):
        """A missing column is absent, not a bearish vote.

        Sabotage: `above_trend.get(symbol, False)`. The second asset then counts
        as "not above its average" from its first bar and breadth halves, which
        is how 2017-2018 was manufactured into a bear market out of missing data.
        """
        detector = MarketDetector(reference=("BTCUSDT", "ETHUSDT"))
        detector.observe(
            START,
            {"BTCUSDT": 100.0, "ETHUSDT": 4000.0},
            {"BTCUSDT": True},  # ETH has no sma_200 yet
        )
        self.assertEqual(detector.breadth[-1], 1.0)

    def test_depth_measures_the_composite_below_its_running_high(self):
        detector = MarketDetector()
        _feed(detector, [100.0, 200.0, 100.0])
        self.assertAlmostEqual(detector.depth, 0.5, places=6)
        _feed(detector, [200.0])  # back to the high
        self.assertAlmostEqual(detector.depth, 0.0, places=6)


class TestClassification(unittest.TestCase):
    def _parameters(self, **overrides):
        base = dict(trend_period=5, slope_period=2, confirmation_bars=1)
        base.update(overrides)
        return RegimeParameters(**base)

    def test_no_label_is_emitted_before_the_windows_have_filled(self):
        """UNKNOWN is a state, not a missing value."""
        detector = MarketDetector(self._parameters(require_slope=True))
        labels = _feed(detector, [100.0 + i for i in range(6)])
        self.assertTrue(all(label is MarketRegime.UNKNOWN for label in labels[:6]))
        self.assertEqual(detector.parameters.warmup_bars, 7)

    def test_the_slope_window_is_only_charged_for_when_it_is_required(self):
        """Warmup is dead time: the router holds flat through it.

        Charging `slope_period` bars for a statistic no branch consults would
        keep the system out of the market for longer than the mechanism needs,
        which is not caution -- it is a warmup applied to nothing.
        """
        self.assertEqual(self._parameters().warmup_bars, 5)
        self.assertEqual(self._parameters(require_slope=True).warmup_bars, 7)
        detector = MarketDetector(self._parameters())
        labels = _feed(detector, [100.0 + i for i in range(6)])
        self.assertTrue(all(label is MarketRegime.UNKNOWN for label in labels[:4]))
        self.assertIsNot(labels[4], MarketRegime.UNKNOWN)

    def test_a_rising_broad_market_is_a_bull(self):
        detector = MarketDetector(self._parameters())
        _feed(detector, [100.0 * 1.05**i for i in range(20)])
        self.assertIs(detector.regime, MarketRegime.BULL)

    def test_a_rising_market_with_narrow_breadth_is_not_a_bull(self):
        """Breadth is a required condition, not a tiebreak.

        Sabotage: dropping the `share >= bull_breadth` clause. The same series
        then labels BULL and this assertion fails.
        """
        detector = MarketDetector(self._parameters())
        series = [100.0 * 1.05**i for i in range(20)]
        _feed(detector, series, above=[False] * len(series))
        self.assertIsNot(detector.regime, MarketRegime.BULL)

    def test_a_falling_narrow_market_is_a_bear(self):
        detector = MarketDetector(self._parameters())
        series = [100.0 * 0.95**i for i in range(20)]
        _feed(detector, series, above=[False] * len(series))
        self.assertIs(detector.regime, MarketRegime.BEAR)

    def test_a_single_threshold_touch_does_not_flip_the_regime(self):
        """Hysteresis, and the control that proves the test can fail.

        Sabotage: setting `self.regime = raw` unconditionally. The one-bar dip
        flips the label to SIDEWAYS and the first assertion fails. The second
        half is the control: with enough persistence the state MUST move, or a
        detector frozen at its first label would pass the first assertion too.
        """
        detector = MarketDetector(self._parameters(confirmation_bars=5))
        series = [100.0 * 1.05**i for i in range(20)]
        _feed(detector, series)
        self.assertIs(detector.regime, MarketRegime.BULL)

        # One bar of narrow breadth: raw reading is SIDEWAYS, state must hold.
        _feed(detector, [series[-1] * 1.05], above=[False])
        self.assertIs(detector.regime, MarketRegime.BULL)

        # Five consecutive: the state moves.
        level = series[-1]
        for _ in range(6):
            level *= 1.05
            _feed(detector, [level], above=[False])
        self.assertIs(detector.regime, MarketRegime.SIDEWAYS)

    def test_episode_age_counts_bars_inside_the_current_label(self):
        detector = MarketDetector(self._parameters())
        _feed(detector, [100.0 * 1.05**i for i in range(20)])
        self.assertIs(detector.regime, MarketRegime.BULL)
        age = detector.episode_age
        _feed(detector, [detector.index[-1] * 1.05])
        self.assertEqual(detector.episode_age, age + 1)


class TestTheSlopeTestIsWhatMadeItLate(unittest.TestCase):
    """H-L081D: requiring the trend average's slope to have turned is the term
    that made BEAR arrive after the bottom.

    Measured on the reference basket 2017-2025, the incumbent detector named
    its three falls 56%, 77% and 104% of the way from peak to trough, and its
    BEAR label's forward 20-bar composite return was POSITIVE (+1.27%) -- it
    selected recoveries, not falls. Dropping this one term took the median lag
    to 8% and the forward return to -0.31%.

    These tests do not re-measure that. They lock down the mechanism the
    measurement blamed, on a series small enough to reason about: a long rise
    followed by a sharp fall, which is the shape the detector kept missing.
    """

    def _series(self):
        # Twenty bars up, then a fast fall. The trailing average is still well
        # above where it was `slope_period` bars ago for a while after price
        # has broken below it -- which is precisely the gap being tested.
        return [100.0 * 1.03**i for i in range(20)] + [
            100.0 * 1.03**19 * 0.93**i for i in range(1, 15)
        ]

    def _first_bear(self, require_slope):
        detector = MarketDetector(
            RegimeParameters(
                trend_period=5,
                slope_period=4,
                confirmation_bars=1,
                require_slope=require_slope,
            )
        )
        labels = _feed(detector, self._series(), above=[False] * 34)
        return next(
            (i for i, label in enumerate(labels) if label is MarketRegime.BEAR), None
        )

    def test_both_settings_eventually_name_the_fall(self):
        """Neither is broken outright -- the difference is WHEN, which is the
        whole finding. A test that only showed one of them calling BEAR would
        be consistent with the slope test simply being disabled."""
        self.assertIsNotNone(self._first_bear(True))
        self.assertIsNotNone(self._first_bear(False))

    def test_requiring_the_slope_delays_the_label(self):
        """Sabotage: make `_classify` ignore `require_slope`. Both branches
        then return the same bar and this is the only test that fails."""
        self.assertLess(self._first_bear(False), self._first_bear(True))

    def test_breadth_is_never_optional(self):
        """Dropping the slope test must not leave price-vs-average alone in
        charge. One deep reference asset would otherwise carry the label for
        the whole market -- the per-asset filter H-REGIME-001 already refuted."""
        detector = MarketDetector(
            RegimeParameters(trend_period=5, slope_period=2, confirmation_bars=1)
        )
        # Falling hard, but every reference asset is above its own average.
        labels = _feed(detector, [100.0 * 0.9**i for i in range(15)], above=[True] * 15)
        self.assertNotIn(MarketRegime.BEAR, labels)


class TestCausality(unittest.TestCase):
    def test_a_label_never_changes_when_later_bars_arrive(self):
        """Prefix equality. The whole point of an incremental detector.

        Sabotage: any rule that reads ahead -- for instance classifying against
        `max(self.index)` computed over the full array at the end -- breaks this
        immediately, because the maximum of a prefix is not the maximum of the
        series.
        """
        parameters = RegimeParameters(
            trend_period=5, slope_period=2, confirmation_bars=2
        )
        series = [100.0]
        for i in range(1, 60):
            series.append(series[-1] * (1.05 if i % 11 < 6 else 0.94))

        whole = _feed(MarketDetector(parameters), series)
        for cut in (20, 35, 50):
            prefix = _feed(MarketDetector(parameters), series[:cut])
            self.assertEqual(prefix, whole[:cut], f"labels changed at prefix {cut}")

    def test_separation_reads_forward_and_is_therefore_a_post_run_measure(self):
        parameters = RegimeParameters(
            trend_period=5, slope_period=2, confirmation_bars=1
        )
        detector = MarketDetector(parameters)
        _feed(detector, [100.0 * 1.05**i for i in range(30)])
        report = detector.separation(horizon=3)
        self.assertIn("BULL", report)
        self.assertGreater(report["BULL"]["mean_forward_return"], 0.0)
        self.assertEqual(report["BULL"]["positive_share"], 1.0)


class TestAssetDetector(unittest.TestCase):
    def test_it_waits_for_the_slope_window_before_labelling(self):
        detector = AssetDetector(slope_period=3, confirmation_bars=1)
        for i in range(3):
            self.assertIs(
                detector.observe(100.0 + i, {"sma_200": 90.0 + i}),
                MarketRegime.UNKNOWN,
            )
        self.assertIs(detector.observe(104.0, {"sma_200": 94.0}), MarketRegime.BULL)

    def test_a_missing_column_holds_the_previous_label(self):
        """Sabotage: treating `None` as 0.0. Price is then always above its
        average and every asset is a permanent BULL from bar one."""
        detector = AssetDetector(slope_period=2, confirmation_bars=1)
        for i in range(4):
            detector.observe(100.0 + i, {"sma_200": 90.0 + i})
        self.assertIs(detector.regime, MarketRegime.BULL)
        self.assertIs(detector.observe(1.0, {}), MarketRegime.BULL)

    def test_hysteresis_holds_the_label_through_one_dissenting_bar(self):
        detector = AssetDetector(slope_period=2, confirmation_bars=3)
        for i in range(6):
            detector.observe(100.0 + i, {"sma_200": 90.0 + i})
        self.assertIs(detector.regime, MarketRegime.BULL)
        detector.observe(50.0, {"sma_200": 96.0})
        self.assertIs(detector.regime, MarketRegime.BULL)


if __name__ == "__main__":
    unittest.main()
