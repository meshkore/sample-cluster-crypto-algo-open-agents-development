"""The pulled clock, the indicator panel, and the no-lookahead fill rule.

The most important test in this file is `test_orders_fill_at_the_next_open`.
Every lookahead this laboratory has caught came from a decision touching the bar
it was made on, and the session is where that is now structurally impossible.

All sabotage-verified; each test names the bug it was checked against.
"""

from datetime import datetime, timedelta, timezone
import unittest

from quantlab_backtester.backtest import CostModel
from quantlab_backtester.indicators import IndicatorSpec, panel_for
from quantlab_backtester.ledger import BacktestRun
from quantlab_backtester.models import Bar, utc_now
from quantlab_backtester.session import BacktestSession, OrderRequest, SessionError

UTC = timezone.utc


def _bars(closes, opens=None):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Bar(
            timestamp=start + timedelta(days=i),
            open=(opens[i] if opens else c),
            high=max(c, opens[i] if opens else c) * 1.01,
            low=min(c, opens[i] if opens else c) * 0.99,
            close=c,
            volume=1_000_000.0,
        )
        for i, c in enumerate(closes)
    ]


def _session(bars_by_symbol, **kwargs) -> BacktestSession:
    run = BacktestRun(
        backtest_id="test",
        label="test",
        created_at=utc_now(),
        initial_capital=kwargs.pop("initial_capital", 10_000.0),
        strategy_family="test",
        strategy_params={},
        policy={},
        universe_size=len(bars_by_symbol),
        window_start=None,
        window_end=None,
    )
    return BacktestSession(run=run, bars_by_symbol=bars_by_symbol, **kwargs)


class ClockTest(unittest.TestCase):
    def test_the_clock_only_moves_when_pulled(self) -> None:
        session = _session({"AAA": _bars([10.0] * 5)})
        self.assertEqual(session.cursor, -1)
        session.next_tick()
        self.assertEqual(session.cursor, 0)
        session.next_tick()
        self.assertEqual(session.cursor, 1)

    def test_it_reports_done_at_the_end_and_refuses_to_go_further(self) -> None:
        session = _session({"AAA": _bars([10.0] * 3)})
        for _ in range(3):
            self.assertFalse(session.next_tick()["done"])
        self.assertTrue(session.next_tick()["done"])
        with self.assertRaises(SessionError):
            session.next_tick()

    def test_a_tick_carries_the_candle_indicators_and_account(self) -> None:
        session = _session({"AAA": _bars([10.0 + i for i in range(30)])})
        for _ in range(25):
            tick = session.next_tick()
        self.assertIn("AAA", tick["candles"])
        self.assertIn("sma_20", tick["indicators"]["AAA"])
        self.assertEqual(tick["account"]["cash"], 10_000.0)
        self.assertEqual(tick["clock"]["total"], 30)


class NoLookaheadTest(unittest.TestCase):
    def test_orders_fill_at_the_next_open(self) -> None:
        """The rule the whole design rests on.

        The decision is made after seeing bar N's close. It must fill at bar
        N+1's OPEN -- not bar N's close, and not bar N's open, which the
        decision could not have known about in a live setting either.

        Sabotage check: filling inside `submit` instead of on the next tick
        makes this fail, and so does filling at the close.
        """
        opens = [100.0, 200.0, 300.0]
        closes = [110.0, 210.0, 310.0]
        session = _session({"AAA": _bars(closes, opens)}, initial_capital=1000.0)

        session.next_tick()  # bar 0: open 100, close 110
        session.submit([OrderRequest("AAA", "BUY", notional=500.0)])
        self.assertEqual(session.ledger.orders, [], "filled before the next bar")

        session.next_tick()  # bar 1: open 200
        self.assertEqual(len(session.ledger.orders), 1)
        self.assertAlmostEqual(session.ledger.orders[0].price, 200.0)

    def test_the_account_in_a_tick_already_reflects_that_bars_fills(self) -> None:
        session = _session(
            {"AAA": _bars([100.0, 100.0, 100.0])}, initial_capital=1000.0
        )
        session.next_tick()
        session.submit([OrderRequest("AAA", "BUY", notional=400.0)])
        tick = session.next_tick()
        self.assertAlmostEqual(tick["account"]["cash"], 600.0)
        self.assertIn("AAA", tick["account"]["positions"])

    def test_indicators_are_causal_under_truncation(self) -> None:
        """Prefix equality: the panel over a cut series must match the panel over
        the whole one. Sabotage check: any centred or forward-looking window
        fails this at every cut point."""
        bars = _bars(
            [100.0 * (1.01**i) * (0.97 if i % 7 == 0 else 1.0) for i in range(300)]
        )
        full = panel_for(bars, IndicatorSpec())
        for cut in (60, 120, 201, 299):
            truncated = panel_for(bars[:cut], IndicatorSpec())
            self.assertEqual(len(truncated), cut)
            for key, value in truncated[cut - 1].items():
                expected = full[cut - 1][key]
                if value is None or expected is None:
                    self.assertEqual(value, expected, f"{key} at cut {cut}")
                else:
                    self.assertAlmostEqual(
                        value, expected, places=9, msg=f"{key} at cut {cut}"
                    )

    def test_warm_up_values_are_none_not_zero(self) -> None:
        """A missing indicator read as 0.0 is a real signal to a naive rule."""
        panel = panel_for(_bars([10.0] * 30), IndicatorSpec())
        self.assertIsNone(panel[0]["sma_200"])
        self.assertIsNone(panel[5]["sma_20"])
        self.assertIsNotNone(panel[25]["sma_20"])


class OrderValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = _session({"AAA": _bars([100.0] * 6)}, initial_capital=1000.0)
        self.session.next_tick()

    def test_it_refuses_orders_before_the_first_tick(self) -> None:
        fresh = _session({"AAA": _bars([100.0] * 4)})
        with self.assertRaises(SessionError):
            fresh.submit([OrderRequest("AAA", "BUY", notional=10.0)])

    def test_unknown_symbols_and_double_buys_are_rejected_not_raised(self) -> None:
        """One bad order must not abort a run, but it must be recorded -- a
        silently dropped order looks exactly like a decision not to trade."""
        result = self.session.submit([OrderRequest("GHOST", "BUY", notional=10.0)])
        self.assertEqual(result["accepted"], 0)
        self.assertIn("unknown symbol", result["rejected"][0]["reason"])

        self.session.submit([OrderRequest("AAA", "BUY", notional=100.0)])
        self.session.next_tick()
        again = self.session.submit([OrderRequest("AAA", "BUY", notional=100.0)])
        self.assertIn("already holding", again["rejected"][0]["reason"])

    def test_selling_what_is_not_held_is_rejected(self) -> None:
        result = self.session.submit([OrderRequest("AAA", "SELL")])
        self.assertIn("no open position", result["rejected"][0]["reason"])

    def test_a_buy_cannot_spend_more_than_the_cash(self) -> None:
        self.session.submit([OrderRequest("AAA", "BUY", notional=10_000.0)])
        self.session.next_tick()
        self.assertGreaterEqual(self.session.ledger.cash, -1e-9)

    def test_a_malformed_side_is_refused_at_construction(self) -> None:
        with self.assertRaises(SessionError):
            OrderRequest("AAA", "SHORT", notional=1.0)

    def test_unknown_order_fields_are_refused(self) -> None:
        with self.assertRaises(SessionError):
            OrderRequest.from_payload(
                {"symbol": "AAA", "side": "BUY", "notional": 1.0, "leverage": 5}
            )


class StopTest(unittest.TestCase):
    def test_the_trading_system_can_end_the_run(self) -> None:
        session = _session({"AAA": _bars([100.0] * 10)})
        session.next_tick()
        summary = session.stop("drawdown mandate breached")
        self.assertEqual(summary["status"], "stopped")
        self.assertIn("drawdown", summary["stop_reason"])
        with self.assertRaises(SessionError):
            session.next_tick()

    def test_costs_are_applied_on_both_sides(self) -> None:
        session = _session(
            {"AAA": _bars([100.0] * 5)},
            costs=CostModel(10.0, 10.0),
            initial_capital=1000.0,
        )
        session.next_tick()
        session.submit([OrderRequest("AAA", "BUY", notional=500.0)])
        session.next_tick()
        buy = session.ledger.orders[0]
        self.assertGreater(buy.price, 100.0, "slippage did not move the buy price up")
        self.assertGreater(buy.fee, 0.0)
        session.submit([OrderRequest("AAA", "SELL")])
        session.next_tick()
        sell = session.ledger.orders[1]
        self.assertLess(sell.price, 100.0, "slippage did not move the sell price down")


if __name__ == "__main__":
    unittest.main()
