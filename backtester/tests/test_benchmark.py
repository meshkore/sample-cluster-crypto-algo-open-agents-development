import unittest
from datetime import datetime, timedelta, timezone

from quantlab_backtester import benchmark
from quantlab_backtester.models import Bar


def bars(closes: list[float], start_day: int = 1) -> list[Bar]:
    start = datetime(2026, 1, start_day, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(days=index),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1_000_000.0,
        )
        for index, close in enumerate(closes)
    ]


WINDOW = (
    datetime(2026, 1, 1, tzinfo=timezone.utc),
    datetime(2026, 12, 31, tzinfo=timezone.utc),
)


class BuyAndHoldTest(unittest.TestCase):
    def test_a_doubling_market_returns_about_one_hundred_percent(self):
        held = benchmark.buy_and_hold({"BTCUSDT": bars([100, 150, 200])}, *WINDOW)
        # Entry pays slippage, exit pays slippage, both sides pay commission,
        # so it lands just under the gross 100%.
        self.assertLess(held, 1.0)
        self.assertGreater(held, 0.99)

    def test_costs_are_charged_and_not_quietly_waived(self):
        flat = benchmark.buy_and_hold({"BTCUSDT": bars([100, 100, 100])}, *WINDOW)
        self.assertLess(flat, 0.0)
        free = benchmark.buy_and_hold(
            {"BTCUSDT": bars([100, 100, 100])},
            *WINDOW,
            commission_bps=0.0,
            slippage_bps=0.0,
        )
        self.assertAlmostEqual(free, 0.0, places=9)

    def test_a_missing_or_too_short_series_is_none_not_zero(self):
        self.assertIsNone(benchmark.buy_and_hold({}, *WINDOW))
        self.assertIsNone(benchmark.buy_and_hold({"BTCUSDT": bars([100])}, *WINDOW))

    def test_only_bars_inside_the_window_are_used(self):
        # Ten years of history, but the window is a single week.
        series = bars([100] * 4 + [400] * 4)
        held = benchmark.buy_and_hold(
            {"BTCUSDT": series},
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 3, tzinfo=timezone.utc),
        )
        self.assertLess(abs(held), 0.01)


class EqualWeightTest(unittest.TestCase):
    def test_it_averages_the_assets_it_could_have_held(self):
        even = benchmark.equal_weight(
            {"A": bars([100, 200]), "B": bars([100, 100])},
            *WINDOW,
            commission_bps=0.0,
            slippage_bps=0.0,
        )
        self.assertAlmostEqual(even, 0.5, places=9)

    def test_an_asset_with_no_history_is_skipped_not_counted_as_flat(self):
        """Counting an unlisted asset as 0% is the survivorship bias itself."""
        even = benchmark.equal_weight(
            {"A": bars([100, 200]), "LISTED_LATER": []},
            *WINDOW,
            commission_bps=0.0,
            slippage_bps=0.0,
        )
        self.assertAlmostEqual(even, 1.0, places=9)

    def test_no_usable_asset_is_none(self):
        self.assertIsNone(benchmark.equal_weight({"A": []}, *WINDOW))


class EvaluateTest(unittest.TestCase):
    def test_excess_is_measured_against_the_harder_reference(self):
        result = benchmark.evaluate(
            {"BTCUSDT": bars([100, 110]), "A": bars([100, 300])},
            *WINDOW,
            strategy_return=0.50,
            commission_bps=0.0,
            slippage_bps=0.0,
        )
        # Equal weight (BTC +10%, A +200% → +105%) beats holding BTC, so it is
        # the reference: a strategy cannot look good by picking the weak one.
        self.assertEqual(result["reference_name"], "equal_weight")
        self.assertAlmostEqual(result["reference"], 1.05, places=9)
        self.assertAlmostEqual(result["excess_return"], 0.50 - 1.05, places=9)

    def test_no_benchmark_data_leaves_excess_unknown_rather_than_zero(self):
        result = benchmark.evaluate({}, *WINDOW, strategy_return=0.5)
        self.assertIsNone(result["reference"])
        self.assertIsNone(result["excess_return"])

    def test_a_strategy_that_beats_the_market_shows_positive_excess(self):
        result = benchmark.evaluate(
            {"BTCUSDT": bars([100, 110])},
            *WINDOW,
            strategy_return=0.40,
            commission_bps=0.0,
            slippage_bps=0.0,
        )
        self.assertAlmostEqual(result["excess_return"], 0.30, places=9)


if __name__ == "__main__":
    unittest.main()
