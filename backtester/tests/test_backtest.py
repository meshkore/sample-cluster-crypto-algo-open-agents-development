from datetime import datetime, timedelta, timezone
import unittest

from quantlab_backtester.backtest import Backtester, CostModel
from quantlab_backtester.models import Bar


def bars(opens, closes):
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(start + timedelta(days=i), o, max(o, c), min(o, c), c, 1000)
        for i, (o, c) in enumerate(zip(opens, closes))
    ]


class BacktesterTest(unittest.TestCase):
    def test_signal_is_filled_on_next_open(self):
        data = bars([100, 100, 110], [100, 110, 110])
        # Signal appears after bar zero. It participates only in bar one's move.
        result = Backtester(1000, CostModel(0, 0)).run(
            data, lambda observed: 1 if len(observed) == 1 else 0
        )
        self.assertAlmostEqual(result.final_equity, 1100)
        self.assertEqual(result.trades[0].timestamp, data[1].timestamp)

    def test_round_trip_costs_are_exact(self):
        data = bars([100, 100, 100], [100, 100, 100])
        result = Backtester(1000, CostModel(10, 0)).run(
            data, lambda observed: 1 if len(observed) == 1 else 0
        )
        self.assertAlmostEqual(result.final_equity, 998.001, places=6)
        self.assertAlmostEqual(result.total_commission, 1.999, places=6)

    def test_strategy_target_is_numeric(self):
        data = bars([100, 100, 100], [100, 100, 100])
        with self.assertRaises((TypeError, ValueError)):
            Backtester(1000, CostModel(0, 0)).run(data, lambda _: "invalid")

    def test_strategy_never_receives_future_bars(self):
        data = bars([100, 100, 100], [100, 100, 100])
        observed_lengths = []

        def audited_strategy(observed):
            observed_lengths.append(len(observed))
            return 0

        Backtester(1000, CostModel(0, 0)).run(data, audited_strategy)
        self.assertEqual(observed_lengths, [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
