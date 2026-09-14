"""V0 as a test, because a conservation law nobody runs is a comment.

System 09's whole claim to be more than a simulation with opinions is that its books
balance at every step. These tests are deliberately cheap - a synthetic ledger, then one
short real window - so they run in the ordinary suite rather than in a nightly job nobody
watches. The expensive validation (V2 anchor recovery) lives in `quantlab_system09.mvp`.
"""

from __future__ import annotations

import pytest

from quantlab_system09 import cohorts as C
from quantlab_system09.ledger import Agent, ConservationError, Ledger


def _tiny() -> Ledger:
    return Ledger([Agent("a", "x", coins=10.0, cash=1000.0),
                   Agent("b", "y", coins=5.0, cash=500.0),
                   Agent("venue", C.VENUE)], check_every=True)


def test_a_trade_changes_no_total():
    """The correction at the heart of the design: trades redistribute, they never create."""
    led = _tiny()
    coins, cash = led.total_coins, led.total_cash
    led.settle({"a": -2.0, "b": +2.0}, price=100.0)
    assert led.total_coins == pytest.approx(coins)
    assert led.total_cash == pytest.approx(cash)
    assert led.agents[0].coins == pytest.approx(8.0)
    assert led.agents[0].cash == pytest.approx(1200.0)
    assert led.agents[1].cash == pytest.approx(300.0)


def test_one_sided_deltas_are_refused():
    """A caller that writes only one leg of a transfer is inventing coins."""
    led = _tiny()
    with pytest.raises(ConservationError):
        led.settle({"a": -2.0, "b": +3.0}, price=100.0)


def test_fees_move_to_the_venue_rather_than_vanishing():
    led = _tiny()
    cash = led.total_cash
    led.settle({"a": -1.0, "b": +1.0}, price=100.0, fees={"b": 4.0}, fee_to="venue")
    assert led.total_cash == pytest.approx(cash)
    assert led.agents[2].cash == pytest.approx(4.0)


def test_only_the_boundary_moves_a_total():
    led = _tiny()
    led.issue(1.0, "a")
    assert led.total_coins == pytest.approx(16.0)
    led.mint(250.0, "b")
    assert led.total_cash == pytest.approx(1750.0)
    burned = led.burn(1e9, "b")
    assert burned == pytest.approx(750.0)          # capped by what was actually held
    assert led.total_cash == pytest.approx(1000.0)
    led.check("boundary")


def test_funding_nets_to_zero_between_longs_and_shorts():
    led = _tiny()
    cash = led.total_cash
    led.perp_settle({"a": +3.0, "b": -3.0})
    led.perp_funding(0.001, price=100.0)
    assert led.total_cash == pytest.approx(cash)
    assert sum(x.cash for x in led.agents) == pytest.approx(cash)
    assert led.agents[0].cash < 1000.0       # the long paid
    assert led.agents[1].cash > 500.0        # the short was paid


def test_a_negative_stock_is_refused():
    led = Ledger([Agent("a", "x", coins=1.0, cash=10.0),
                  Agent("b", "y", coins=1.0, cash=10.0)], check_every=True)
    with pytest.raises(ConservationError):
        led.settle({"a": +1.0, "b": -1.0}, price=1000.0)   # a cannot pay for it


def test_the_population_matches_the_observed_totals():
    """An agent population that invents its own totals breaks V0 before the first bucket."""
    agents = C.build_population(19_500_000.0, 1.5e11, 60_000.0)
    led = Ledger(agents, check_every=True)
    assert led.total_coins == pytest.approx(19_500_000.0)
    assert led.total_cash == pytest.approx(1.5e11)
    assert len(agents) == len(C.TRADING) * C.LADDER + 2 * C.LADDER + 2
    led.check("population")


def test_a_real_window_keeps_its_books():
    """One real month of tape through the whole pipeline, with the invariant on every step."""
    cat = pytest.importorskip("quantlab_catalog")
    from quantlab_system09 import boundary as B, buckets, reconstruct as R

    bars = buckets.window(cat.research(["BTCUSDT"])["BTCUSDT"], "2024-03-01", "2024-04-01")
    if not bars:
        pytest.skip("BTCUSDT candles are not on this machine")
    bkts = buckets.build(bars, buckets.sizing(bars, 8.0))
    rec = R.Reconstruction(bkts, boundary=B.Boundary(use_etf=True, cash_share=False),
                           funding=cat.funding("BTCUSDT"), check_every=True)
    traj = rec.run()
    assert traj.buckets > 100
    assert traj.shortfall_events == 0
    assert traj.overall_fill > 0.90
    rec.ledger.check("end of the real window")
