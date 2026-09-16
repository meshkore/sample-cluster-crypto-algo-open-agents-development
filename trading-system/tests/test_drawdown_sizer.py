"""Size from the distance to the drawdown limit - a taper instead of a cliff.

The measured reason this exists: P09 found that raising the deployment ceiling collapses
above 0.50 not because the market punishes size but because the hard abort forfeits 2021,
a year worth 227 points more than the alternative. Grossman-Zhou's answer to growth under
a maximum-drawdown constraint is to invest in proportion to the excess above a moving
floor, which in this book's terms is headroom = 1 - dd / mandate.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from system006_oracle_net_15m.channels import Channels
from system006_oracle_net_15m.modules.base import MarketView
from system006_oracle_net_15m.modules.drawdown import DrawdownSizer


def _view(equity: float) -> MarketView:
    return MarketView(
        timestamp=datetime(2021, 6, 1, tzinfo=timezone.utc), ns=1,
        candles={"AAA": {"close": 1.0}},
        account={"equity": equity, "positions": {}},
        channels=Channels({"AAA": {"prob": {}, "trend": {}, "vol": {}, "mom": {},
                                   "hurst": {}, "feargreed": {}, "sweep": {}}}),
        held=set(), peaks={})


def test_off_by_default():
    assert DrawdownSizer().evaluate(_view(100.0)).deploy_mult is None


def test_full_size_at_a_new_high_and_tapering_as_the_limit_nears():
    m = DrawdownSizer(dd_sizer=1.0, max_drawdown=0.25)
    assert m.evaluate(_view(100.0)).deploy_mult == pytest.approx(1.0)
    # Down 5% of a 25% mandate: one fifth of the headroom is gone.
    assert m.evaluate(_view(95.0)).deploy_mult == pytest.approx(0.8, abs=1e-6)
    # Down 12.5%: exactly half way to the limit.
    assert m.evaluate(_view(87.5)).deploy_mult == pytest.approx(0.5, abs=1e-6)


def test_the_floor_stops_it_reaching_zero_at_the_limit():
    """The orchestrator floors deploy at 0.05 anyway, so this module tapers - it cannot
    flatten the book. The abort remains the only thing that fully stops trading."""
    m = DrawdownSizer(dd_sizer=1.0, max_drawdown=0.25, floor_mult=0.10)
    m.evaluate(_view(100.0))
    assert m.evaluate(_view(75.0)).deploy_mult == pytest.approx(0.10)   # at the limit
    assert m.evaluate(_view(60.0)).deploy_mult == pytest.approx(0.10)   # past it


def test_size_is_RESTORED_as_the_account_recovers():
    """The point of a taper over an abort: an abort never comes back within the year."""
    m = DrawdownSizer(dd_sizer=1.0, max_drawdown=0.25)
    m.evaluate(_view(100.0))
    deep = m.evaluate(_view(80.0)).deploy_mult
    back = m.evaluate(_view(95.0)).deploy_mult
    assert deep < back < 1.0
    # ...but the high-water mark does not fall, so recovery is measured from the peak.
    assert back == pytest.approx(0.8, abs=1e-6)


def test_power_shapes_the_taper_and_a_higher_power_cuts_earlier():
    half = _view(87.5)   # half way to the limit
    for m in (DrawdownSizer(dd_sizer=1.0, max_drawdown=0.25),
              DrawdownSizer(dd_sizer=2.0, max_drawdown=0.25)):
        m.evaluate(_view(100.0))
    gentle = DrawdownSizer(dd_sizer=1.0, max_drawdown=0.25)
    gentle.evaluate(_view(100.0))
    sharp = DrawdownSizer(dd_sizer=2.0, max_drawdown=0.25)
    sharp.evaluate(_view(100.0))
    assert sharp.evaluate(half).deploy_mult < gentle.evaluate(half).deploy_mult


def test_reset_clears_the_high_water_mark_between_independent_years():
    """Each calendar year is its own account with its own mandate; a peak carried across
    them would taper a fresh year for a fall that happened in a previous one."""
    m = DrawdownSizer(dd_sizer=1.0, max_drawdown=0.25)
    m.evaluate(_view(200.0))
    assert m.evaluate(_view(100.0)).deploy_mult == pytest.approx(0.10)  # deep vs old peak
    m.reset()
    assert m.evaluate(_view(100.0)).deploy_mult == pytest.approx(1.0)   # a fresh account


def test_the_lever_reaches_the_brain():
    import inspect

    from system006_oracle_net_15m import orchestrator, strategy
    from system006_oracle_net_15m.autoloop import MODULE_LEVERS

    assert "dd_sizer" in inspect.signature(orchestrator.build_ensemble).parameters
    assert "dd_sizer" in inspect.signature(strategy.OracleNetBrain.__init__).parameters
    assert "dd_sizer" in MODULE_LEVERS
