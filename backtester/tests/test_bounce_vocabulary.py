"""The columns a bounce trade needs, checked against arithmetic done by hand.

The catalogue could already say "price is 30% below its average". It could not
say "and it closed at the top of its range", because the rule language has no
division and refuses to compare a bar's high against its own low. So every
candle-anatomy technique -- hammer, engulfing, close-near-high -- was outside
what the loop could invent, for seventy-three iterations.

These columns are that missing half. Each one is normalised to the bar's own
range or to its own average, so a $0.0001 coin and a $60,000 one are directly
comparable, and each is a CONTINUOUS quantity rather than a pattern flag: a
threshold the search can move beats a definition it cannot.

Causality is not tested here -- `test_the_catalogue_is_causal_under_truncation`
already walks every column at three cut points, and these are in it.
"""

from datetime import datetime, timedelta, timezone
import unittest

from quantlab_backtester.indicators import IndicatorSpec, panel_for
from quantlab_backtester.models import Bar

UTC = timezone.utc
START = datetime(2020, 1, 1, tzinfo=UTC)


def _bar(day, o, h, low, c, volume=1_000.0):
    return Bar(
        timestamp=START + timedelta(days=day),
        open=o,
        high=h,
        low=low,
        close=c,
        volume=volume,
    )


def _panel(bars):
    return panel_for(bars, IndicatorSpec())


def _flat(count, price=100.0, volume=1_000.0):
    """A dull series to pad with, so the bar under test is the only event."""
    return [_bar(i, price, price, price, price, volume) for i in range(count)]


class TestBarAnatomy(unittest.TestCase):
    """Where the bar closed inside its own range, and what shape it was."""

    def test_a_hammer_closes_at_the_top_of_its_range(self):
        """The bar you would actually bounce from: swept low, closed high.

        Sabotage: compute (close - open) / span instead. The hammer below has
        open == close and this returns 0, which is a doji -- the opposite
        reading of the same bar.
        """
        bars = _flat(30) + [_bar(30, o=100.0, h=101.0, low=91.0, c=100.5)]
        row = _panel(bars).at(30)
        # span 10, close 9.5 above the low
        self.assertAlmostEqual(row["internal_bar_strength"], 0.95, places=9)
        self.assertAlmostEqual(row["lower_wick_fraction"], 0.90, places=9)
        self.assertAlmostEqual(row["upper_wick_fraction"], 0.05, places=9)
        self.assertAlmostEqual(row["body_fraction"], 0.05, places=9)

    def test_a_knife_still_falling_closes_at_the_bottom(self):
        """The bar you must NOT buy, and the reason this column exists: it is
        identical to the hammer above in every column the catalogue had before
        -- same range, same low, same drop."""
        bars = _flat(30) + [_bar(30, o=100.0, h=101.0, low=91.0, c=91.2)]
        row = _panel(bars).at(30)
        self.assertAlmostEqual(row["internal_bar_strength"], 0.02, places=9)
        self.assertGreater(row["body_fraction"], 0.8)

    def test_the_four_fractions_account_for_the_whole_bar(self):
        bars = _flat(30) + [_bar(30, o=97.0, h=104.0, low=94.0, c=101.0)]
        row = _panel(bars).at(30)
        total = (
            row["body_fraction"]
            + row["upper_wick_fraction"]
            + row["lower_wick_fraction"]
        )
        self.assertAlmostEqual(total, 1.0, places=9)

    def test_a_bar_that_did_not_move_has_no_anatomy(self):
        """NAN, not 0.5. A rule reading it must stand aside rather than be
        handed the midpoint as though it were a measurement."""
        row = _panel(_flat(31)).at(30)
        self.assertIsNone(row["internal_bar_strength"])
        self.assertIsNone(row["body_fraction"])


