from datetime import datetime, timedelta, timezone
import unittest

from quantlab.models import Bar
from quantlab.strategies import build_strategy


def _bars(closes: list[float]) -> list[Bar]:
    """Flat bars (high == low == close): Donchian only reads high/low/close
    levels, unlike ATR-based strategies it needs no real intrabar range."""
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


def _trend(start: float, step: float, n: int) -> list[float]:
    return [start + step * i for i in range(n)]


class DonchianBreakoutTest(unittest.TestCase):
    """H-DONCH-001: long on a fresh N-bar high, flat on a fresh M-bar low
    (M<N) -- the classic Turtle Trading breakout, long side only.
    """

    def _strategy(self, **params):
        return build_strategy(
            "donchian_breakout", {"entry_period": 20, "exit_period": 10, **params}
        )

    def test_history_shorter_than_the_entry_period_is_silent(self):
        strategy = self._strategy()
        bars = _bars(_trend(100.0, 1.0, 15))
        self.assertEqual(strategy.on_bar(bars), 0.0)

    def test_a_flat_price_never_enters(self):
        # Every close ties the prior N-bar high exactly, never exceeds it.
        strategy = self._strategy()
        bars = _bars([100.0] * 30)
        self.assertEqual(strategy.on_bar(bars), 0.0)

    def test_a_downtrend_never_produces_a_long_signal(self):
        strategy = self._strategy()
        bars = _bars(_trend(200.0, -1.0, 30))
        for i in range(20, 30):
            self.assertEqual(strategy.on_bar(bars[: i + 1]), 0.0)

    def test_a_sustained_uptrend_eventually_breaks_out(self):
        closes = _trend(100.0, 1.5, 30)
        strategy = self._strategy()
        signals = [strategy.on_bar(_bars(closes)[: i + 1]) for i in range(20, 30)]
        self.assertIn(1.0, signals)

    def test_a_break_below_the_exit_channel_closes_the_position(self):
        # Climb past the entry channel, then fall hard enough to clear the
        # (shorter) exit channel's own low.
        climb = _trend(100.0, 1.5, 25)
        closes = climb + _trend(climb[-1], -3.0, 15)
        all_bars = _bars(closes)
        strategy = self._strategy()
        entered = False
        exited = False
        for i in range(20, len(all_bars)):
            signal = strategy.on_bar(all_bars[: i + 1])
            if signal == 1.0:
                entered = True
            elif entered and signal == 0.0:
                exited = True
                break
        self.assertTrue(entered, "the setup never entered in the first place")
        self.assertTrue(exited, "a hard reversal never closed the position")

    def test_holding_survives_a_pullback_that_does_not_clear_the_exit_channel(self):
        # A single one-bar dip, far shallower than the 10-bar exit channel's
        # own low, must not be mistaken for a fresh M-bar low.
        closes = _trend(100.0, 1.5, 25)
        dip = closes[-1] - 0.5  # one small dip, then resume climbing
        closes.append(dip)
        closes += _trend(dip + 1.5, 1.5, 5)
        all_bars = _bars(closes)
        strategy = self._strategy()
        entered = False
        for i in range(20, len(all_bars)):
            signal = strategy.on_bar(all_bars[: i + 1])
            if signal == 1.0:
                entered = True
            elif entered:
                self.fail(f"bar {i}: holding was revoked by a shallow pullback")
        self.assertTrue(entered, "the setup never entered in the first place")


if __name__ == "__main__":
    unittest.main()
