"""Adding to an open position: off by default, correct when switched on.

Two system-06 experiments were silently voided because the engine rejected every
BUY on a held symbol while the strategy believed it was pyramiding - 378 orders
fired in one year with no effect on the result. The behaviour is now a choice a
session makes, and these tests pin both sides of it.
"""
from datetime import datetime, timedelta, timezone

import pytest

from quantlab_backtester.ledger import AccountLedger


def _stamp(i=0):
    return datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)


def test_a_second_buy_accumulates_quantity_and_averages_the_cost():
    led = AccountLedger(initial_capital=10_000.0, cash=10_000.0)
    led.record_buy(_stamp(0), "BTCUSDT", quantity=1.0, price=100.0, notional=100.0, fee=0.0)
    led.record_buy(_stamp(5), "BTCUSDT", quantity=1.0, price=200.0, notional=200.0, fee=0.0)
    h = led.holdings["BTCUSDT"]
    assert h.quantity == pytest.approx(2.0)
    assert h.invested == pytest.approx(300.0)
    assert h.entry_price == pytest.approx(150.0), "cost basis must be the weighted average"


def test_the_original_entry_time_survives_an_add():
    """A strategy's minimum-hold and trailing-stop clocks measure the POSITION. If an
    add reset the entry time, a book could re-arm its own stops by buying more."""
    led = AccountLedger(initial_capital=10_000.0, cash=10_000.0)
    led.record_buy(_stamp(0), "BTCUSDT", 1.0, 100.0, 100.0, 0.0)
    led.record_buy(_stamp(9), "BTCUSDT", 1.0, 120.0, 120.0, 0.0)
    assert led.holdings["BTCUSDT"].entry_time == _stamp(0)


def test_cash_is_debited_for_every_tranche():
    led = AccountLedger(initial_capital=1_000.0, cash=1_000.0)
    led.record_buy(_stamp(0), "BTCUSDT", 1.0, 100.0, 100.0, 0.0)
    led.record_buy(_stamp(1), "BTCUSDT", 1.0, 100.0, 100.0, 0.0)
    assert led.cash == pytest.approx(800.0)


def test_selling_closes_the_whole_accumulated_position():
    led = AccountLedger(initial_capital=1_000.0, cash=1_000.0)
    led.record_buy(_stamp(0), "BTCUSDT", 1.0, 100.0, 100.0, 0.0)
    led.record_buy(_stamp(1), "BTCUSDT", 2.0, 100.0, 200.0, 0.0)
    led.record_sell(_stamp(2), "BTCUSDT", price=150.0, proceeds=450.0, fee=0.0, reason="EXIT")
    assert "BTCUSDT" not in led.holdings
    assert led.cash == pytest.approx(1150.0)


def test_a_session_refuses_adds_unless_it_opts_in():
    import inspect

    from quantlab_backtester.session import BacktestSession
    fields = inspect.signature(BacktestSession).parameters
    assert "allow_adds" in fields
    assert fields["allow_adds"].default is False, (
        "every system written before this change must keep its exact behaviour")
    src = inspect.getsource(BacktestSession._why_not)
    assert "not self.allow_adds" in src
