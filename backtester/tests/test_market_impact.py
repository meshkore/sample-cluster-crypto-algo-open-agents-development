"""Size-dependent slippage: our own order moves the price.

Operator, 2026-09-02: *"no podemos comprar cien mil dólares de una sola cripto - bueno,
en Bitcoin a lo mejor sí - pero muchas de las otras, nuestro propio volumen alteraría
las cifras"*. Exactly right, and the flat slippage the engine charged said the opposite.
This is the shared engine, so the rule lands on every strategy at once.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from quantlab_backtester.backtest import CostModel
from quantlab_backtester.ledger import BacktestRun
from quantlab_backtester.models import Bar
from quantlab_backtester.session import BacktestSession, OrderRequest


def _bars(volume, n=4, price=100.0):
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return {"ALTUSDT": [Bar(timestamp=t0 + timedelta(minutes=15 * i), open=price,
                            high=price * 1.01, low=price * 0.99, close=price,
                            volume=volume) for i in range(n)]}


def _session(costs, volume):
    bars = _bars(volume)
    run = BacktestRun(backtest_id="t", label="t", created_at=datetime.now(timezone.utc),
                      initial_capital=1_000_000.0, strategy_family="t",
                      strategy_params={}, policy={}, universe_size=1,
                      window_start=bars["ALTUSDT"][0].timestamp.isoformat(),
                      window_end=bars["ALTUSDT"][-1].timestamp.isoformat())
    return BacktestSession(run=run, bars_by_symbol=bars, costs=costs)


def _buy(session, notional):
    session.next_tick()
    session.submit([OrderRequest(symbol="ALTUSDT", side="BUY", notional=notional)], "")
    session.next_tick()
    return session.ledger.orders[-1].document()


def test_the_default_charges_no_impact_so_every_old_result_reproduces():
    """A shared engine change that moved existing numbers would invalidate the whole
    ledger of this project. Impact is opt-in; off, the fill is the flat one."""
    d = _buy(_session(CostModel(10.0, 5.0), volume=1_000.0), 100_000.0)
    assert d["price"] == pytest.approx(100.0 * (1 + 5.0 / 10_000))


def test_impact_grows_with_participation_by_the_square_root_law():
    """1% of the bar costs a tenth of the full-bar impact, not a hundredth and not
    all of it - sqrt(0.01) = 0.1. The shape is the whole point: it penalises size
    steeply at first and then flattens, which is what a real book does."""
    c = CostModel(10.0, 5.0, impact_bps=100.0)
    traded = 1_000_000.0
    assert c.slippage_for(traded * 0.01, traded) == pytest.approx(5.0 + 10.0)
    assert c.slippage_for(traded * 0.25, traded) == pytest.approx(5.0 + 50.0)
    assert c.slippage_for(traded, traded) == pytest.approx(5.0 + 100.0)
    # And it cannot run away past the whole bar.
    assert c.slippage_for(traded * 9, traded) == pytest.approx(5.0 + 100.0)


def test_the_same_order_costs_more_in_a_thin_market_than_in_a_deep_one():
    """The operator's exact framing: $100k is nothing in BTC and a bulldozer in an
    illiquid alt. One number, two markets, two prices."""
    costs = CostModel(10.0, 5.0, impact_bps=100.0)
    deep = _buy(_session(costs, volume=1_000_000.0), 100_000.0)   # $100M bar
    thin = _buy(_session(costs, volume=2_000.0), 100_000.0)       # $200k bar
    assert thin["price"] > deep["price"] * 1.001
    # Deep book: 0.1% participation -> ~3.2 extra bps. Thin: 50% -> ~70.7 extra.
    assert deep["price"] == pytest.approx(100.0 * (1 + (5 + 100 * math.sqrt(0.001)) / 10_000))
    assert thin["price"] == pytest.approx(100.0 * (1 + (5 + 100 * math.sqrt(0.5)) / 10_000))


def test_exits_pay_impact_too():
    """A stop fires in the thin, fast bar where the book is thinnest - charging impact
    on entries only would flatter exactly the trades that hurt most in reality."""
    costs = CostModel(10.0, 5.0, impact_bps=100.0)
    s = _session(costs, volume=2_000.0)
    _buy(s, 50_000.0)
    s.submit([OrderRequest(symbol="ALTUSDT", side="SELL")], "")
    s.next_tick()
    sell = [o.document() for o in s.ledger.orders if o.document()["side"] == "SELL"][-1]
    assert sell["price"] < 100.0 * (1 - 5.0 / 10_000), "the exit paid more than the flat spread"


def test_a_feed_without_volume_falls_back_to_the_flat_spread():
    """Unknown liquidity must not price as free NOR as infinite - a missing field is
    a missing measurement, and the honest default is the behaviour we had before."""
    c = CostModel(10.0, 5.0, impact_bps=100.0)
    assert c.slippage_for(100_000.0, 0.0) == pytest.approx(5.0)
    assert c.slippage_for(0.0, 1_000_000.0) == pytest.approx(5.0)