class TestTheEventColumns(unittest.TestCase):
    def test_volume_ratio_is_this_bar_against_its_own_average(self):
        """Bounded from BOTH sides, which `volume > volume_sma_20 * 3` never
        was. 'Between two and four times normal' is what separates a climax
        from a listing pump."""
        bars = _flat(30, volume=1_000.0) + [
            _bar(30, 100.0, 101.0, 99.0, 100.0, volume=3_500.0)
        ]
        # The average is trailing and INCLUDES this bar, like every other
        # rolling column here: (19 x 1000 + 3500) / 20 = 1125. So a bar that is
        # 3.5x the quiet level reads as 3.11x, and a rule wanting "three times
        # normal" is asking for rather more than it sounds. Written down
        # because the alternative -- an average that excludes the current bar --
        # would be a different column with the same name.
        self.assertAlmostEqual(
            _panel(bars).at(30)["volume_ratio_20"], 3_500.0 / 1_125.0, places=6
        )

    def test_range_vs_atr_finds_the_wide_bar(self):
        """Capitulation arrives on a range several times normal, and `natr` is
        the average itself -- it cannot say 'this bar against it'."""
        quiet = [_bar(i, 100.0, 101.0, 99.0, 100.0) for i in range(40)]
        wide = quiet + [_bar(40, 100.0, 110.0, 90.0, 92.0)]
        row = _panel(wide).at(40)
        self.assertGreater(row["range_vs_atr"], 5.0)
        self.assertLess(_panel(quiet).at(39)["range_vs_atr"], 1.5)

    def test_down_streak_counts_consecutive_lower_closes(self):
        """Two down closes is what drives Connors' RSI(2) to its floor, and a
        count is the one thing a stateless comparison language cannot derive."""
        prices = [100.0, 99.0, 98.0, 97.0, 98.5, 97.5]
        bars = [_bar(i, p, p + 1, p - 1, p) for i, p in enumerate(prices)]
        panel = _panel(bars)
        self.assertEqual(panel.at(0)["down_streak"], 0.0)
        self.assertEqual(panel.at(3)["down_streak"], 3.0)
        # one up close resets it, and starts the other one
        self.assertEqual(panel.at(4)["down_streak"], 0.0)
        self.assertEqual(panel.at(4)["up_streak"], 1.0)
        self.assertEqual(panel.at(5)["down_streak"], 1.0)

    def test_bullish_engulfing_needs_a_down_bar_then_a_covering_up_bar(self):
        """Sabotage: drop the `was_down` term. Every strong up bar inside a
        rally then reads as a reversal signal, which is where these patterns
        earn their bad reputation."""
        down = _bar(0, o=100.0, h=100.5, low=94.0, c=95.0)
        engulf = _bar(1, o=94.5, h=101.5, low=94.0, c=101.0)
        self.assertEqual(_panel([down, engulf]).at(1)["bullish_engulfing"], 1.0)
        # same up bar, but yesterday was green: not a reversal of anything
        up = _bar(0, o=95.0, h=100.5, low=94.0, c=100.0)
        self.assertEqual(_panel([up, engulf]).at(1)["bullish_engulfing"], 0.0)
        # an up bar that does not cover yesterday's body
        small = _bar(1, o=94.5, h=96.0, low=94.0, c=95.5)
        self.assertEqual(_panel([down, small]).at(1)["bullish_engulfing"], 0.0)

    def test_bars_since_low_separates_the_low_from_the_days_after_it(self):
        """Buying on the bar that made the low is a different trade from buying
        eight bars later, and the search had no way to tell them apart."""
        prices = [100.0, 98.0, 90.0, 92.0, 94.0, 96.0]
        bars = [_bar(i, p, p + 0.5, p - 0.5, p) for i, p in enumerate(prices)]
        panel = _panel(bars)
        self.assertEqual(panel.at(2)["bars_since_low_20"], 0.0)
        self.assertEqual(panel.at(5)["bars_since_low_20"], 3.0)


