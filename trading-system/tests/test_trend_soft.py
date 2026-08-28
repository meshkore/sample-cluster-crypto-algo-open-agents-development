"""`trend_soft`: turn the down-trend veto into a dimmer, so the flat years can be traded small.

The measured diagnosis this lever exists for: the strategy's worst calendar years are the
bear and sideways ones, and there the trend veto holds exposure at 1-9%. A defence of
"stay flat" bounds the worst year near zero by construction - it cannot lose much and it
cannot earn anything. Every lever tested before this one acts on trades the system chooses
to take, which is why none of them could move that year.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quantlab_system06.channels import Channels
from quantlab_system06.modules.base import MarketView
from quantlab_system06.modules.oracle_nn import OracleNN

NS = 1_700_000_000_000_000_000


def _view(up_aaa: bool, up_bbb: bool) -> MarketView:
    table = {
        "AAA": {"prob": {NS: 0.9}, "trend": {NS: 1 if up_aaa else 0}, "vol": {}, "mom": {},
                "hurst": {}, "feargreed": {}, "sweep": {}},
        "BBB": {"prob": {NS: 0.8}, "trend": {NS: 1 if up_bbb else 0}, "vol": {}, "mom": {},
                "hurst": {}, "feargreed": {}, "sweep": {}},
    }
    return MarketView(
        timestamp=datetime(2022, 6, 1, tzinfo=timezone.utc), ns=NS,
        candles={"AAA": {"close": 100.0}, "BBB": {"close": 50.0}},
        account={"equity": 10_000.0, "positions": {}},
        channels=Channels(table), held=set(), peaks={},
    )


def test_off_by_default_the_veto_is_unchanged():
    """Zero must reproduce the wall exactly, or every result on record moves."""
    out = OracleNN().evaluate(_view(up_aaa=True, up_bbb=False))
    assert out.votes["AAA"].veto is False and out.votes["AAA"].size_mult == 1.0
    assert out.votes["BBB"].veto is True
    assert out.votes["BBB"].size_mult == 1.0, "a vetoed name must not also be resized"


def test_a_soft_trend_admits_the_down_name_at_reduced_size():
    out = OracleNN(trend_soft=0.25).evaluate(_view(up_aaa=True, up_bbb=False))
    # The uptrend name is untouched...
    assert out.votes["AAA"].veto is False and out.votes["AAA"].size_mult == 1.0
    # ...while the downtrend name is now allowed in, but small.
    assert out.votes["BBB"].veto is False
    assert out.votes["BBB"].size_mult == pytest.approx(0.25)
    # Conviction is the model's own and must not be altered by the regime.
    assert out.votes["BBB"].conviction == pytest.approx(0.8)


def test_the_dimmer_can_never_exceed_full_size():
    """This lever exists to trade the flat years SMALL, never larger than an uptrend."""
    out = OracleNN(trend_soft=5.0).evaluate(_view(up_aaa=False, up_bbb=False))
    assert out.votes["AAA"].size_mult == 1.0
    assert OracleNN(trend_soft=-1.0).trend_soft == 0.0


def test_names_with_no_signal_are_still_abstained_on():
    table = {"AAA": {"prob": {NS: 0.0}, "trend": {NS: 0}, "vol": {}, "mom": {},
                     "hurst": {}, "feargreed": {}, "sweep": {}}}
    view = MarketView(
        timestamp=datetime(2022, 6, 1, tzinfo=timezone.utc), ns=NS,
        candles={"AAA": {"close": 1.0}}, account={"equity": 1.0, "positions": {}},
        channels=Channels(table), held=set(), peaks={})
    assert OracleNN(trend_soft=0.5).evaluate(view).votes == {}


def test_the_lever_reaches_the_brain_and_is_surfaced_only_when_active():
    """A lever the brain silently drops would read as INERT and waste GPU hours."""
    import inspect

    from quantlab_system06 import orchestrator, strategy

    assert "trend_soft" in inspect.signature(orchestrator.build_ensemble).parameters
    assert "trend_soft" in inspect.signature(strategy.OracleNetBrain.__init__).parameters

    from quantlab_system06.autoloop import MODULE_LEVERS, _row_to_kwargs
    assert "trend_soft" in MODULE_LEVERS, "the risk grid could not explore it otherwise"
    assert _row_to_kwargs({"trend_soft": 0.25}) == {"trend_soft": 0.25}
