"""Money management: Kelly sizes by edge; anti-martingale presses winners, retreats in losses."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from system006_oracle_net_15m.channels import Channels
from system006_oracle_net_15m.modules.base import MarketView
from system006_oracle_net_15m.modules.money import Money


def _view(channels, ns=10, equity=100_000.0, symbols=("AAA",)):
    return MarketView(timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), ns=ns,
                      candles={s: {"close": 100.0} for s in symbols},
                      account={"equity": equity, "positions": {}}, channels=channels,
                      held=set(), peaks={})


def test_kelly_sizes_by_edge():
    table = {s: {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "meta": {10: e}}
             for s, e in [("HI", 0.04), ("MID", 0.02), ("LO", 0.01)]}
    ch = Channels(table)
    out = Money(kelly=1.0, kelly_ref=0.02, kelly_lo=0.5, kelly_hi=1.6).evaluate(
        _view(ch, symbols=["HI", "MID", "LO"]))
    assert out.votes["HI"].size_mult == pytest.approx(1.6)    # 2x edge -> capped up
    assert out.votes["MID"].size_mult == pytest.approx(1.0)   # reference edge -> neutral
    assert out.votes["LO"].size_mult == pytest.approx(0.5)    # half edge -> floored down


def test_off_by_default_abstains():
    ch = Channels({"AAA": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "meta": {10: 0.05}}})
    out = Money().evaluate(_view(ch))
    assert out.votes == {} and out.deploy_mult is None


def test_pyramid_presses_winners_and_retreats_in_losses():
    ch = Channels({"AAA": {"prob": {}, "trend": {}, "vol": {}, "mom": {}}})
    up = Money(pyramid=1.0)
    up.reset()
    last = 1.0
    for eq in [100_000 * (1.02 ** i) for i in range(30)]:  # a sustained rise
        out = up.evaluate(_view(ch, equity=eq))
        if out.deploy_mult is not None:
            last = out.deploy_mult
    assert last > 1.0  # above its own trend -> deploy MORE (with the market's money)

    down = Money(pyramid=1.0)
    down.reset()
    last = 1.0
    for eq in [100_000 * (0.98 ** i) for i in range(30)]:  # a sustained fall
        out = down.evaluate(_view(ch, equity=eq))
        if out.deploy_mult is not None:
            last = out.deploy_mult
    assert last < 1.0  # below trend -> deploy LESS (never martingale into losses)
