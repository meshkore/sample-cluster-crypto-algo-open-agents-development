"""Microstructure: the contrarian score reads the crowd, the module vetoes fragile longs."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from quantlab_system06.channels import Channels
from quantlab_system06.microstructure import contrarian_score
from quantlab_system06.modules.base import MarketView
from quantlab_system06.modules.microstructure import Microstructure


def _view(channels, ns=10, symbols=("AAA",)):
    return MarketView(timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), ns=ns,
                      candles={s: {"close": 100.0} for s in symbols},
                      account={"positions": {}}, channels=channels, held=set(), peaks={})


def test_score_bounds_and_sign():
    n = 300
    rng = np.random.default_rng(0)
    funding = rng.normal(0, 1e-4, n)
    oi = np.cumsum(rng.normal(0, 1.0, n)) + 1000
    liq_long = np.abs(rng.normal(0, 1.0, n))
    liq_short = np.abs(rng.normal(0, 1.0, n))
    # A crowded top at bar 200: funding and OI both spike hard.
    funding[200] = 0.02
    oi[200:] += 500
    score = contrarian_score(funding, oi, liq_long, liq_short)
    assert score.shape == (n,)
    assert np.all(score >= -1.0) and np.all(score <= 1.0)
    assert score[200] < 0  # crowded, over-levered longs -> contrarian bearish

    # A long-liquidation flush -> contrarian bullish.
    liq_long2 = liq_long.copy()
    liq_long2[250] = 50.0
    score2 = contrarian_score(funding, oi, liq_long2, liq_short)
    assert score2[250] > 0


def test_module_vetoes_fragile_and_abstains_when_off():
    ch = Channels({"AAA": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "micro": {10: -0.8}},
                  "BBB": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "micro": {10: 0.6}}})
    assert Microstructure(gate=None).evaluate(_view(ch, symbols=["AAA", "BBB"])).votes == {}
    out = Microstructure(gate=0.5).evaluate(_view(ch, symbols=["AAA", "BBB"]))
    assert out.votes["AAA"].veto is True   # crowded top -> vetoed
    assert "BBB" not in out.votes          # flushed / bullish -> allowed
