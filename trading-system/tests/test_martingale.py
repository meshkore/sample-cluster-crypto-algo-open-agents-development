"""Martingale: a bounded, occasional press into a SHALLOW dip — and a hard refusal
to press a deep drawdown (where a naive martingale would double into ruin)."""

from __future__ import annotations

from datetime import datetime, timezone

from system006_oracle_net_15m.channels import Channels
from system006_oracle_net_15m.modules.base import MarketView
from system006_oracle_net_15m.modules.martingale import Martingale


def _view(ns=10, equity=100_000.0):
    ch = Channels({"AAA": {"prob": {}, "trend": {}, "vol": {}, "mom": {}}})
    return MarketView(timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), ns=ns,
                      candles={"AAA": {"close": 100.0}}, account={"equity": equity, "positions": {}},
                      channels=ch, held=set(), peaks={})


def test_off_by_default_abstains():
    m = Martingale()  # step 0
    m.reset()
    for eq in (100_000, 90_000, 80_000):
        assert m.evaluate(_view(equity=eq)).deploy_mult is None


def test_shallow_dip_presses_up_bounded():
    m = Martingale(step=0.5, cap=1.35, floor_dd=0.12)
    m.reset()
    m.evaluate(_view(equity=100_000))          # seed the equity EMA
    out = m.evaluate(_view(equity=95_000))     # ~5% dip, shallow
    assert out.deploy_mult is not None
    assert 1.0 < out.deploy_mult <= 1.35       # presses, but capped


def test_deep_drawdown_stands_down():
    m = Martingale(step=0.5, floor_dd=0.12)
    m.reset()
    m.evaluate(_view(equity=100_000))          # seed
    out = m.evaluate(_view(equity=80_000))     # 20% dip, beyond the floor
    assert out.deploy_mult == 1.0              # refuses to martingale a real drawdown


def test_above_trend_is_neutral_never_scales_down():
    m = Martingale(step=0.5)
    m.reset()
    m.evaluate(_view(equity=100_000))          # seed
    out = m.evaluate(_view(equity=106_000))    # above trend
    assert out.deploy_mult == 1.0              # neutral; it only ever presses, never retreats
