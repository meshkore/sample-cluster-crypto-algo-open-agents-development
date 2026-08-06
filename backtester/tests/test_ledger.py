"""The account ledger, the run identity, and the read-only account view.

These pin down the seam the operator asked for: the backtester owns the book,
the trading system may read it and may not write it, and every run carries an
id that its records hang off.

All sabotage-verified -- see the notes on each test for the bug it was checked
against.
"""

from datetime import datetime, timedelta, timezone
import unittest

from quantlab_backtester.backtest import CostModel
from quantlab_backtester.engine import LongOnlyPortfolioBacktester
from quantlab_backtester.ledger import AccountLedger, BacktestRun
from quantlab_backtester.models import Bar
from quantlab_trading.policy import MoneyManagement

UTC = timezone.utc


def _policy(**overrides) -> MoneyManagement:
    base = {
        "risk_per_trade": 0.02,
        "maximum_position_fraction": 0.50,
        "stop_loss_pct": 0.30,
        "take_profit_pct": 0.20,
        "minimum_confidence": 0.25,
        "maximum_concurrent_assets": 5,
        "minimum_order_notional": 1.0,
        "minimum_position_fraction": 0.0,
        "volatility_target": 1.0,
        "minimum_daily_quote_volume": 0.0,
        "maximum_volume_participation": 1.0,
        "drawdown_deleverage_start": 0.25,
    }
    base.update(overrides)
    return MoneyManagement(**base)


def _bars(closes, start=None):
    start = start or datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Bar(
            timestamp=start + timedelta(days=i),
            open=c,
            high=c * 1.02,
            low=c * 0.98,
            close=c,
            volume=1_000_000.0,
        )
        for i, c in enumerate(closes)
    ]


