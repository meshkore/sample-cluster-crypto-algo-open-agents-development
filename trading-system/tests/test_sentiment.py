"""Behavioural fear/greed: the causal index reads crowd emotion, the module sizes contrarian."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from quantlab_system06.channels import Channels
from quantlab_system06.infer import _causal_feargreed
from quantlab_system06.modules.base import MarketView
from quantlab_system06.modules.sentiment import Sentiment


def _view(channels, ns=10, symbols=("AAA",)):
    return MarketView(timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), ns=ns,
                      candles={s: {"close": 100.0} for s in symbols},
                      account={"positions": {}}, channels=channels, held=set(), peaks={})


def test_feargreed_direction_and_bounds():
    n = 6000
    rng = np.random.default_rng(0)

    # A calm blow-off top: a long steady base, then price extends far above its trailing
    # mean with LOW added noise -> greed (fg high) by the end.
    base = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.002, n - 800)))
    ramp = base[-1] * (1.0 + np.linspace(0, 0.8, 800))  # smooth surge above the mean, calm
    greedy = np.concatenate([base, ramp])
    fg_greed = float(_causal_feargreed(greedy)[-1])

    # A turbulent capitulation: price drops well below its trailing mean amid high vol -> fear.
    drop = base[-1] * np.exp(np.cumsum(rng.normal(-0.01, 0.05, 800)))
    fearful = np.concatenate([base, drop])
    fg_fear = float(_causal_feargreed(fearful)[-1])

    assert 0.0 <= fg_greed <= 1.0 and 0.0 <= fg_fear <= 1.0
    assert fg_greed > 0.6, fg_greed        # extended + calm -> greedy
    assert fg_fear < 0.4, fg_fear          # below trend + turbulent -> fearful
    assert fg_greed > fg_fear


def test_feargreed_is_causal():
    n = 3000
    rng = np.random.default_rng(1)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    fg = _causal_feargreed(close)
    assert fg.shape == (n,)
    assert np.all(fg >= 0.0) and np.all(fg <= 1.0)
    fg_prefix = _causal_feargreed(close[:2000])
    assert np.allclose(fg[:2000].astype(float), fg_prefix.astype(float))


def test_module_trims_greed_presses_fear_abstains_off():
    ch = Channels({
        "GREED": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {}, "feargreed": {10: 0.95}},
        "FEAR":  {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {}, "feargreed": {10: 0.05}},
        "CALM":  {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {}, "feargreed": {10: 0.50}},
        "NONE":  {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {}, "feargreed": {}},
    })
    syms = ["GREED", "FEAR", "CALM", "NONE"]

    # Off -> abstains entirely (identical to the pre-sentiment path).
    assert Sentiment(feargreed=0.0).evaluate(_view(ch, symbols=syms)).votes == {}

    out = Sentiment(feargreed=1.0).evaluate(_view(ch, symbols=syms))
    assert out.votes["GREED"].size_mult < 1.0   # greed -> trim
    assert out.votes["FEAR"].size_mult > 1.0    # fear -> press
    assert "CALM" not in out.votes              # neutral -> no change
    assert "NONE" not in out.votes              # unknown -> abstain
    # Bounded.
    assert 0.5 <= out.votes["GREED"].size_mult <= 1.3
    assert 0.5 <= out.votes["FEAR"].size_mult <= 1.3
