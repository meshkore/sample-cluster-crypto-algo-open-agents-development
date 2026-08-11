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
    CycleDetector,
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
        # `minimum_phase=1` opts out of the middle level's duration floor.
        # These tests are about the classification mechanism, and a 60-bar
        # floor on a 20-bar tape would freeze the first label forever and
        # make every one of them pass for the wrong reason.
        base = dict(
            trend_period=5, slope_period=2, confirmation_bars=1, minimum_phase=1
        )
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
                minimum_phase=1,
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
            RegimeParameters(
                trend_period=5, slope_period=2, confirmation_bars=1, minimum_phase=1
            )
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


class TestWhatTheMarketIs(unittest.TestCase):
    """H-L086M: the detector read six survivors and called that the market.

    Scored against the broad market's own forward return, the six-name basket
    is not correctly ordered -- its SIDEWAYS bucket falls harder than its BEAR
    bucket -- while the whole listed universe is, and nearly doubles the bear
    branch's training signal in the fold that falls.

    Breadth is the sharper reason and these tests pin it: on six names breadth
    can only report 0, 1/6, 2/6 ... against thresholds at 0.35 and 0.50, so one
    asset changing its mind was the difference between a bull market and a bear
    one.
    """

    def _observe(self, detector, closes, above, weights=None):
        return detector.observe(START, closes, above, weights)

    def test_universe_scope_counts_assets_outside_the_basket(self):
        """Sabotage: keep the `symbol in self.reference` filter. The seventh
        asset vanishes, breadth reads 1.0 instead of 6/7, and the detector is
        back to describing a sample."""
        detector = MarketDetector(RegimeParameters(market_scope="universe"))
        closes = {"BTCUSDT": 100.0, **{f"ALT{i}": 10.0 for i in range(6)}}
        above = {"BTCUSDT": True, **{f"ALT{i}": i < 5 for i in range(6)}}
        self._observe(detector, closes, above)
        self.assertAlmostEqual(detector.breadth[-1], 6 / 7, places=6)
        self.assertEqual(len(detector.seen_symbols), 7)

    def test_basket_scope_still_ignores_everything_else(self):
        """The old behaviour is kept, not deleted, so the two can be compared on
        the same run rather than across two branches of the repository."""
        detector = MarketDetector(RegimeParameters(market_scope="basket"))
        closes = {"BTCUSDT": 100.0, **{f"ALT{i}": 10.0 for i in range(6)}}
        above = {"BTCUSDT": True, **{f"ALT{i}": False for i in range(6)}}
        self._observe(detector, closes, above)
        self.assertEqual(detector.breadth[-1], 1.0)
        self.assertEqual(detector.seen_symbols, {"BTCUSDT"})

    def test_turnover_weighting_lets_the_big_asset_carry_the_index(self):
        """Sabotage: ignore `weights`. Both variants then move identically and
        the whole capitalisation-proxy question becomes untestable."""
        closes_a = {"BIG": 100.0, "SMALL": 100.0}
        closes_b = {"BIG": 110.0, "SMALL": 90.0}  # +10% and -10%
        weights = {"BIG": 1_000_000_000.0, "SMALL": 1_000.0}
        above = {"BIG": True, "SMALL": True}

        equal = MarketDetector(RegimeParameters(market_scope="universe"))
        heavy = MarketDetector(
            RegimeParameters(market_scope="universe", weighting="turnover")
        )
        for detector in (equal, heavy):
            detector.observe(START, closes_a, above, weights)
            detector.observe(START + timedelta(days=1), closes_b, above, weights)

        # Equal weight nets the two moves out; turnover weight follows BIG up.
        self.assertLess(equal.index[-1], 100.5)
        self.assertGreater(heavy.index[-1], 109.0)

    def test_a_weightless_asset_cannot_silently_drop_out(self):
        """An asset with no turnover column under turnover weighting has no
        weight, and counting it as zero would delete it from the market. It is
        still counted in BREADTH, where it needs no weight at all."""
        detector = MarketDetector(
            RegimeParameters(market_scope="universe", weighting="turnover")
        )
        above = {"A": True, "B": False}
        detector.observe(START, {"A": 100.0, "B": 100.0}, above, {"A": 5.0})
        detector.observe(
            START + timedelta(days=1), {"A": 110.0, "B": 50.0}, above, {"A": 5.0}
        )
        self.assertAlmostEqual(detector.breadth[-1], 0.5, places=6)
        # B has no weight, so only A's +10% moved the index.
        self.assertGreater(detector.index[-1], 109.0)

    def test_an_unknown_scope_or_weighting_is_refused_at_construction(self):
        """A typo that silently falls through to a default would make a recorded
        run describe a market it did not measure."""
        with self.assertRaises(ValueError):
            RegimeParameters(market_scope="everything")
        with self.assertRaises(ValueError):
            RegimeParameters(weighting="marketcap")


