from datetime import datetime, timedelta, timezone
import unittest

from quantlab.models import Bar
from quantlab.strategies import build_strategy


def _bars(closes: list[float], spread: float = 0.4) -> list[Bar]:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = []
    previous = closes[0]
    for index, close in enumerate(closes):
        high = max(previous, close) + spread
        low = min(previous, close) - spread
        bars.append(
            Bar(
                timestamp=start + timedelta(hours=index),
                open=previous,
                high=high,
                low=low,
                close=close,
                volume=1000.0,
            )
        )
        previous = close
    return bars


def _trend(start: float, step: float, count: int) -> list[float]:
    return [start + step * index for index in range(count)]


class SMARSITrendTest(unittest.TestCase):
    """H-SMARSI-001: fast SMA > slow SMA, RSI above a floor, and close above
    the fast SMA -- all three to enter. Exit on the trend turning or RSI
    exceeding its ceiling. Confidence is binary, never graded.
    """

    def _strategy(self, **params):
        return build_strategy(
            "sma_rsi_trend",
            {
                "fast_period": 10,
                "slow_period": 30,
                "rsi_period": 14,
                "rsi_floor": 50.0,
                "rsi_ceiling": 75.0,
                **params,
            },
        )

    def test_history_shorter_than_the_slow_average_is_silent(self):
        strategy = self._strategy()
        self.assertEqual(strategy.on_bar(_bars(_trend(100.0, 0.5, 20))), 0.0)

    def test_a_steady_uptrend_opens_a_position(self):
        # A ceiling of 100 keeps the momentum exit out of the way so this
        # test measures the entry conditions only.
        closes = _trend(100.0, 1.0, 60)
        strategy = self._strategy(rsi_ceiling=100.0)
        signals = [strategy.on_bar(_bars(closes)[: i + 1]) for i in range(30, 60)]
        self.assertIn(1.0, signals)

    def test_the_signal_is_binary_and_never_graded(self):
        closes = _trend(100.0, 1.0, 40) + _trend(140.0, -1.0, 40)
        strategy = self._strategy(rsi_ceiling=100.0)
        bars = _bars(closes)
        signals = {strategy.on_bar(bars[: i + 1]) for i in range(30, len(bars))}
        self.assertTrue(
            signals <= {0.0, 1.0}, f"expected only 0.0/1.0, saw {sorted(signals)}"
        )

    def test_a_downtrend_never_opens_a_position(self):
        closes = _trend(300.0, -1.0, 60)
        strategy = self._strategy()
        for i in range(30, 60):
            self.assertEqual(strategy.on_bar(_bars(closes)[: i + 1]), 0.0)

    def test_the_trend_turning_closes_the_position(self):
        climb = _trend(100.0, 1.0, 60)
        fall = _trend(climb[-1], -2.0, 40)
        bars = _bars(climb + fall)
        strategy = self._strategy(rsi_ceiling=100.0)
        opened = closed = False
        for i in range(30, len(bars)):
            signal = strategy.on_bar(bars[: i + 1])
            if signal == 1.0:
                opened = True
            elif opened and signal == 0.0:
                closed = True
                break
        self.assertTrue(opened, "the position never opened in the first place")
        self.assertTrue(closed, "the position never closed once the trend turned")

    def test_an_rsi_ceiling_breach_closes_the_position(self):
        # A pure one-directional climb pins RSI at 100, so a low ceiling must
        # exit while the trend is still intact -- isolating the momentum exit
        # from the trend exit.
        closes = _trend(100.0, 1.0, 60)
        bars = _bars(closes)
        strategy = self._strategy(rsi_ceiling=60.0)
        signals = [strategy.on_bar(bars[: i + 1]) for i in range(30, len(bars))]
        self.assertNotIn(1.0, signals)

    def test_a_high_rsi_floor_blocks_entry_that_a_low_floor_allows(self):
        # The RSI gate has to be load-bearing: same bars, same trend, only
        # the floor differs.
        closes = _trend(100.0, 1.0, 60)
        bars = _bars(closes)
        permissive = [
            self._strategy(rsi_floor=40.0, rsi_ceiling=100.0).on_bar(bars[: i + 1])
            for i in range(30, len(bars))
        ]
        blocked = self._strategy(rsi_floor=101.0, rsi_ceiling=200.0)
        strict = [blocked.on_bar(bars[: i + 1]) for i in range(30, len(bars))]
        self.assertIn(1.0, permissive)
        self.assertNotIn(1.0, strict)

    def test_reset_clears_an_open_position(self):
        closes = _trend(100.0, 1.0, 60)
        bars = _bars(closes)
        strategy = self._strategy(rsi_ceiling=100.0)
        for i in range(30, len(bars)):
            strategy.on_bar(bars[: i + 1])
        self.assertTrue(strategy.active)
        strategy.reset()
        self.assertFalse(strategy.active)


if __name__ == "__main__":
    unittest.main()
