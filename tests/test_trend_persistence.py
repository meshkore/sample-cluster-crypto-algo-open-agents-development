from datetime import datetime, timedelta, timezone
import unittest

from quantlab.models import Bar
from quantlab.strategies import build_strategy


def _drift(daily_return: float, n: int, noise: float = 0.0006) -> list[float]:
    """A geometric drift with tiny alternating noise.

    Real bars are never noise-free, so a strategy that reads the mean-to-
    standard-deviation ratio of returns needs a nonzero standard deviation to
    exercise at all; a perfectly smooth exponential has zero variance in its
    log returns and would otherwise divide by zero.
    """
    price = 100.0
    closes = [price]
    for i in range(n - 1):
        price *= (1 + daily_return) * (1 + noise * (1 if i % 2 == 0 else -1))
        closes.append(price)
    return closes


def _bars(closes: list[float]) -> list[Bar]:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(days=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1000.0,
        )
        for i, close in enumerate(closes)
    ]


class TrendPersistenceTest(unittest.TestCase):
    """The signal is a t-statistic of drift, not a price-level breakout: it
    must stay silent on short history, flat noise, and a quiet grind that
    never clears the entry threshold, and it must grade its confidence by
    how far the drift's t-statistic sits above that threshold.
    """

    def _strategy(self, **params):
        return build_strategy(
            "trend_persistence",
            {
                "lookback": 30,
                "entry_threshold": 1.0,
                "confidence_ceiling": 3.0,
                **params,
            },
        )

    def test_history_shorter_than_lookback_is_silent(self):
        strategy = self._strategy()
        bars = _bars([100.0 + i for i in range(20)])
        self.assertEqual(strategy.on_bar(bars), 0.0)

    def test_flat_price_never_enters(self):
        strategy = self._strategy()
        bars = _bars([100.0] * 40)
        self.assertEqual(strategy.on_bar(bars), 0.0)

    def test_a_persistent_uptrend_clears_the_threshold(self):
        strategy = self._strategy()
        bars = _bars(_drift(0.01, 40))
        confidence = strategy.on_bar(bars)
        self.assertGreater(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)

    def test_confidence_saturates_at_the_ceiling_rather_than_exceeding_one(self):
        strategy = self._strategy(confidence_ceiling=1.01)
        bars = _bars(_drift(0.02, 40))
        self.assertEqual(strategy.on_bar(bars), 1.0)

    def test_a_noisier_series_scores_a_weaker_trend_than_a_calmer_one(self):
        calm = self._strategy()
        rough = self._strategy()
        calm_closes = _drift(0.006, 40, noise=0.0006)
        rough_closes = _drift(0.006, 40, noise=0.02)
        self.assertGreater(
            calm.on_bar(_bars(calm_closes)), rough.on_bar(_bars(rough_closes))
        )

    def test_a_downtrend_never_produces_a_long_signal(self):
        strategy = self._strategy()
        bars = _bars(_drift(-0.01, 40))
        self.assertEqual(strategy.on_bar(bars), 0.0)


if __name__ == "__main__":
    unittest.main()
