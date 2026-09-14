"""V0 as a test, because a conservation law nobody runs is a comment.

System 09's whole claim to be more than a simulation with opinions is that its books balance
at every step - across fourteen assets, one shared cash pool, a population that changes size,
and eight and a half years. These tests are deliberately cheap: a synthetic ledger, then one
short slice of the real record. The expensive validation (V2 anchor recovery over the whole
history) lives in `quantlab_system09.phase1`.
"""

from __future__ import annotations

import pytest

from quantlab_system09 import cohorts as C
from quantlab_system09.ledger import Agent, ConservationError, Ledger

BTC, ETH = "BTCUSDT", "ETHUSDT"


def _tiny() -> Ledger:
    return Ledger([Agent("a", "x", coins={BTC: 10.0}, basis_cost={BTC: 500.0}, cash=1000.0),
                   Agent("b", "y", coins={BTC: 5.0}, basis_cost={BTC: 250.0}, cash=500.0),
                   Agent("venue", C.VENUE)], check_every=True)


def test_a_trade_changes_no_total():
    """The correction at the heart of the design: trades redistribute, they never create."""
    led = _tiny()
    units, cash = led.total_coins[BTC], led.total_cash
    led.settle(BTC, {"a": -2.0, "b": +2.0}, price=100.0)
    assert led.total_coins[BTC] == pytest.approx(units)
    assert led.total_cash == pytest.approx(cash)
    assert led.agents[0].held(BTC) == pytest.approx(8.0)
    assert led.agents[0].cash == pytest.approx(1200.0)
    assert led.agents[1].cash == pytest.approx(300.0)


def test_one_sided_deltas_are_refused():
    """A caller that writes only one leg of a transfer is inventing units."""
    led = _tiny()
    with pytest.raises(ConservationError):
        led.settle(BTC, {"a": -2.0, "b": +3.0}, price=100.0)


def test_cash_is_shared_across_assets():
    """The point of one wallet: dollars spent on one asset are gone from the other.

    This is the invented liquidity the single-asset version had, written as a test so it
    cannot come back.
    """
    led = _tiny()
    led.agents[0].coins[ETH] = 0.0
    led.agents[1].coins[ETH] = 100.0
    led.total_coins[ETH] = 100.0
    led.settle(ETH, {"a": +50.0, "b": -50.0}, price=20.0)     # a spends 1000 of its 1000
    assert led.agents[0].cash == pytest.approx(0.0)
    with pytest.raises(ConservationError):
        led.settle(BTC, {"a": +1.0, "b": -1.0}, price=100.0)  # and now cannot buy at all


def test_fees_move_to_the_venue_rather_than_vanishing():
    led = _tiny()
    cash = led.total_cash
    led.settle(BTC, {"a": -1.0, "b": +1.0}, price=100.0, fees={"b": 4.0}, fee_to="venue")
    assert led.total_cash == pytest.approx(cash)
    assert led.agents[2].cash == pytest.approx(4.0)


def test_only_the_boundary_moves_a_total():
    led = _tiny()
    led.issue(BTC, 1.0, "a")
    assert led.total_coins[BTC] == pytest.approx(16.0)
    led.mint(250.0, "b")
    assert led.total_cash == pytest.approx(1750.0)
    burned = led.burn(1e9, "b")
    assert burned == pytest.approx(750.0)          # capped by what was actually held
    assert led.total_cash == pytest.approx(1000.0)
    led.check("boundary")


def test_funding_nets_to_zero_between_longs_and_shorts():
    led = _tiny()
    cash = led.total_cash
    led.perp_settle(BTC, {"a": +3.0, "b": -3.0})
    led.perp_funding(BTC, 0.001, price=100.0)
    assert led.total_cash == pytest.approx(cash)
    assert led.agents[0].cash < 1000.0       # the long paid
    assert led.agents[1].cash > 500.0        # the short was paid


def test_a_negative_stock_is_refused():
    led = Ledger([Agent("a", "x", coins={BTC: 1.0}, cash=10.0),
                  Agent("b", "y", coins={BTC: 1.0}, cash=10.0)], check_every=True)
    with pytest.raises(ConservationError):
        led.settle(BTC, {"a": +1.0, "b": -1.0}, price=1000.0)   # a cannot pay for it


