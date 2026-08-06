from datetime import datetime, timedelta, timezone
import unittest

from quantlab_backtester.models import Bar
from quantlab_trading.strategies import build_strategy


def _bars(
    closes: list[float], taker_ratio: float = 0.5, volume: float = 1000.0
) -> list[Bar]:
    """Flat-range bars (high==low==close) with a fixed taker-buy ratio.

    Trend and momentum only read `close`; order-flow reads
    `taker_buy_volume`/`volume`, so a constant ratio isolates that factor
    from the other two in most tests below.
    """
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(days=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=volume,
            taker_buy_volume=volume * taker_ratio,
        )
        for i, close in enumerate(closes)
    ]


def _bars_with_ratios(
    closes: list[float], ratios: list[float], volume: float = 1000.0
) -> list[Bar]:
    """Like `_bars`, but with a distinct taker-buy ratio per bar (`Bar` is
    frozen, so per-bar variation must be built in, not mutated after)."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=start + timedelta(days=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=volume,
            taker_buy_volume=volume * ratio,
        )
        for i, (close, ratio) in enumerate(zip(closes, ratios))
    ]


def _trend(start: float, step: float, n: int) -> list[float]:
    return [start + step * i for i in range(n)]


class MultiFactorTrendTest(unittest.TestCase):
    """H-MULTI-001: long once >=2 of 3 votes (trend, momentum, order-flow)
    agree; the position survives a single dissenting vote and closes only
    once all 3 turn against it.
    """

    def _strategy(self, **params):
        return build_strategy(
            "multi_factor_trend",
            {
                "trend_period": 50,
                "rsi_period": 14,
                "flow_short_period": 5,
                "flow_long_period": 20,
                "rsi_floor": 50.0,
                "min_votes": 2,
                **params,
            },
        )

    def test_history_shorter_than_the_warmup_is_silent(self):
        strategy = self._strategy()
        bars = _bars(_trend(100.0, 1.0, 30))
        self.assertEqual(strategy.on_bar(bars), 0.0)

    def test_a_flat_price_and_flat_flow_never_enters(self):
        # Constant close: SMA never rises, RSI sits at 50 (not > floor), flow
        # ratio never diverges from its own baseline -- zero votes always.
        strategy = self._strategy()
        bars = _bars([100.0] * 80)
        self.assertEqual(strategy.on_bar(bars), 0.0)

    def test_a_sustained_uptrend_with_neutral_flow_reaches_two_votes(self):
        # Trend + momentum agree; flow stays neutral (constant ratio) so it
        # never casts a vote either way -- exactly 2 of 3, the entry floor.
        closes = _trend(100.0, 1.0, 80)
        strategy = self._strategy()
        signals = [strategy.on_bar(_bars(closes)[: i + 1]) for i in range(60, 80)]
        self.assertIn(round(2 / 3, 6), [round(s, 6) for s in signals])

    def test_a_sustained_downtrend_never_produces_a_long_signal(self):
        closes = _trend(200.0, -1.0, 80)
        strategy = self._strategy()
        for i in range(60, 80):
            self.assertEqual(strategy.on_bar(_bars(closes)[: i + 1]), 0.0)

    def test_all_three_factors_agreeing_gives_full_confidence(self):
        # Uptrend (trend+momentum) plus a taker-buy ratio rising above its
        # own longer baseline (flow) -- all 3 should agree.
        closes = _trend(100.0, 1.0, 80)
        ratios = [0.5] * (len(closes) - 5) + [0.8] * 5
        bars = _bars_with_ratios(closes, ratios)
        strategy = self._strategy()
        signal = strategy.on_bar(bars)
        self.assertEqual(signal, 1.0)

    def test_holding_survives_a_single_dissenting_vote(self):
        # Enter on a clean uptrend (2 votes), then flip momentum alone
        # against the position by forcing RSI's floor unreachable -- trend
        # is still up, so only 1 of 3 turns, not all 3.
        closes = _trend(100.0, 1.0, 80)
        bars = _bars(closes)
        strategy = self._strategy()
        entered = False
        for i in range(60, 80):
            signal = strategy.on_bar(bars[: i + 1])
            if signal > 0.0 and not entered:
                entered = True
                strategy.params["rsi_floor"] = 999.0
            elif entered:
                self.assertGreater(
                    signal,
                    0.0,
                    f"bar {i}: a single dissenting vote closed the position",
                )
        self.assertTrue(entered, "the setup never entered in the first place")

    def test_holding_is_closed_once_all_three_votes_turn(self):
        # Climb, then a hard enough reversal that trend, momentum and flow
        # all flip against the position.
        climb = _trend(100.0, 1.5, 70)
        fall = _trend(climb[-1], -3.0, 30)
        closes = climb + fall
        # Sellers dominate once the reversal starts.
        ratios = [0.5] * len(climb) + [0.2] * len(fall)
        bars = _bars_with_ratios(closes, ratios)
        strategy = self._strategy()
        entered = False
        exited = False
        for i in range(60, len(bars)):
            signal = strategy.on_bar(bars[: i + 1])
            if signal > 0.0:
                entered = True
            elif entered:
                exited = True
                break
        self.assertTrue(entered, "the setup never entered in the first place")
        self.assertTrue(exited, "a full reversal never closed the position")


if __name__ == "__main__":
    unittest.main()
