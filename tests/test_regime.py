from datetime import datetime, timedelta, timezone
import unittest

from quantlab.models import Bar
from quantlab.regime import (
    MarketContext,
    MarketRegime,
    RegimeParameters,
    RegimeTimeline,
    build_market_timeline,
    market_context_from,
)


def _bars(closes: list[float], start: datetime | None = None, step_days: int = 1):
    start = start or datetime(2020, 1, 1, tzinfo=timezone.utc)
    bars, previous = [], closes[0]
    for i, close in enumerate(closes):
        bars.append(
            Bar(
                timestamp=start + timedelta(days=i * step_days),
                open=previous,
                high=max(previous, close) * 1.01,
                low=min(previous, close) * 0.99,
                close=close,
                volume=1_000.0,
            )
        )
        previous = close
    return bars


def _ramp(start: float, factor: float, count: int) -> list[float]:
    values, level = [], start
    for _ in range(count):
        values.append(level)
        level *= factor
    return values


class RegimeTimelineCausalityTest(unittest.TestCase):
    """The invariant everything else rests on: a regime label may never move
    because of a bar that had not happened when it was assigned.

    A cycle top is obvious in hindsight and invisible in real time, so this is
    the one place in the four-piece system where a leak would produce a
    spectacular and entirely fake result.
    """

    def _basket(self, cycles: int = 3, leg: int = 220) -> dict[str, list[Bar]]:
        """Repeated sharp reversals, not one smooth arc.

        The shape matters for what this class is testing. A single ramp up and
        down cannot detect a lookahead: a centred average and a trailing one
        disagree on the *value* everywhere but on the *label* nowhere, because
        both stay on the same side of a monotone trend. A peak is where a rule
        that can see forward starts calling the turn early, so the series has
        to contain several.
        """
        closes, level = [], 100.0
        for cycle in range(cycles):
            up = _ramp(level, 1.008, leg)
            down = _ramp(up[-1], 0.992, leg)
            closes.extend(up + down)
            level = down[-1] * (1.3 if cycle % 2 == 0 else 0.8)
        return {
            "AAAUSDT": _bars(closes),
            "BBBUSDT": _bars([c * 1.5 for c in closes]),
        }

    def test_labels_computed_on_a_prefix_match_the_full_history(self):
        """Truncating the future must not change a single past label.

        This is the sabotage detector for the whole module: any rule that
        peeks -- a centred average, a drawdown measured against a peak that has
        not formed, a smoothing pass over the full array -- makes the prefix
        and the full run disagree.

        Every cut point is checked, not one. A single cut only exercises the
        lookahead if the decision happens to flip right there; sweeping the
        series guarantees some cut lands beside a reversal, which is where a
        forward-peeking rule gives itself away.
        """
        basket = self._basket()
        full = build_market_timeline(basket)
        total = len(full.stamps)
        checked = 0
        for position in range(240, total, 17):
            cut = full.stamps[position]
            prefix = build_market_timeline(
                {
                    symbol: [bar for bar in bars if bar.timestamp <= cut]
                    for symbol, bars in basket.items()
                }
            )
            self.assertEqual(len(prefix.labels), position + 1)
            self.assertEqual(
                prefix.labels,
                full.labels[: position + 1],
                f"labels changed when history was truncated at bar {position}",
            )
            checked += 1
        self.assertGreater(checked, 20)

    def test_a_label_is_withheld_until_its_own_bar_has_closed(self):
        """A daily bar stamped D is not complete until D+1.

        A strategy acting anywhere inside day D must therefore read D-1's
        label. Handing out D's label at time D is a one-bar lookahead that
        would be invisible in every summary statistic.

        This has to be asserted **on a transition bar**. Sampling the middle of
        a stable regime proves nothing, because yesterday's label and today's
        are the same value there -- the first version of this test did exactly
        that, and removing the lag from `at()` left it passing.
        """
        timeline = build_market_timeline(self._basket())
        index = next(
            i
            for i in range(1, len(timeline.labels))
            if timeline.labels[i] is not timeline.labels[i - 1]
        )
        stamp = timeline.stamps[index]
        self.assertIsNot(timeline.labels[index], timeline.labels[index - 1])
        # Inside day D -- the new label exists but has not closed.
        self.assertIs(timeline.at(stamp), timeline.labels[index - 1])
        self.assertIs(
            timeline.at(stamp + timedelta(hours=23)), timeline.labels[index - 1]
        )
        # D has closed; the new label becomes readable and not one moment before.
        self.assertIs(timeline.at(stamp + timedelta(days=1)), timeline.labels[index])

    def test_a_moment_before_any_history_is_unknown_not_a_guess(self):
        timeline = build_market_timeline(self._basket())
        self.assertIs(
            timeline.at(timeline.stamps[0] - timedelta(days=5)), MarketRegime.UNKNOWN
        )

    def test_naive_timestamps_are_refused(self):
        timeline = build_market_timeline(self._basket())
        with self.assertRaises(ValueError):
            timeline.at(datetime(2021, 1, 1))