def test_retiring_a_player_conserves_its_book():
    """A participant that stops trading has not destroyed its coins - somebody holds them."""
    led = _tiny()
    units, cash = led.total_coins[BTC], led.total_cash
    led.amalgamate("a", "b", "2020-01-01")
    assert led.agents[0].retired == "2020-01-01"
    assert not led.agents[0].active
    assert led.agents[1].held(BTC) == pytest.approx(15.0)
    assert led.total_coins[BTC] == pytest.approx(units)
    assert led.total_cash == pytest.approx(cash)
    led.check("after retirement")


def test_admitting_a_player_is_a_boundary_claim():
    """Adding an agent with stocks raises the totals, so it cannot be done by accident."""
    led = _tiny()
    led.add(Agent("c", "z", coins={BTC: 2.0}, cash=99.0))
    assert led.total_coins[BTC] == pytest.approx(17.0)
    assert led.total_cash == pytest.approx(1599.0)
    led.check("after admission")


def test_the_opening_population_is_empty():
    """Nothing is handed out by a constructor: every unit and dollar has a boundary event."""
    ranks = {BTC: 0, ETH: 1}
    agents = C.opening_population("2017-08-17", ranks)
    led = Ledger(agents, check_every=True)
    assert led.total_cash == 0.0
    assert not led.total_coins
    assert all(a.affinity and BTC in a.affinity for a in agents if a.cohort in C.TRADING)
    led.check("opening")


def test_the_crowd_is_the_right_way_up():
    """The pyramid the first version had upside down: retail is the most numerous class,
    market makers the least, and institutions are few."""
    from collections import Counter
    ranks = {BTC: 0, ETH: 1}
    agents = C.opening_population("2017-08-17", ranks, scale=1.0)
    n = Counter(a.segment for a in agents)
    assert n["retail"] > n["whales"] > n["institutional"] > n["market_makers"], (
        f"the population is not the real shape: {dict(n)}")
    assert n["retail"] > 3 * n["whales"], "retail must dominate the headcount"


def test_an_agent_stands_for_many_people():
    """An agent is a profile group, and the class totals must match the stated real-world
    counts - otherwise the dashboard reports model buckets as if they were humans."""
    ranks = {BTC: 0, ETH: 1}
    agents = C.opening_population("2017-08-17", ranks, scale=1.0)
    rep: dict[str, int] = {}
    for a in agents:
        rep[a.segment] = rep.get(a.segment, 0) + a.represents
    for klass, want in C.REPRESENTS.items():
        assert rep.get(klass, 0) == pytest.approx(want, rel=0.01), (
            f"{klass} stands for {rep.get(klass)} against a stated {want}")
    assert rep["retail"] > rep["whales"] > rep["institutional"] > rep["market_makers"]


def test_a_real_slice_keeps_its_books():
    """A month of the real record, three assets, invariant checked at every daily close."""
    cat = pytest.importorskip("quantlab_catalog")
    from quantlab_system09 import buckets
    from quantlab_system09.boundary import Boundary, day_range
    from quantlab_system09.reconstruct import Reconstruction

    syms = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    raw = cat.research(syms)
    tapes = {}
    for s in syms:
        bars = buckets.window(raw.get(s, []), "2024-03-01", "2024-04-01")
        if bars:
            tapes[s] = buckets.build(bars, buckets.sizing(bars, 6), symbol=s)
    if len(tapes) < 2:
        pytest.skip("candles are not on this machine")
    bnd = Boundary(day_range("2024-03-01", "2024-03-31"),
                   {s: t[0].day for s, t in tapes.items()})
    rec = Reconstruction(tapes, boundary=bnd, funding={}, check_daily=True)
    traj = rec.run(until="2024-03-31")
    assert traj.buckets > 100
    assert traj.shortfall_events == 0
    assert traj.overall_fill > 0.80
    rec.ledger.check("end of the real slice")
