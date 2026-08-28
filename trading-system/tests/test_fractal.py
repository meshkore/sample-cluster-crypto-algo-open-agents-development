"""Fractal regime: the causal Hurst channel reads persistence, the module gates chop."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from quantlab_system06.channels import Channels
from quantlab_system06.infer import _causal_hurst
from quantlab_system06.modules.base import MarketView
from quantlab_system06.modules.fractal import Fractal


def _view(channels, ns=10, symbols=("AAA",)):
    return MarketView(timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), ns=ns,
                      candles={s: {"close": 100.0} for s in symbols},
                      account={"positions": {}}, channels=channels, held=set(), peaks={})


def test_hurst_separates_regimes():
    n = 4000
    rng = np.random.default_rng(0)

    # Persistent / trending: a steady drift dominates -> tau-lag moves grow ~linearly
    # with tau -> H well above 0.5.
    trend = 100.0 * (1.0004 ** np.arange(n)) * np.exp(rng.normal(0, 2e-4, n))
    h_trend = float(_causal_hurst(trend)[-1])

    # Random walk: increments i.i.d. -> tau-lag move grows as sqrt(tau) -> H ~ 0.5.
    walk = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    h_walk = float(_causal_hurst(walk)[-1])

    # Anti-persistent / choppy: sign-alternating oscillation -> tau-lag moves do not
    # grow with tau (they cancel) -> H well below 0.5.
    chop = 100.0 * np.exp(0.01 * ((-1.0) ** np.arange(n)))
    h_chop = float(_causal_hurst(chop)[-1])

    assert h_trend > 0.55, h_trend
    assert 0.40 <= h_walk <= 0.60, h_walk
    assert h_chop < 0.45, h_chop
    assert h_trend > h_walk > h_chop


def test_hurst_is_causal_and_bounded():
    n = 2000
    rng = np.random.default_rng(1)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    h = _causal_hurst(close)
    assert h.shape == (n,)
    assert np.all(h >= 0.0) and np.all(h <= 1.0)
    # Warm-up bars are the neutral 0.5 (honest 'unknown'), never a fabricated call.
    assert np.allclose(h[:100].astype(float), 0.5)
    # Recomputing on a prefix must not change earlier values (strict causality).
    h_prefix = _causal_hurst(close[:1500])
    assert np.allclose(h[:1500].astype(float), h_prefix.astype(float))


def test_hurst_too_short_is_neutral():
    h = _causal_hurst(np.linspace(100, 110, 50))
    assert np.allclose(h.astype(float), 0.5)


def test_module_vetoes_choppy_and_abstains_when_off():
    ch = Channels({
        "AAA": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {10: 0.30}},   # choppy
        "BBB": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {10: 0.70}},   # persistent
        "CCC": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {10: 0.50}},   # warm-up neutral
        "DDD": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {}},           # unknown
    })
    syms = ["AAA", "BBB", "CCC", "DDD"]

    # Off -> abstains entirely (identical to the pre-fractal path).
    assert Fractal(hurst_gate=0.0).evaluate(_view(ch, symbols=syms)).votes == {}

    out = Fractal(hurst_gate=0.45).evaluate(_view(ch, symbols=syms))
    assert out.votes["AAA"].veto is True   # H<0.45 -> choppy -> vetoed
    assert "BBB" not in out.votes          # persistent -> allowed
    assert "CCC" not in out.votes          # neutral 0.5 not below 0.45 -> allowed
    assert "DDD" not in out.votes          # unknown -> abstain -> allowed
