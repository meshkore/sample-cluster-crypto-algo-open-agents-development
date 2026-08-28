"""Edge monitor: bank closed-trade outcomes, cut deploy only when they turn negative."""

from __future__ import annotations

from datetime import datetime, timezone

from quantlab_system06.channels import Channels
from quantlab_system06.modules.base import MarketView
from quantlab_system06.modules.edgemonitor import EdgeMonitor

CH = Channels({})


def _view(positions):
    """A bar where `positions` maps symbol -> unrealized return."""
    return MarketView(
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), ns=0,
        candles={s: {"close": 100.0} for s in positions},
        account={"equity": 100_000.0,
                 "positions": {s: {"unrealized_pct": r} for s, r in positions.items()}},
        channels=CH, held=set(positions), peaks={})


def _run(module, trades):
    """Open then close one position per trade outcome, returning the last output."""
    out = None
    for i, ret in enumerate(trades):
        symbol = f"S{i}"
        module.evaluate(_view({symbol: ret}))   # holding, at this return
        out = module.evaluate(_view({}))        # gone -> closed, outcome banked
    return out


def test_off_abstains():
    assert EdgeMonitor(edge_monitor=0.0).evaluate(_view({"A": -0.5})).deploy_mult is None


def test_silent_until_enough_trades():
    m = EdgeMonitor(edge_monitor=1.0, min_trades=15)
    out = _run(m, [-0.02] * 10)          # losing, but too few to judge
    assert out.deploy_mult is None


def test_winning_edge_leaves_deployment_alone():
    m = EdgeMonitor(edge_monitor=1.0, min_trades=15)
    out = _run(m, [0.01] * 20)
    assert out.deploy_mult is None


def test_losing_edge_cuts_deployment_and_respects_the_floor():
    m = EdgeMonitor(edge_monitor=1.0, min_trades=15, floor=0.25)
    out = _run(m, [-0.02] * 20)          # heavy losses -> full cut, bounded by the floor
    assert out.deploy_mult == 0.25
    assert "edge monitor" in out.note

    mild = EdgeMonitor(edge_monitor=1.0, min_trades=15, floor=0.25)
    out_mild = _run(mild, [-0.002] * 20)  # a small average loss -> a partial cut only
    assert 0.25 < out_mild.deploy_mult < 1.0


def test_strength_scales_the_cut():
    strong = _run(EdgeMonitor(edge_monitor=1.0, min_trades=15), [-0.01] * 20)
    weak = _run(EdgeMonitor(edge_monitor=0.5, min_trades=15), [-0.01] * 20)
    assert strong.deploy_mult < weak.deploy_mult < 1.0


def test_recovery_restores_full_deployment():
    m = EdgeMonitor(edge_monitor=1.0, window=20, min_trades=15)
    assert _run(m, [-0.02] * 20).deploy_mult == 0.25     # cut while losing
    out = _run(m, [0.02] * 20)                            # the window fills with winners
    assert out.deploy_mult is None                        # ... and the book is released


def test_reset_clears_history_between_years():
    m = EdgeMonitor(edge_monitor=1.0, min_trades=15)
    assert _run(m, [-0.02] * 20).deploy_mult == 0.25
    m.reset()
    assert _run(m, [-0.02] * 5).deploy_mult is None       # fresh account, no evidence yet
