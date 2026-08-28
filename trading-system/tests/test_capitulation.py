"""The capitulation feature: fires only on a volume-spike + drop + lower-wick candle,
stays ~0 on calm bars and in uptrends, and is strictly causal (no lookahead)."""

from __future__ import annotations

import numpy as np

from quantlab_system06.capitulation import capitulation_score


def _calm(n=200):
    close = np.full(n, 100.0)
    high = close + 0.5
    low = close - 0.5
    volume = np.full(n, 1000.0)
    return high, low, close, volume


def test_calm_market_scores_zero():
    high, low, close, volume = _calm()
    s = capitulation_score(high, low, close, volume)
    assert s.max() < 1e-6


def test_capitulation_candle_fires():
    high, low, close, volume = _calm(200)
    # a decline over the last ~20 bars, then a capitulation candle at i=180:
    for i in range(160, 181):
        close[i] = 100.0 - (i - 160) * 2.0   # steady drop
        high[i] = close[i] + 0.5
        low[i] = close[i] - 0.5
    i = 180
    # capitulation candle: huge volume, deep low, close recovers to the top of the range
    low[i] = close[i] - 12.0            # long lower wick
    high[i] = close[i] + 0.5
    volume[i] = 20000.0                 # ~20x volume spike
    s = capitulation_score(high, low, close, volume)
    assert s[i] > 0.3, f"capitulation candle should score high, got {s[i]:.3f}"
    # a calm bar far from it stays quiet
    assert s[50] < 1e-6


def test_uptrend_volume_spike_does_not_fire():
    # rising prices + a volume spike but NO drop -> not a capitulation
    n = 200
    close = 100.0 * (1.01 ** np.arange(n))
    high = close * 1.005
    low = close * 0.995
    volume = np.full(n, 1000.0)
    volume[150] = 30000.0
    s = capitulation_score(high, low, close, volume)
    assert s[150] < 1e-6, "no drop -> no capitulation even on a volume spike"


def test_is_causal():
    # changing a FUTURE bar must not change an earlier score
    high, low, close, volume = _calm(200)
    for i in range(160, 181):
        close[i] = 100.0 - (i - 160) * 2.0
        high[i], low[i] = close[i] + 0.5, close[i] - 0.5
    s_before = capitulation_score(high, low, close, volume)[180]
    # mutate bars strictly AFTER 180
    close[190:] = 50.0
    volume[190:] = 99999.0
    low[190:] = 10.0
    s_after = capitulation_score(high, low, close, volume)[180]
    assert s_before == s_after, "score at bar 180 must not depend on bars after 180"