class RegimeClassificationTest(unittest.TestCase):
    def _timeline(self, closes: list[float], **overrides) -> RegimeTimeline:
        parameters = RegimeParameters(
            trend_period=50,
            slope_period=10,
            breadth_period=50,
            confirmation_bars=5,
            **overrides,
        )
        return build_market_timeline({"AAAUSDT": _bars(closes)}, parameters)

    def test_the_warmup_is_unknown_rather_than_sideways(self):
        """UNKNOWN is a state, not a null.

        Labelling the warmup SIDEWAYS would let the router trade from bar one
        on a regime nobody measured, which is exactly the claim the operator
        agreed the system should not make.
        """
        timeline = self._timeline(_ramp(100.0, 1.005, 200))
        self.assertTrue(
            all(label is MarketRegime.UNKNOWN for label in timeline.labels[:59])
        )
        self.assertIs(timeline.labels[-1], MarketRegime.BULL)

    def test_a_sustained_decline_is_bear(self):
        timeline = self._timeline(_ramp(100.0, 0.995, 250))
        self.assertIs(timeline.labels[-1], MarketRegime.BEAR)

    def test_a_recovery_from_a_deep_drawdown_is_not_labelled_bear(self):
        """The defect that killed the first version of this rule.

        Defining BEAR as a drawdown from the running all-time high keeps it
        true through the entire recovery: the prototype labelled the 2020 and
        2023 rebounds (+54% and +38% on the composite) bear markets, and would
        have run the bear branch through both. Trend and slope, not distance
        from a peak.

        The assertion has to sit on a **partial** recovery -- still far below
        the old high, already rising for weeks. A recovery that makes a new
        high is no test at all: the drawdown is zero there, so the broken rule
        and the correct one agree, and the first version of this test passed
        against the very defect it was written to catch.
        """
        decline = _ramp(100.0, 0.99, 150)
        closes = decline + _ramp(decline[-1], 1.012, 120)
        timeline = self._timeline(closes)
        peak = max(closes[:175])
        for position in range(174, 245):
            # Every bar in this window is 30-70% below the running peak, so a
            # drawdown-defined BEAR would fire on all of them, and the market
            # has been rising for at least 24 bars, so it is not a bear market.
            self.assertLessEqual(closes[position] / peak - 1, -0.30)
            self.assertIsNot(
                timeline.labels[position],
                MarketRegime.BEAR,
                f"bar {position} is {closes[position] / peak - 1:.1%} below the peak "
                "and rising, and was still called BEAR",
            )
        self.assertIn(MarketRegime.BULL, timeline.labels[174:245])

    def test_a_single_threshold_touch_does_not_flip_the_regime(self):
        """Hysteresis: a raw reading must persist `confirmation_bars` bars.

        Without it the label oscillates around every crossing and the router
        pays a full round trip in costs for a regime call that reverses on the
        next bar.
        """
        closes = _ramp(100.0, 1.005, 200)
        closes = closes + [closes[-1] * 0.80] + _ramp(closes[-1] * 1.005, 1.005, 40)
        timeline = self._timeline(closes)
        self.assertIs(timeline.labels[201], MarketRegime.BULL)

    def test_inverted_breadth_thresholds_are_refused_at_construction(self):
        with self.assertRaises(ValueError):
            RegimeParameters(bull_breadth=0.2, bear_breadth=0.6)

    def test_an_asset_without_enough_history_is_absent_from_breadth(self):
        """Missing history must not be counted as a bearish vote.

        A newly listed asset has no trailing average; scoring it as "not above
        its average" manufactures weak breadth out of an empty column, which
        biases the whole 2017-2018 stretch of the real basket toward BEAR.
        """
        long_history = _bars(_ramp(100.0, 1.005, 200))
        newcomer = _bars(
            _ramp(50.0, 1.005, 20), start=datetime(2020, 1, 1, tzinfo=timezone.utc)
        )
        parameters = RegimeParameters(
            trend_period=50, slope_period=10, breadth_period=50, confirmation_bars=5
        )
        timeline = build_market_timeline(
            {"OLDUSDT": long_history, "NEWUSDT": newcomer}, parameters
        )
        # The newcomer never reaches 50 bars, so breadth is decided by the one
        # asset that qualifies and stays at full strength.
        self.assertEqual(timeline.breadth[100], 1.0)
        self.assertIs(timeline.labels[-1], MarketRegime.BULL)


