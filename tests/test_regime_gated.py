from datetime import datetime, timedelta, timezone
import unittest

from quantlab.models import Bar
from quantlab.strategies import build_strategy, initial_hypotheses


def _closes_from_returns(daily_return: float, n: int, noise: float = 0.001) -> list[float]:
    """A geometric drift with small alternating noise."""
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


def _regime_series() -> list[float]:
    """bear -> range -> bull, the planted regime structure our HMM recovers."""
    closes: list[float] = []
    x = 100.0
    for _ in range(60):
        x *= 0.995  # bear drift
        closes.append(x)
    for _ in range(60):
        x *= 1.0  # range
        closes.append(x)
    for _ in range(80):
        x *= 1.004  # bull drift
        closes.append(x)
    return closes


class RegimeGatedTest(unittest.TestCase):
    """The signal is the smoothed bull posterior of a dependency-free HMM,
    gated by a minimum dwell: it must stay silent on short history and on a
    bear regime, turn on only after sustained bull evidence, and return a
    continuous confidence rather than a flat 0/1 label."""

    def _strategy(self, **params):
        return build_strategy(
            "regime_gated",
            {
                "fit_window": 60,
                "refit_every": 10,
                "entry_threshold": 0.55,
                "exit_threshold": 0.45,
                "min_dwell": 3,
                "n_states": 3,
                "seed": 42,
                **params,
            },
        )

    def test_hypothesis_is_registered(self):
        ids = {h.id for h in initial_hypotheses("transfer")}
        self.assertIn("H-REGIME-001", ids)
        hyp = next(h for h in initial_hypotheses("transfer") if h.id == "H-REGIME-001")
        self.assertEqual(hyp.family, "regime_gated")
        self.assertIn("hmm_bull_posterior", hyp.features)

    def test_history_shorter_than_fit_window_is_silent(self):
        strategy = self._strategy()
        bars = _bars([100.0 + i for i in range(30)])
        self.assertEqual(strategy.on_bar(bars), 0.0)

    def test_bear_regime_produces_no_long_signal(self):
        strategy = self._strategy()
        bars = _bars(_closes_from_returns(-0.006, 200))
        # Feed bars one at a time so the strategy sees the whole bear tape.
        out = []
        for i in range(1, len(bars) + 1):
            out.append(strategy.on_bar(bars[:i]))
        self.assertEqual(max(out), 0.0)

    def test_planted_bull_regime_eventually_enters(self):
        strategy = self._strategy()
        bars = _bars(_regime_series())
        out = []
        for i in range(1, len(bars) + 1):
            out.append(strategy.on_bar(bars[:i]))
        self.assertGreater(max(out), 0.0)

    def test_signal_is_continuous_confidence_not_binary(self):
        strategy = self._strategy()
        bars = _bars(_regime_series())
        out = []
        for i in range(1, len(bars) + 1):
            out.append(strategy.on_bar(bars[:i]))
        nonzero = [v for v in out if v > 0.0]
        self.assertTrue(nonzero)
        # The signal must be graded, not a flat 0/1: at least one bar carries
        # a strictly intermediate confidence (a probability inside (0,1)).
        graded = [v for v in nonzero if 0.0 < v < 1.0]
        self.assertTrue(graded, "signal collapsed to a binary 0/1 gate")
        self.assertLessEqual(max(nonzero), 1.0)

    def test_deterministic_under_same_seed(self):
        a = self._strategy()
        b = self._strategy()
        bars = _bars(_regime_series())
        out_a, out_b = [], []
        for i in range(1, len(bars) + 1):
            out_a.append(a.on_bar(bars[:i]))
        for i in range(1, len(bars) + 1):
            out_b.append(b.on_bar(bars[:i]))
        self.assertEqual(out_a, out_b)


if __name__ == "__main__":
    unittest.main()
