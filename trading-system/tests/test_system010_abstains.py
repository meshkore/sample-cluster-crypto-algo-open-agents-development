"""An untrained system 10 does not trade: a full research year, zero orders.

System 10 is registered before it has a policy, so it is reachable from every place a
brain can be named - the manager, the autotest runner, an engine package. The one thing
that makes that safe is the abstain branch in `ConditionedPolicyBrain.decide`. This test
drives it over a real research year through the same `BacktestSession` the server uses
and demands that the book end exactly where it started. If a later task wires half a
policy in and forgets the `trained` guard, this is where it shows up - not in a ledger.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "trading-system/backtester/data"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
YEAR = 2025


def test_the_brain_registers_and_says_it_is_untrained():
    from quantlab_core import brains
    import system010_conditioned_rl  # noqa: F401 -- registers the brain

    assert "system10-conditioned-rl" in {b["name"] for b in brains.available()}
    brain = brains.get("system10-conditioned-rl").build()
    assert brain.parameters()["trained"] is False


@pytest.mark.skipif(not DATA.is_dir(), reason="no candles on this machine")
def test_a_research_year_places_zero_trades():
    from quantlab_backtester.backtest import CostModel
    from quantlab_backtester.ledger import BacktestRun
    from quantlab_backtester.models import utc_now
    from quantlab_backtester.session import BacktestSession, OrderRequest
    from quantlab_catalog.candles import research
    from system010_conditioned_rl import ConditionedPolicyBrain

    start = datetime(YEAR, 1, 1, tzinfo=timezone.utc)
    end = datetime(YEAR, 12, 31, 23, 59, tzinfo=timezone.utc)
    bars = {s: [b for b in series if start <= b.timestamp <= end]
            for s, series in research(SYMBOLS).items()}
    bars = {s: series for s, series in bars.items() if len(series) >= 2}
    if not bars:
        pytest.skip(f"no {YEAR} candles for {SYMBOLS} on this machine")

    brain = ConditionedPolicyBrain()
    capital = 100_000.0
    run = BacktestRun(
        backtest_id=BacktestRun.fingerprint(
            "system10-conditioned-rl", brain.parameters(), {},
            BacktestRun.universe_digest(bars), start.isoformat(), end.isoformat(), capital),
        label="system10-dry", created_at=utc_now(), initial_capital=capital,
        strategy_family="system10-conditioned-rl", strategy_params=brain.parameters(),
        policy={}, universe_size=len(bars),
        window_start=start.isoformat(), window_end=end.isoformat(),
    )
    session = BacktestSession(run=run, bars_by_symbol=bars,
                              costs=CostModel(10.0, 5.0, impact_bps=60.0))
    ticks = 0
    while True:
        tick = session.next_tick()
        if tick.get("done"):
            break
        ticks += 1
        decision = brain.decide(tick)
        assert not decision.orders
        session.submit([OrderRequest.from_payload(o) for o in decision.orders], decision.note)

    assert ticks > 30_000, f"only {ticks} bars served - the year did not load"
    assert not session.ledger.orders
    assert session.ledger.equity == pytest.approx(capital, abs=1e-9)