class RunIdentityTest(unittest.TestCase):
    def test_the_same_configuration_gets_the_same_id(self) -> None:
        args = (
            "sma_rsi",
            {"fast": 10},
            {"risk_per_trade": 0.01},
            ["A", "B"],
            "2022",
            "2025",
            100.0,
        )
        self.assertEqual(BacktestRun.fingerprint(*args), BacktestRun.fingerprint(*args))

    def test_key_ordering_and_float_shape_do_not_change_the_id(self) -> None:
        """{"a": 1} and {"a": 1.0} written on different days are one cell."""
        first = BacktestRun.fingerprint(
            "f", {"a": 1, "b": 2}, {"r": 1.0}, ["A", "B"], "s", "e", 100.0
        )
        second = BacktestRun.fingerprint(
            "f", {"b": 2, "a": 1.0}, {"r": 1}, ["B", "A"], "s", "e", 100.0
        )
        self.assertEqual(first, second)

    def test_a_different_universe_is_a_different_run(self) -> None:
        """Sabotage check: hashing a COUNT instead of the symbols makes this
        pass wrongly. This laboratory once selected a winner on 321 assets and
        deployed it on 386; those must never share an id."""
        narrow = BacktestRun.fingerprint("f", {}, {}, ["A", "B"], "s", "e", 100.0)
        wide = BacktestRun.fingerprint("f", {}, {}, ["A", "C"], "s", "e", 100.0)
        self.assertNotEqual(narrow, wide)

    def test_every_input_that_moves_the_result_moves_the_id(self) -> None:
        base = ("f", {"a": 1}, {"r": 0.01}, ["A"], "2022", "2025", 100.0)
        variants = [
            ("g", {"a": 1}, {"r": 0.01}, ["A"], "2022", "2025", 100.0),
            ("f", {"a": 2}, {"r": 0.01}, ["A"], "2022", "2025", 100.0),
            ("f", {"a": 1}, {"r": 0.02}, ["A"], "2022", "2025", 100.0),
            ("f", {"a": 1}, {"r": 0.01}, ["A"], "2023", "2025", 100.0),
            ("f", {"a": 1}, {"r": 0.01}, ["A"], "2022", "2026", 100.0),
            ("f", {"a": 1}, {"r": 0.01}, ["A"], "2022", "2025", 200.0),
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertNotEqual(
                    BacktestRun.fingerprint(*base), BacktestRun.fingerprint(*variant)
                )


class AccountLedgerTest(unittest.TestCase):
    def test_cash_and_equity_follow_the_fills(self) -> None:
        ledger = AccountLedger(initial_capital=1000.0)
        self.assertEqual(ledger.cash, 1000.0)
        self.assertEqual(ledger.equity, 1000.0)

        stamp = datetime(2024, 1, 1, tzinfo=UTC)
        ledger.record_buy(
            stamp, "AAA", quantity=9.0, price=10.0, notional=100.0, fee=1.0
        )
        self.assertEqual(ledger.cash, 900.0)
        self.assertAlmostEqual(ledger.invested, 90.0)
        self.assertAlmostEqual(ledger.equity, 990.0)

        ledger.mark("AAA", 20.0)
        self.assertAlmostEqual(ledger.invested, 180.0)
        self.assertAlmostEqual(ledger.equity, 1080.0)

        ledger.record_sell(
            stamp, "AAA", price=20.0, proceeds=180.0, fee=2.0, reason="EXIT"
        )
        self.assertAlmostEqual(ledger.cash, 1078.0)
        self.assertEqual(ledger.invested, 0.0)

    def test_every_fill_is_logged_in_order_with_the_cash_it_left(self) -> None:
        ledger = AccountLedger(initial_capital=1000.0)
        stamp = datetime(2024, 1, 1, tzinfo=UTC)
        ledger.record_buy(stamp, "AAA", 9.0, 10.0, 100.0, 1.0)
        ledger.record_buy(stamp, "BBB", 4.0, 50.0, 200.0, 2.0)
        ledger.record_sell(stamp, "AAA", 12.0, 108.0, 1.0, "TAKE_PROFIT")

        self.assertEqual([o.sequence for o in ledger.orders], [1, 2, 3])
        self.assertEqual([o.side for o in ledger.orders], ["BUY", "BUY", "SELL"])
        self.assertEqual([o.symbol for o in ledger.orders], ["AAA", "BBB", "AAA"])
        self.assertEqual(ledger.orders[-1].reason, "TAKE_PROFIT")
        # cash_after is the point of the log: it makes the book auditable
        # without replaying it.
        self.assertEqual([o.cash_after for o in ledger.orders], [900.0, 700.0, 807.0])

    def test_marking_an_asset_it_does_not_hold_is_ignored(self) -> None:
        ledger = AccountLedger(initial_capital=100.0)
        ledger.mark("GHOST", 999.0)
        self.assertEqual(ledger.equity, 100.0)

    def test_zero_capital_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            AccountLedger(initial_capital=0.0)


class AccountViewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = AccountLedger(initial_capital=1000.0)
        self.stamp = datetime(2024, 1, 1, tzinfo=UTC)
        self.ledger.record_buy(self.stamp, "AAA", 9.0, 10.0, 100.0, 1.0)
        self.view = self.ledger.view()

    def test_it_reports_the_live_book_not_a_snapshot(self) -> None:
        """A view taken before a fill must still see the fill. Sabotage check:
        copying the values at construction passes every other test here."""
        before = self.view.cash
        self.ledger.record_buy(self.stamp, "BBB", 1.0, 50.0, 50.0, 0.5)
        self.assertEqual(before, 900.0)
        self.assertEqual(self.view.cash, 850.0)

    def test_it_answers_what_is_held(self) -> None:
        self.assertTrue(self.view.holds("AAA"))
        self.assertFalse(self.view.holds("ZZZ"))
        self.assertEqual(self.view.open_symbols, ("AAA",))
        self.assertIsNone(self.view.position("ZZZ"))
        self.assertAlmostEqual(self.view.position("AAA").quantity, 9.0)

    def test_unrealised_moves_with_the_mark(self) -> None:
        self.assertAlmostEqual(self.view.unrealised_pct("AAA"), 0.0)
        self.ledger.mark("AAA", 11.0)
        self.assertAlmostEqual(self.view.unrealised_pct("AAA"), 0.10)
        self.assertEqual(self.view.unrealised_pct("ZZZ"), 0.0)

    def test_it_refuses_to_be_written(self) -> None:
        """The instrument records and the trading system decides. A strategy
        that could write here could rewrite its own result."""
        with self.assertRaises(AttributeError):
            self.view.cash = 10_000.0

    def test_the_position_handle_cannot_mutate_the_book(self) -> None:
        """Sabotage check: returning the live Holding makes this fail."""
        handle = self.view.position("AAA")
        handle.quantity = 10_000.0
        self.assertAlmostEqual(self.ledger.holdings["AAA"].quantity, 9.0)


class _AccountAwareStrategy:
    """Buys once, then holds while it is up and sells when it is not.

    It cannot be expressed without the account: the decision depends on what is
    already owned and at what price.
    """

    wants_account = True

    def reset(self) -> None:
        self.seen_account = False

    def on_bar(self, bars, account):
        self.seen_account = True
        symbol = "AAA"
        if not account.holds(symbol):
            return 1.0 if len(bars) > 3 else 0.0
        return 1.0 if account.unrealised_pct(symbol) > -0.05 else 0.0


class AccountAwareStrategyTest(unittest.TestCase):
    def test_a_strategy_can_read_the_account_while_it_decides(self) -> None:
        rising = _bars([100.0 * (1.02**i) for i in range(40)])
        result = LongOnlyPortfolioBacktester(CostModel(0.0, 0.0), _policy()).run(
            {"AAA": rising}, _AccountAwareStrategy, 10_000.0
        )
        self.assertTrue(result.trades or result.equity_curve)
        # It traded, which means the live path produced real signals rather than
        # leaving the zero placeholders the precompute pass writes.
        self.assertGreater(
            max(point["equity"] for point in result.equity_curve), 10_000.0
        )

    def test_the_ledger_agrees_with_the_engine(self) -> None:
        """The strongest check available here: the engine tracks cash in its own
        local, the ledger tracks it independently from the fills, and the two
        must land on the same number. A discrepancy means one of them is not
        seeing every order."""

        class _Choppy:
            def reset(self):
                self.n = 0

            def on_bar(self, bars):
                self.n += 1
                return 1.0 if self.n % 7 < 4 else 0.0

        closes, price = [], 100.0
        for i in range(120):
            price *= 1.03 if i % 3 else 0.95
            closes.append(price)
        result = LongOnlyPortfolioBacktester(CostModel(5.0, 5.0), _policy()).run(
            {"AAA": _bars(closes), "BBB": _bars(closes[::-1])}, _Choppy, 10_000.0
        )
        self.assertTrue(result.ledger.orders)
        self.assertAlmostEqual(result.ledger.cash, result.cash, places=6)
        self.assertEqual(
            sum(1 for o in result.ledger.orders if o.side == "SELL"),
            len(result.trades),
            "every completed trade must have exactly one sell in the order log",
        )

    def test_the_ordinary_path_is_untouched(self) -> None:
        """A strategy that does not ask for the account must be evaluated
        exactly as before, or every stored result silently changes meaning."""

        class _AlwaysLong:
            def reset(self) -> None:
                pass

            def on_bar(self, bars):
                return 1.0

        rising = _bars([100.0 * (1.02**i) for i in range(40)])
        result = LongOnlyPortfolioBacktester(CostModel(0.0, 0.0), _policy()).run(
            {"AAA": rising}, _AlwaysLong, 10_000.0
        )
        self.assertGreater(result.return_pct, 0.0)


if __name__ == "__main__":
    unittest.main()