class TestTheCycleDoesNotChurn(unittest.TestCase):
    """H-L087C: the global trend, and the reason it needed its own mechanism.

    The regime detector produced 74 phases in 8.4 years -- median 28 days, 89%
    under three months, the longest 136 days. Every published dating of the same
    period finds six to ten. The operator's objection is exactly right: a bear
    market does not last a fortnight, and a detector that says it does will hand
    the trading module six different opinions in a quarter.

    `CycleDetector` dates turning points instead of reading price against an
    average: a swing threshold from the running extreme, and a minimum phase
    length that censors anything shorter. At the shipped defaults it produces
    six phases over the same tape, with 24-month bears matching the halving
    cycles.
    """

    def _ramp(self, detector, start, growth, bars):
        level = start
        for _ in range(bars):
            level *= growth
            detector.observe(level)
        return level

    def test_a_short_bounce_does_not_end_a_bear(self):
        """The operator's complaint, pinned in both directions.

        Sabotage: drop the `minimum_phase` test in `observe`. The bounce then
        renames the market on the bar it clears the bull swing, which is how a
        fortnight of green appeared inside a two-year fall.
        """
        floor = 60
        detector = CycleDetector(
            smoothing=5, bear_swing=0.30, bull_swing=0.50, minimum_phase=floor
        )
        level = self._ramp(detector, 100.0, 1.02, 80)
        while detector.regime is not MarketRegime.BEAR:
            level *= 0.97
            detector.observe(level)
        # BEAR has just been declared, so the phase clock is at zero. Bounce
        # violently for less than the floor: far past the bull swing, and not
        # long enough to be a phase.
        for _ in range(floor - 2):
            level *= 1.06
            detector.observe(level)
        self.assertIs(
            detector.regime,
            MarketRegime.BEAR,
            "a bounce inside the floor ended the bear",
        )
        # OPEN-GATE CONTROL. A rule that can never leave BEAR would pass the
        # assertion above and be useless; past the floor it must give way.
        for _ in range(4):
            level *= 1.06
            detector.observe(level)
        self.assertIs(
            detector.regime, MarketRegime.BULL, "the floor never let the phase end"
        )

    def test_a_sustained_recovery_does_end_it(self):
        """The counterpart, and the reason this is not a drawdown rule.

        `regime.py` records that measuring the fall from the all-time high was
        tried and rejected because nothing ever ended a bear. A rule that can
        never leave BEAR would pass the test above and be useless."""
        detector = CycleDetector(
            smoothing=5, bear_swing=0.30, bull_swing=0.50, minimum_phase=20
        )
        level = self._ramp(detector, 100.0, 1.02, 40)
        level = self._ramp(detector, level, 0.97, 60)
        self.assertIs(detector.regime, MarketRegime.BEAR)
        self._ramp(detector, level, 1.03, 60)
        self.assertIs(detector.regime, MarketRegime.BULL)

    def test_the_extremes_reset_with_the_phase(self):
        """A bear that ends must forget the old high, or the next bull is
        measured against a peak two years stale and can never start."""
        detector = CycleDetector(
            smoothing=1, bear_swing=0.30, bull_swing=0.50, minimum_phase=1
        )
        self._ramp(detector, 100.0, 1.02, 50)
        top = detector._peak
        self._ramp(detector, detector.level, 0.95, 20)
        self.assertIs(detector.regime, MarketRegime.BEAR)
        self.assertLess(detector._peak, top, "the peak survived the phase change")

    def test_it_reads_no_bar_before_it_closes(self):
        """The textbook dating algorithm is retrospective and this one may not
        be. Feeding a prefix and then the whole series must give identical
        labels over the prefix."""
        level, whole = 100.0, []
        for i in range(80):
            level *= 1.02 if i < 40 else 0.96
            whole.append(level)
        early = CycleDetector(smoothing=5, minimum_phase=10)
        prefix = [early.observe(v) for v in whole[:55]]
        late = CycleDetector(smoothing=5, minimum_phase=10)
        full = [late.observe(v) for v in whole]
        self.assertEqual(prefix, full[:55])

    def test_a_nonsense_configuration_is_refused(self):
        with self.assertRaises(ValueError):
            CycleDetector(smoothing=0)
        with self.assertRaises(ValueError):
            CycleDetector(minimum_phase=0)
        with self.assertRaises(ValueError):
            CycleDetector(bear_swing=0.0)


class TestTheMiddleLevelHasAFloor(unittest.TestCase):
    def test_a_phase_shorter_than_the_floor_cannot_be_replaced(self):
        """`confirmation_bars` asks a NEW reading to persist; `minimum_phase`
        asks the CURRENT phase to have lasted. Only the second bounds how short
        an episode can be.

        Sabotage: drop `long_enough` from `_apply_hysteresis`. The label then
        flips as soon as the confirmation streak clears, which is how 74 phases
        appeared in eight years."""
        parameters = RegimeParameters(
            trend_period=5, slope_period=2, confirmation_bars=1, minimum_phase=40
        )
        detector = MarketDetector(parameters, reference=("BTCUSDT",))
        labels = _feed(detector, [100.0 * 1.05**i for i in range(15)])
        first = detector.regime
        self.assertIsNot(first, MarketRegime.UNKNOWN)
        # A hard reversal, well past every threshold, inside the floor.
        labels += _feed(
            detector,
            [detector.index[-1] * 0.9**i for i in range(1, 12)],
            above=[False] * 11,
        )
        self.assertIs(detector.regime, first, "the floor did not hold the phase")