class RegimeReportingTest(unittest.TestCase):
    def test_episodes_partition_the_timeline_exactly(self):
        timeline = build_market_timeline(
            {"AAAUSDT": _bars(_ramp(100.0, 1.004, 400))},
            RegimeParameters(
                trend_period=50, slope_period=10, breadth_period=50, confirmation_bars=5
            ),
        )
        episodes = timeline.episodes()
        self.assertEqual(sum(e.bars for e in episodes), len(timeline.labels))
        self.assertEqual(episodes[0].start, timeline.stamps[0])
        self.assertEqual(episodes[-1].end, timeline.stamps[-1])
        for earlier, later in zip(episodes, episodes[1:]):
            self.assertIsNot(earlier.regime, later.regime)

    def test_separation_buckets_forward_returns_by_the_label_known_that_bar(self):
        timeline = build_market_timeline(
            {"AAAUSDT": _bars(_ramp(100.0, 1.004, 400))},
            RegimeParameters(
                trend_period=50, slope_period=10, breadth_period=50, confirmation_bars=5
            ),
        )
        separation = timeline.separation(20)
        self.assertIn("BULL", separation)
        self.assertGreater(separation["BULL"]["mean_forward_return"], 0.0)
        self.assertEqual(separation["BULL"]["positive_share"], 1.0)

    def test_a_context_cannot_be_built_from_an_empty_basket(self):
        with self.assertRaises(ValueError):
            market_context_from(lambda symbols, interval: {})

    def test_market_context_records_which_symbols_actually_loaded(self):
        """A silently reduced basket changes the regime and must be visible.

        If four of six reference assets fail to load, the composite is a
        different index and the labels are different labels; recording the
        loaded set is what lets a later reader tell the two runs apart.
        """
        context = market_context_from(
            lambda symbols, interval: {"AAAUSDT": _bars(_ramp(100.0, 1.004, 300))},
            RegimeParameters(
                trend_period=50, slope_period=10, breadth_period=50, confirmation_bars=5
            ),
        )
        self.assertIsInstance(context, MarketContext)
        self.assertEqual(context.notes["loaded_symbols"], ["AAAUSDT"])
        self.assertEqual(len(context.notes["requested_symbols"]), 6)


if __name__ == "__main__":
    unittest.main()
