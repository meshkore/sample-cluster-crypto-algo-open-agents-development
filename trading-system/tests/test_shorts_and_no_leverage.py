"""Shorts, unleveraged - and proof the long-only path did not move.

Operator, 2026-09-08: *"quiero uno completo que haga cortos tambien. no quiero
apalancamiento, porque nos expondremos a liquidaciones rapidas y caeremos en la trampa
de los brokers, donde queremos salir y no se puede por fallos de api, overloading, o
cola de ordenes."*

That is two requirements, and the second is the harder one. No leverage is not a
preference here, it is a way of removing an exit that somebody ELSE controls: a
liquidation is a forced close, at the worst possible moment, through an API that may
not answer. At gross exposure <= 1x a short would need roughly a 100% move against it
before a venue could touch it, which in practice means the only exit is ours.

The other half of this file matters just as much. The backtester is the frozen
instrument every system in this laboratory shares, and five systems' recorded results
must keep reproducing. So the long-only path is asserted to be UNCHANGED rather than
assumed to be - shorts arrive behind a flag that defaults to off, and the tests below
would fail if any of it leaked into the old behaviour.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from quantlab_backtester.ledger import AccountLedger, Holding


def _stamp(minutes: int = 0) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minutes)


def _ledger(capital: float = 10_000.0) -> AccountLedger:
    return AccountLedger(initial_capital=capital)


# --- the long-only path must be byte-identical ------------------------------------

def test_a_long_round_trip_is_unchanged():
    led = _ledger()
    led.record_buy(_stamp(), "BTCUSDT", quantity=0.1, price=100.0,
                   notional=1000.0, fee=1.0)
    assert led.cash == pytest.approx(9000.0)
    assert led.holdings["BTCUSDT"].quantity == pytest.approx(0.1)
    led.mark("BTCUSDT", 110.0)
    assert led.equity == pytest.approx(9000.0 + 11.0)

    led.record_sell(_stamp(1), "BTCUSDT", price=110.0, proceeds=11.0, fee=0.011,
                    reason="EXIT")
    assert "BTCUSDT" not in led.holdings
    assert led.cash == pytest.approx(9000.0 + 11.0 - 0.011)


def test_selling_without_a_quantity_still_closes_the_whole_long():
    """The pre-shorts signature. Every existing caller relies on this default."""
    led = _ledger()
    led.record_buy(_stamp(), "ETHUSDT", quantity=2.0, price=50.0,
                   notional=100.0, fee=0.0)
    order = led.record_sell(_stamp(1), "ETHUSDT", price=60.0, proceeds=120.0,
                            fee=0.0, reason="EXIT")
    assert order.quantity == pytest.approx(2.0)
    assert not led.holdings


# --- shorts -----------------------------------------------------------------------

def test_opening_a_short_takes_cash_in_and_leaves_equity_flat():
    led = _ledger()
    before = led.equity
    led.record_sell(_stamp(), "BTCUSDT", price=100.0, proceeds=1000.0, fee=0.0,
                    reason="SHORT", quantity=10.0)
    held = led.holdings["BTCUSDT"]
    assert held.is_short and held.quantity == pytest.approx(-10.0)
    assert led.cash == pytest.approx(11_000.0), "the sale proceeds are real cash"
    assert led.equity == pytest.approx(before), \
        "opening a position cannot create or destroy equity"


def test_a_short_gains_when_the_price_falls_and_loses_when_it_rises():
    led = _ledger()
    led.record_sell(_stamp(), "BTCUSDT", price=100.0, proceeds=1000.0, fee=0.0,
                    reason="SHORT", quantity=10.0)
    led.mark("BTCUSDT", 90.0)
    assert led.equity == pytest.approx(10_100.0), "a 10% fall on a $1,000 short = +$100"
    led.mark("BTCUSDT", 120.0)
    assert led.equity == pytest.approx(9_800.0), "a 20% rise = -$200"


def test_covering_a_short_closes_it_rather_than_averaging_into_it():
    """Buying against a short is a COVER. The add branch would produce nonsense."""
    led = _ledger()
    led.record_sell(_stamp(), "BTCUSDT", price=100.0, proceeds=1000.0, fee=0.0,
                    reason="SHORT", quantity=10.0)
    order = led.record_buy(_stamp(1), "BTCUSDT", quantity=10.0, price=90.0,
                           notional=900.0, fee=0.0)
    assert "BTCUSDT" not in led.holdings
    assert order.reason == "COVER"
    assert led.equity == pytest.approx(10_100.0)


def test_a_partial_cover_keeps_the_original_entry_clock():
    """Restarting entry time on a partial close would let a book re-arm its stops."""
    led = _ledger()
    led.record_sell(_stamp(), "BTCUSDT", price=100.0, proceeds=1000.0, fee=0.0,
                    reason="SHORT", quantity=10.0)
    opened = led.holdings["BTCUSDT"].entry_time
    led.record_buy(_stamp(30), "BTCUSDT", quantity=4.0, price=95.0,
                   notional=380.0, fee=0.0)
    held = led.holdings["BTCUSDT"]
    assert held.quantity == pytest.approx(-6.0)
    assert held.entry_time == opened
    assert held.entry_price == pytest.approx(100.0)


def test_adding_to_a_short_is_refused_loudly():
    led = _ledger()
    led.record_sell(_stamp(), "BTCUSDT", price=100.0, proceeds=1000.0, fee=0.0,
                    reason="SHORT", quantity=10.0)
    with pytest.raises(ValueError, match="already short"):
        led.record_sell(_stamp(1), "BTCUSDT", price=101.0, proceeds=500.0, fee=0.0,
                        reason="SHORT", quantity=5.0)


def test_a_short_with_no_quantity_is_refused():
    led = _ledger()
    with pytest.raises(ValueError, match="explicit positive quantity"):
        led.record_sell(_stamp(), "BTCUSDT", price=100.0, proceeds=1000.0, fee=0.0,
                        reason="SHORT")


# --- funding, whose SIGN is the whole argument ------------------------------------

def test_a_positive_funding_rate_pays_the_short_and_charges_the_long():
    """When funding is positive, longs pay shorts. Getting this backwards would
    reverse the economics of the entire short book - and A63 declined shorts on a
    funding argument whose sign was never written down."""
    short = _ledger()
    short.record_sell(_stamp(), "BTCUSDT", price=100.0, proceeds=1000.0, fee=0.0,
                      reason="SHORT", quantity=10.0)
    flow = short.accrue_funding(_stamp(1), "BTCUSDT", rate=0.0001)
    assert flow > 0, "a short RECEIVES funding when the rate is positive"
    assert flow == pytest.approx(1000.0 * 0.0001)

    long = _ledger()
    long.record_buy(_stamp(), "BTCUSDT", quantity=10.0, price=100.0,
                    notional=1000.0, fee=0.0)
    assert long.accrue_funding(_stamp(1), "BTCUSDT", rate=0.0001) == \
        pytest.approx(-1000.0 * 0.0001), "a long PAYS when the rate is positive"


def test_a_negative_funding_rate_reverses_both_sides():
    led = _ledger()
    led.record_sell(_stamp(), "BTCUSDT", price=100.0, proceeds=1000.0, fee=0.0,
                    reason="SHORT", quantity=10.0)
    assert led.accrue_funding(_stamp(1), "BTCUSDT", rate=-0.0002) < 0


def test_funding_on_a_flat_book_is_nothing():
    assert _ledger().accrue_funding(_stamp(), "BTCUSDT", rate=0.01) == 0.0


# --- the no-leverage invariant ----------------------------------------------------

def test_gross_exposure_counts_both_sides_rather_than_netting_them():
    """A book long one coin and short another has a small NET and two full positions
    of risk. Netting would let leverage in through the back door."""
    led = _ledger()
    led.record_buy(_stamp(), "BTCUSDT", quantity=10.0, price=100.0,
                   notional=1000.0, fee=0.0)
    led.record_sell(_stamp(), "ETHUSDT", price=100.0, proceeds=1000.0, fee=0.0,
                    reason="SHORT", quantity=10.0)
    assert led.invested == pytest.approx(0.0), "net exposure is zero"
    assert led.gross_invested == pytest.approx(2000.0), "gross is two positions"
    assert led.gross_exposure == pytest.approx(0.2)


def test_the_session_refuses_a_short_that_would_breach_the_limit():
    from quantlab_backtester.session import BacktestSession

    assert BacktestSession.__dataclass_fields__["allow_shorts"].default is False, \
        "shorts must be opt-in or five systems' recorded results change meaning"
    assert BacktestSession.__dataclass_fields__["max_gross_exposure"].default == 1.0, \
        "the no-leverage ceiling is 1x gross and is not a tuning knob"


# --- the exit we do NOT control ---------------------------------------------------
# Operator, 2026-09-08: "si tu confias en que cuando haya una caida fuerte vamos a poder
# salir de esos cortos o de esos largos, estas equivocado, porque en el momento en que
# lances la orden habra mil ordenes por delante de la tuya."
#
# Stops in this laboratory are evaluated on the CLOSE and filled at the next open, so a
# violent spike inside a bar that reverts before the close is invisible. For an
# unleveraged long that is optimistic but survivable. For a collateralised short it is
# ruin the record would never show. These tests exist so it shows.

class _Bar:
    def __init__(self, o, h, l, c, v=1e9):
        self.open, self.high, self.low, self.close, self.volume = o, h, l, c, v
        self.timestamp = _stamp()


def _short_session(**kw):
    """A one-symbol session already short, to exercise the forced-exit path."""
    from quantlab_backtester.session import BacktestSession
    sess = BacktestSession.__new__(BacktestSession)
    sess.allow_shorts = True
    sess.max_gross_exposure = kw.get("max_gross_exposure", 1.0)
    sess.short_stop = kw.get("short_stop", 0.0)
    sess.ledger = _ledger()
    sess.forced_exits = []

    class _Costs:
        commission_bps = 0.0
    sess.costs = _Costs()
    sess.ledger.record_sell(_stamp(), "BTCUSDT", price=100.0, proceeds=1000.0,
                            fee=0.0, reason="SHORT", quantity=10.0)
    return sess


def test_a_spike_that_reverts_before_the_close_still_kills_a_short():
    """The bar closes flat. The high went through the collateral. It is gone."""
    sess = _short_session(max_gross_exposure=1.0)
    bar = _Bar(o=101.0, h=205.0, l=99.0, c=100.0)   # +105% intrabar, closes at entry
    out = sess._force_close_blown_shorts(_stamp(1), {"BTCUSDT": bar})
    assert out, "the position survived a move that wiped its collateral"
    assert sess.forced_exits[0]["reason"] == "LIQUIDATION"
    assert "BTCUSDT" not in sess.ledger.holdings


def test_a_resting_stop_fires_inside_the_bar_rather_than_at_the_next_open():
    sess = _short_session(short_stop=0.05)
    bar = _Bar(o=101.0, h=120.0, l=100.0, c=100.5)
    sess._force_close_blown_shorts(_stamp(1), {"BTCUSDT": bar})
    exit_ = sess.forced_exits[0]
    assert exit_["reason"] == "STOP_GAP"
    assert exit_["fill"] == pytest.approx(105.0), "filled at the stop, not the close"


def test_a_gap_straight_through_the_stop_fills_where_the_market_actually_is():
    """The whole point. A stop at +5% is worth +5% only if price passes through it."""
    sess = _short_session(short_stop=0.05)
    bar = _Bar(o=140.0, h=150.0, l=139.0, c=145.0)   # opened 40% above entry
    sess._force_close_blown_shorts(_stamp(1), {"BTCUSDT": bar})
    exit_ = sess.forced_exits[0]
    assert exit_["fill"] == pytest.approx(140.0), \
        "a gap must fill at the open, not at the price we asked for"
    assert exit_["gapped"] is True


def test_a_quiet_bar_leaves_the_short_alone():
    sess = _short_session(short_stop=0.05)
    bar = _Bar(o=99.0, h=101.0, l=97.0, c=98.0)
    assert sess._force_close_blown_shorts(_stamp(1), {"BTCUSDT": bar}) == []
    assert sess.ledger.holdings["BTCUSDT"].is_short


def test_lower_leverage_survives_what_higher_leverage_does_not():
    """The operator's instruction, as arithmetic: 'si tenemos que apalancarnos en corto
    hagamos un apalancamiento muy bajo'."""
    spike = _Bar(o=101.0, h=160.0, l=99.0, c=100.0)      # +60% intrabar
    hot = _short_session(max_gross_exposure=1.5)          # ruin at ~+67%... survives
    cold = _short_session(max_gross_exposure=2.0)         # ruin at +50% ... does not
    assert hot._force_close_blown_shorts(_stamp(1), {"BTCUSDT": spike}) == []
    assert cold._force_close_blown_shorts(_stamp(1), {"BTCUSDT": spike}) != []


def test_longs_are_untouched_by_any_of_this():
    sess = _short_session()
    sess.ledger.holdings.clear()
    sess.ledger.record_buy(_stamp(), "ETHUSDT", quantity=10.0, price=100.0,
                           notional=1000.0, fee=0.0)
    crash = _Bar(o=60.0, h=101.0, l=40.0, c=95.0)        # -60% intrabar, recovers
    assert sess._force_close_blown_shorts(_stamp(1), {"ETHUSDT": crash}) == []
    assert "ETHUSDT" in sess.ledger.holdings, (
        "an unleveraged long survives the spike - that asymmetry is the reason "
        "shorts need their own machinery")