class TestTheDeviationRate(unittest.TestCase):
    def test_distance_to_sma_20_is_kotegawa_s_deviation_rate(self):
        """He bought 20-35% below the 25-day average. The catalogue held the
        50 and 200-day versions, which measure trend position; only a short one
        measures dislocation, and dislocation is what a bounce trade is."""
        bars = [_bar(i, 100.0, 100.0, 100.0, 100.0) for i in range(20)]
        bars.append(_bar(20, 100.0, 100.0, 70.0, 72.0))
        row = _panel(bars).at(20)
        average = (100.0 * 19 + 72.0) / 20
        self.assertAlmostEqual(row["distance_to_sma_20"], 72.0 / average - 1, places=9)
        self.assertLess(row["distance_to_sma_20"], -0.25)

    def test_rsi_2_reaches_its_floor_while_rsi_14_does_not(self):
        """The whole point of a two-bar RSI, and it needs a RISING series to
        show: after a long climb, two down closes pin RSI(2) at its floor while
        RSI(14) still reads the trend it is embedded in. That gap is the signal
        -- on a flat series both collapse to zero and the test would pass while
        proving nothing.
        """
        prices = [100.0 + i for i in range(24)] + [118.0, 112.0]
        bars = [_bar(i, p, p + 0.5, p - 0.5, p) for i, p in enumerate(prices)]
        row = _panel(bars).at(len(prices) - 1)
        # Connors' famous threshold is 5, but that is a number he fitted to US
        # equities, not a property of the indicator: Wilder smoothing keeps a
        # little of the prior gain, so two down closes land near the floor
        # rather than on it. The gap between the two periods is the claim being
        # tested, and the search is what gets to pick the threshold.
        self.assertLess(row["rsi_2"], 10.0)
        self.assertGreater(row["rsi_14"], 5 * row["rsi_2"])


class TestTheLoopCanReachThem(unittest.TestCase):
    """A column the rule language cannot name is a column that does not exist."""

    def test_every_new_column_is_known_to_the_grammar(self):
        from quantlab_trading import grammar

        served = set(panel_for(_flat(3), IndicatorSpec()).names)
        for name in (
            "internal_bar_strength",
            "body_fraction",
            "upper_wick_fraction",
            "lower_wick_fraction",
            "down_streak",
            "up_streak",
            "bars_since_low_20",
            "volume_ratio_20",
            "range_vs_atr",
            "bullish_engulfing",
            "distance_to_sma_20",
            "rsi_2",
        ):
            self.assertIn(name, served, f"{name} is not served")
            self.assertIn(name, grammar.KNOWN_COLUMNS, f"{name} is unreachable")

    def test_an_additive_catalogue_change_leaves_old_columns_alone(self):
        """Adding columns must not move the ones already there.

        This is load-bearing beyond tidiness. The loop's gate compares a fit
        score against the best score recorded for that module, and I nearly
        discarded a legitimately-earned incumbent on the assumption that a
        wider catalogue made older scores incomparable. It does not: a score is
        a measurement of a configuration, and adding a column the configuration
        does not reference cannot move it. Measured rather than assumed.

        Sabotage: put a new period into `rsi_periods` that exceeds the current
        warmup, or recompute an existing column from a different source, and
        this fails -- which is exactly when old scores WOULD stop comparing.
        """
        import math

        before = IndicatorSpec(rsi_periods=(7, 14, 21))
        after = IndicatorSpec()
        bars = [
            _bar(i, 100.0 + i % 7, 102.0 + i % 7, 98.0 + i % 7, 100.5 + i % 7, 1e6 + i)
            for i in range(400)
        ]
        old, new = panel_for(bars, before), panel_for(bars, after)
        self.assertEqual(old.warmup_bars, new.warmup_bars)
        for index in (300, 399):
            a, b = old.at(index), new.at(index)
            for name in set(old.names) & set(new.names):
                x, y = a.get(name), b.get(name)
                if x is None or y is None:
                    self.assertIs(x, y, f"{name} at {index}")
                else:
                    self.assertTrue(
                        math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-12),
                        f"{name} at {index}: {x} != {y}",
                    )

    def test_the_grammar_never_names_a_column_that_is_not_served(self):
        """The failure this pairs against: a rule referencing a column nobody
        computes evaluates to None for ever and silently never fires."""
        from quantlab_trading import grammar

        served = set(panel_for(_flat(3), IndicatorSpec()).names)
        self.assertEqual(sorted(grammar.KNOWN_COLUMNS - served), [])


if __name__ == "__main__":
    unittest.main()
