from datetime import datetime, timedelta, timezone
import unittest

from quantlab.backtest import CostModel
from quantlab.models import Bar
from quantlab.portfolio import (
    LongOnlyExecutionBacktester,
    LongOnlyPortfolioBacktester,
    MoneyManagement,
)


def bars(rows):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(start + timedelta(days=i), open_, high, low, close, 1000)
        for i, (open_, high, low, close) in enumerate(rows)
    ]


class PortfolioExecutionTest(unittest.TestCase):
    def test_negative_signal_cannot_open_short(self):
        data = bars([(100, 101, 99, 100), (100, 110, 90, 95), (95, 100, 90, 92)])
        result = LongOnlyExecutionBacktester(CostModel(0, 0), MoneyManagement()).run(
            "BTCUSDT", data, lambda _: -1, 1000
        )
        self.assertEqual(result.final_equity, 1000)
        self.assertEqual(result.trades, [])

    def test_risk_sizing_and_stop_loss(self):
        data = bars([(100, 101, 99, 100), (100, 101, 94, 96), (96, 97, 95, 96)])
        policy = MoneyManagement(
            risk_per_trade=0.01,
            maximum_position_fraction=0.25,
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
        )
        result = LongOnlyExecutionBacktester(CostModel(0, 0), policy).run(
            "BTCUSDT", data, lambda observed: 1 if len(observed) == 1 else 0, 1000
        )
        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertAlmostEqual(trade.invested_capital, 200)
        self.assertAlmostEqual(trade.pnl, -10)
        self.assertEqual(trade.exit_reason, "STOP_LOSS")
        self.assertEqual(trade.duration_seconds, 0)

    def test_take_profit_and_trade_duration_are_recorded(self):
        data = bars([(100, 101, 99, 100), (100, 108, 99, 106), (106, 112, 105, 111)])
        result = LongOnlyExecutionBacktester(CostModel(0, 0), MoneyManagement()).run(
            "ETHUSDT", data, lambda _: 1, 1000
        )
        self.assertEqual(result.trades[0].exit_reason, "TAKE_PROFIT")
        self.assertEqual(result.trades[0].duration_seconds, 86400)
        self.assertGreater(result.trades[0].pnl, 0)

    def test_shared_portfolio_never_overspends_and_sizes_by_confidence(self):
        data = bars(
            [
                (100, 101, 99, 100),
                (100, 102, 99, 101),
                (101, 103, 100, 102),
                (102, 103, 101, 102),
            ]
        )
        policy = MoneyManagement(
            risk_per_trade=0.01,
            stop_loss_pct=0.05,
            maximum_position_fraction=0.8,
            minimum_order_notional=1,
        )
        engine = LongOnlyPortfolioBacktester(CostModel(0, 0), policy)
        result = engine.run(
            {"BTCUSDT": data, "ETHUSDT": data}, lambda: lambda _: 0.5, 1000
        )
        self.assertGreaterEqual(min(point["cash"] for point in result.equity_curve), 0)
        self.assertLessEqual(sum(x.peak_capital_at_risk for x in result.assets), 1000)
        self.assertTrue(all(trade.invested_capital > 0 for trade in result.trades))

    def test_shared_portfolio_reports_progress_and_no_short_trades(self):
        data = bars([(100, 101, 99, 100), (100, 102, 99, 101), (101, 103, 100, 102)])
        progress = []
        result = LongOnlyPortfolioBacktester(CostModel(0, 0), MoneyManagement()).run(
            {"BTCUSDT": data}, lambda: lambda _: -1, 1000, progress.append
        )
        self.assertEqual(result.trades, [])
        self.assertEqual(result.final_equity, 1000)
        self.assertEqual(progress[-1]["processed_days"], progress[-1]["total_days"])

    def test_portfolio_is_pruned_immediately_at_drawdown_limit(self):
        data = bars(
            [
                (100, 101, 99, 100),
                (100, 101, 70, 72),
                (72, 73, 60, 62),
                (62, 63, 50, 52),
            ]
        )
        policy = MoneyManagement(
            risk_per_trade=0.25,
            maximum_position_fraction=1,
            stop_loss_pct=0.30,
            take_profit_pct=0.90,
            maximum_drawdown=0.25,
            minimum_order_notional=1,
        )
        result = LongOnlyPortfolioBacktester(CostModel(0, 0), policy).run(
            {"BTCUSDT": data}, lambda: lambda _: 1, 1000
        )
        self.assertTrue(result.aborted)
        self.assertEqual(result.abort_reason, "DRAWDOWN_SAFETY_TRIGGER")
        self.assertLess(len(result.equity_curve), len(data))
        self.assertEqual(result.trades[-1].exit_reason, "MAX_DRAWDOWN_ABORT")


if __name__ == "__main__":
    unittest.main()
