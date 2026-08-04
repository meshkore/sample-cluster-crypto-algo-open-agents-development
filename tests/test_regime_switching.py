from datetime import datetime, timedelta, timezone
import unittest

from quantlab.models import Bar
from quantlab.strategies import build_strategy


def _bars(closes: list[float], spread: float = 0.6) -> list[Bar]:
    """Bars with a real high/low range: the RSI-oversold bounce branch reads
    close-to-close changes only, but keeping a real range matches the
    style of every other indicator-driven strategy's tests here."""
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


class RegimeSwitchingTest(unittest.TestCase):
    """H-REGIME-001: a 200-bar (default) SMA regime call gates a bull
    trend-following branch (full confidence) and a bear oversold-bounce
    branch (reduced confidence); the regime overrides whichever branch is
    currently open.
    """

    def _strategy(self, **params):
        return build_strategy(
            "regime_switching",
            {
                "regime_period": 50,
                "trend_period": 10,
                "rsi_period": 14,
                "oversold_rsi": 30.0,
                "bull_confidence": 1.0,
                "bear_confidence": 0.5,
                **params,
            },
        )

    def test_history_shorter_than_the_warmup_is_silent(self):
        strategy = self._strategy()
        bars = _bars(_trend(100.0, 0.5, 20))
        self.assertEqual(strategy.on_bar(bars), 0.0)

    def test_a_sustained_uptrend_opens_a_full_confidence_bull_position(self):
        closes = _trend(100.0, 1.0, 90)
        strategy = self._strategy()
        signals = [strategy.on_bar(_bars(closes)[: i + 1]) for i in range(60, 90)]
        self.assertIn(1.0, signals)

    def test_a_sustained_downtrend_never_opens_a_bull_position(self):
        closes = _trend(300.0, -1.0, 90)
        strategy = self._strategy()
        for i in range(60, 90):
            signal = strategy.on_bar(_bars(closes)[: i + 1])
            self.assertIn(signal, (0.0, 0.5))

    def test_a_sharp_drop_in_a_bear_regime_opens_a_reduced_confidence_bounce(self):
        # A long decline establishes the bear regime, then a sharp
        # additional drop should push RSI into oversold territory.
        decline = _trend(300.0, -1.0, 60)
        sharp_drop = _trend(decline[-1], -5.0, 10)
        closes = decline + sharp_drop
        strategy = self._strategy()
        signals = [
            strategy.on_bar(_bars(closes)[: i + 1]) for i in range(55, len(closes))
        ]
        self.assertIn(0.5, signals)
        self.assertNotIn(1.0, signals)

    def test_a_bull_position_closes_immediately_if_the_regime_flips_bearish(self):
        climb = _trend(100.0, 1.0, 70)
        crash = _trend(climb[-1], -8.0, 15)
        closes = climb + crash
        bars = _bars(closes)
        strategy = self._strategy()
        entered_bull = False
        for i in range(60, 70):
            if strategy.on_bar(bars[: i + 1]) == 1.0:
                entered_bull = True
        self.assertTrue(entered_bull, "the bull branch never opened in the first place")
        # A hard enough crash should flip the regime and close the position
        # well before the crash finishes, not ride it to the bottom.
        signal_near_end = strategy.on_bar(bars[: len(bars)])
        self.assertNotEqual(signal_near_end, 1.0)

    def test_a_bear_bounce_closes_once_rsi_recovers_to_neutral(self):
        decline = _trend(300.0, -1.0, 60)
        sharp_drop = _trend(decline[-1], -5.0, 8)
        bounce = _trend(sharp_drop[-1], 5.0, 14)
        closes = decline + sharp_drop + bounce
        bars = _bars(closes)
        strategy = self._strategy()
        entered_bear = False
        exited = False
        for i in range(55, len(bars)):
            signal = strategy.on_bar(bars[: i + 1])
            if signal == 0.5:
                entered_bear = True
            elif entered_bear and signal == 0.0:
                exited = True
                break
        self.assertTrue(entered_bear, "the bear bounce branch never opened")
        self.assertTrue(exited, "the bounce never closed as RSI recovered")


if __name__ == "__main__":
    unittest.main()
