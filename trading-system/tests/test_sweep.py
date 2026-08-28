"""MM liquidation hunt: the two-sided sweep channel is causal; the module presses after one."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from quantlab_system06.channels import Channels
from quantlab_system06.infer import _causal_sweep
from quantlab_system06.modules.base import MarketView
from quantlab_system06.modules.sweep import Sweep


def _series(n=600, seed=0):
    """A calm baseline series with small bodies and small wicks."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    high = close * 1.001
    low = close * 0.999
    volume = np.full(n, 100.0)
    return high, low, close, volume


def _view(ch, symbols, ns=10):
    return MarketView(timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), ns=ns,
                      candles={s: {"close": 100.0} for s in symbols},
                      account={"positions": {}}, channels=ch, held=set(), peaks={})


def test_sweep_fires_on_two_sided_wick_spike():
    high, low, close, volume = _series()
    i = 500
    # A market-maker cleanup: both wicks long around a tiny body, huge volume, wide range.
    high[i] = close[i] * 1.06
    low[i] = close[i] * 0.94
    volume[i] = 2000.0
    score = _causal_sweep(high, low, close, volume)
    assert score.shape == close.shape
    assert np.all(score >= 0.0) and np.all(score <= 1.0)
    assert float(score[i]) > 0.25, float(score[i])          # the sweep bar fires
    calm = np.delete(score.astype(float), i)
    assert calm.max() < float(score[i])                      # and it is the standout bar


def test_one_sided_wick_does_not_fire():
    """A long lower wick alone (ordinary capitulation) is NOT a two-sided sweep."""
    high, low, close, volume = _series(seed=1)
    i = 500
    high[i] = close[i] * 1.001          # no upper wick
    low[i] = close[i] * 0.94            # long lower wick only
    volume[i] = 2000.0
    score = _causal_sweep(high, low, close, volume)
    assert float(score[i]) < 0.10, float(score[i])


def test_sweep_is_causal():
    high, low, close, volume = _series(n=800, seed=2)
    i = 600
    high[i] = close[i] * 1.05
    low[i] = close[i] * 0.95
    volume[i] = 1500.0
    full = _causal_sweep(high, low, close, volume)
    prefix = _causal_sweep(high[:700], low[:700], close[:700], volume[:700])
    assert np.allclose(full[:700].astype(float), prefix.astype(float))


def test_empty_and_warmup_are_zero():
    assert _causal_sweep(np.array([]), np.array([]), np.array([]), np.array([])).shape == (0,)
    high, low, close, volume = _series(n=200, seed=3)
    score = _causal_sweep(high, low, close, volume, span=96)
    assert np.allclose(score[:96].astype(float), 0.0)   # no trailing baseline yet


def test_module_presses_after_sweep_and_abstains_when_off():
    ch = Channels({
        "HIT":  {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {}, "feargreed": {}, "sweep": {10: 0.90}},
        "MILD": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {}, "feargreed": {}, "sweep": {10: 0.05}},
        "NONE": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {}, "feargreed": {}, "sweep": {}},
    })
    syms = ["HIT", "MILD", "NONE"]
    assert Sweep(sweep=0.0).evaluate(_view(ch, syms)).votes == {}      # off -> abstain

    out = Sweep(sweep=1.0).evaluate(_view(ch, syms))
    assert out.votes["HIT"].size_mult > 1.0        # strong sweep -> press
    assert "MILD" not in out.votes                 # below the gate -> untouched
    assert "NONE" not in out.votes                 # unknown -> abstain
    assert out.votes["HIT"].size_mult <= 1.3       # bounded
