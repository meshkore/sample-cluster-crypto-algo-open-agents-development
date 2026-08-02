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
        self.assertEqual(result.abort_reason, "MAX_DRAWDOWN_ABORT")
        self.assertLess(len(result.equity_curve), len(data))
        self.assertEqual(result.trades[-1].exit_reason, "STOP_LOSS")

    def test_portfolio_refuses_entries_without_causal_liquidity(self):
        data = bars(
            [
                (100, 101, 99, 100),
                (100, 102, 99, 101),
                (101, 103, 100, 102),
                (102, 104, 101, 103),
            ]
        )
        policy = MoneyManagement(
            minimum_daily_quote_volume=1_000_000,
            maximum_volume_participation=0.001,
            minimum_order_notional=1,
        )
        result = LongOnlyPortfolioBacktester(CostModel(0, 0), policy).run(
            {"ILLQUSDT": data}, lambda: lambda _: 1, 1_000
        )
        self.assertEqual(result.trades, [])

    def test_gap_through_stop_uses_open_not_an_impossible_stop_fill(self):
        data = bars(
            [
                (100, 101, 99, 100),
                (100, 102, 99, 101),
                (90, 92, 85, 88),
                (88, 89, 87, 88),
            ]
        )
        result = LongOnlyExecutionBacktester(
            CostModel(0, 0), MoneyManagement(stop_loss_pct=0.05)
        ).run("BTCUSDT", data, lambda _: 1, 1_000)
        self.assertEqual(result.trades[0].exit_reason, "STOP_LOSS")
        self.assertEqual(result.trades[0].exit_price, 90)


if __name__ == "__main__":
    unittest.main()


class SizingCausalityTest(unittest.TestCase):
    """QUANT8: the volatility that sizes a fill may not see that fill's day."""

    def series(self, shock_close: float) -> list[Bar]:
        # Thirty identical calm days, then one day whose OPEN matches them and
        # whose CLOSE is a crash. At that open the crash has not happened, so a
        # causal engine must size the entry exactly as it would on a calm day.
        data = bars([(100, 101, 99, 100)] * 30)
        after = data[-1].timestamp + timedelta(days=1)
        data.append(
            Bar(
                after,
                100,
                max(100.0, shock_close),
                min(100.0, shock_close),
                shock_close,
                1000,
            )
        )
        data.append(
            Bar(
                after + timedelta(days=1),
                shock_close,
                shock_close,
                shock_close,
                shock_close,
                1000,
            )
        )
        return data

    def entry_on_the_shock_day(self, shock_close: float) -> float:
        data = self.series(shock_close)
        shock_day = data[-2].timestamp
        policy = MoneyManagement(
            minimum_order_notional=1,
            minimum_position_fraction=0.0,
            minimum_daily_quote_volume=0,
        )

        # Flat until the day before the shock, so the only entry lands on it.
        def factory():
            return lambda observed: 1.0 if len(observed) >= len(data) - 2 else 0.0

        result = LongOnlyPortfolioBacktester(CostModel(0, 0), policy).run(
            {"BTCUSDT": data}, factory, 10_000
        )
        sized = [t.invested_capital for t in result.trades if t.entry_time == shock_day]
        self.assertTrue(sized, "expected an entry on the shock day")
        return sized[0]

    def test_the_days_own_close_cannot_change_the_size_of_its_open(self):
        calm = self.entry_on_the_shock_day(100.0)
        crash = self.entry_on_the_shock_day(60.0)
        # Before the fix the crash day sized far smaller, because the engine
        # already knew the day would be violent while filling at its open.
        self.assertAlmostEqual(calm, crash, places=6)
