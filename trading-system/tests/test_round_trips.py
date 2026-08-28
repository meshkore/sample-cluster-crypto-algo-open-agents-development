"""Per-trade P&L from the order ledger — the system could only see yearly aggregates before.

It matters because the RAW entry rule earns 111% of its gross profit from the top 1% of its
trades. Whether the FILTERED trades the champion actually takes are equally concentrated
decides whether scaling the book scales an edge or a lottery ticket, and that question
cannot be asked without pairing orders into round trips.
"""

from __future__ import annotations

import pytest

from quantlab_system06.launch import round_trips


def _order(symbol, side, notional, fee, stamp, reason="X"):
    return {"symbol": symbol, "side": side, "notional": notional, "fee": fee,
            "timestamp": stamp, "reason": reason}


def test_the_buy_fee_is_already_inside_notional_and_must_not_be_added_again():
    """The engine debits exactly `notional` on a buy - the fee is computed FROM it.

    session.py does `fee = notional * commission` then buys `(notional - fee) / fill`
    units, and ledger.record_buy does `cash -= notional`. Adding the fee on top
    understates every trade; it showed up as 2019 summing to a LOSS in money while the
    account returned +8.9%. A per-trade ledger that cannot reproduce the year it came
    from is measuring something else.
    """
    trips = round_trips([
        _order("AAA", "BUY", 100.0, 1.0, "t0"),
        _order("AAA", "SELL", 120.0, 1.2, "t1", "EXIT"),
    ])
    assert len(trips) == 1
    t = trips[0]
    # 100 left the account; 120 - 1.2 = 118.8 came back.
    assert t["cost"] == pytest.approx(100.0)
    assert t["proceeds"] == pytest.approx(118.8)
    # Values are stored rounded to 6 decimals, so compare at that precision rather
    # than approx's default relative tolerance, which is tighter than the rounding.
    assert t["net_pct"] == pytest.approx(0.188, abs=1e-6)
    assert t["pnl"] == pytest.approx(18.8)
    assert t["reason"] == "EXIT" and t["symbol"] == "AAA"


def test_a_position_still_open_at_the_end_is_not_a_result():
    """An unrealised mark is not a trade; counting it would flatter every measurement."""
    trips = round_trips([
        _order("AAA", "BUY", 100.0, 1.0, "t0"),
        _order("BBB", "BUY", 50.0, 0.5, "t1"),
        _order("AAA", "SELL", 90.0, 0.9, "t2"),
    ])
    assert [t["symbol"] for t in trips] == ["AAA"]
    assert trips[0]["net_pct"] < 0, "a losing round trip must read as a loss"


def test_symbols_are_paired_independently_and_in_order():
    trips = round_trips([
        _order("AAA", "BUY", 100.0, 0.0, "t0"),
        _order("BBB", "BUY", 200.0, 0.0, "t1"),
        _order("BBB", "SELL", 260.0, 0.0, "t2"),
        _order("AAA", "SELL", 110.0, 0.0, "t3"),
        _order("AAA", "BUY", 100.0, 0.0, "t4"),
        _order("AAA", "SELL", 95.0, 0.0, "t5"),
    ])
    assert [(t["symbol"], round(t["net_pct"], 4)) for t in trips] == [
        ("BBB", 0.30), ("AAA", 0.10), ("AAA", -0.05)]


def test_an_unmatched_sell_is_skipped_rather_than_crashing():
    """The runner reads years unattended; one odd ledger must not take it down."""
    trips = round_trips([
        _order("AAA", "SELL", 90.0, 0.0, "t0"),          # no recorded open
        _order("BBB", "BUY", 100.0, 0.0, "t1"),
        _order("BBB", "SELL", 105.0, 0.0, "t2"),
    ])
    assert [t["symbol"] for t in trips] == ["BBB"]


def test_zero_cost_orders_cannot_produce_infinite_returns():
    assert round_trips([
        _order("AAA", "BUY", 0.0, 0.0, "t0"),
        _order("AAA", "SELL", 5.0, 0.0, "t1"),
    ]) == []


def test_the_passthrough_is_off_by_default():
    """A year holds thousands of round trips and the autoloop writes every summary to
    the ledger, so this must never turn itself on."""
    import inspect

    from quantlab_system06 import launch

    for fn in (launch.run_window, launch.year_window):
        assert inspect.signature(fn).parameters["with_trades"].default is False
