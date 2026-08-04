from datetime import datetime, timedelta, timezone
import unittest

from quantlab.models import Bar
from quantlab.strategies import build_strategy


def _bars(closes: list[float], spread: float = 0.6) -> list[Bar]:
    """Bars with a real high/low range around each close.

    SuperTrend and ADX are both built from true range and directional
    movement between highs and lows — a degenerate high==low==close bar (the
    shape most other strategy tests use) would make every true range zero
    and the whole indicator pair undefined.
    """
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = []
    prev = closes[0]
    for i, close in enumerate(closes):
        o = prev
        high, low = max(o, close) + spread, min(o, close) - spread
        bars.append(
            Bar(
                timestamp=start + timedelta(days=i),
                open=o,
                high=high,
                low=low,
                close=close,
                volume=1000.0,
            )
        )
        prev = close
    return bars


def _trend(start: float, step: float, n: int) -> list[float]:
    return [start + step * i for i in range(n)]


class SuperTrendADXTest(unittest.TestCase):
    """H-STA-001: a SuperTrend bullish flip, authorized only when ADX (the
    trend-strength gate) clears its threshold at that same flip — and, once
    authorized, held until SuperTrend itself flips bearish, not re-checked
    against ADX on every later bar.
    """

    def _strategy(self, **params):
        return build_strategy(
            "supertrend_adx",
            {
                "atr_period": 10,
                "adx_period": 14,
                "multiplier": 3.0,
                "adx_threshold": 20.0,
                "supertrend_window": 40,
                "adx_window": 30,
                **params,
            },
        )

    def test_history_shorter_than_the_indicator_periods_is_silent(self):
        strategy = self._strategy()
        bars = _bars(_trend(100.0, 0.5, 10))
        self.assertEqual(strategy.on_bar(bars), 0.0)

    def test_a_flat_price_never_enters(self):
        # open==close every bar, so the band's midpoint tracks price exactly
        # and close is never strictly above it — bullish can never turn true.
        strategy = self._strategy()
        bars = [
            Bar(
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
                open=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
                volume=1000.0,
            )
            for i in range(60)
        ]
        self.assertEqual(strategy.on_bar(bars), 0.0)

    def test_a_sustained_downtrend_never_produces_a_long_signal(self):
        strategy = self._strategy(adx_threshold=0.0)
        bars = _bars(_trend(200.0, -1.0, 60))
        for i in range(35, 60):
            self.assertEqual(strategy.on_bar(bars[: i + 1]), 0.0)

    def test_a_strong_uptrend_enters_once_the_adx_gate_is_disabled(self):
        # A decline into a sharp, sustained climb: enough directional
        # movement to both flip SuperTrend bullish and clear a permissive
        # ADX floor.
        closes = _trend(150.0, -1.0, 20) + _trend(131.0, 3.0, 40)
        strategy = self._strategy(adx_threshold=0.0)
        signals = [strategy.on_bar(_bars(closes)[: i + 1]) for i in range(20, 60)]
        self.assertIn(1.0, signals)

    def test_an_unreachable_adx_threshold_blocks_entry_despite_the_same_trend(self):
        closes = _trend(150.0, -1.0, 20) + _trend(131.0, 3.0, 40)
        strategy = self._strategy(adx_threshold=999.0)
        signals = [strategy.on_bar(_bars(closes)[: i + 1]) for i in range(20, 60)]
        self.assertNotIn(1.0, signals)

    def test_holding_is_not_revoked_by_adx_once_the_flip_authorized_it(self):
        closes = _trend(150.0, -1.0, 20) + _trend(131.0, 3.0, 40)
        all_bars = _bars(closes)
        strategy = self._strategy(adx_threshold=0.0)
        entered = False
        for i in range(20, 60):
            signal = strategy.on_bar(all_bars[: i + 1])
            if signal == 1.0 and not entered:
                entered = True
                # Simulate ADX collapsing well below any realistic threshold
                # for every subsequent bar. A position already open must not
                # be re-vetoed by it — only a fresh SuperTrend flip is gated.
                strategy.params["adx_threshold"] = 1000.0
            elif entered:
                self.assertEqual(signal, 1.0, f"bar {i}: holding was revoked")
        self.assertTrue(entered, "the setup never entered in the first place")


if __name__ == "__main__":
    unittest.main()
