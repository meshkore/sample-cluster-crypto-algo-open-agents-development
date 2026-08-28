"""A causal OHLCV capitulation signal — a NARROW bear-bottom detector.

The R&D loop proved (2026-08-21) that every GLOBAL exposure/entry-timing cut (money
management, volatility targeting, a longer trend filter) LOWERS the rolling one-year
win rate, because the winning cohorts come from catching the bull and any global cut
loses more winners than it saves. The 17 losing cohorts are all shallow bear-entries.

So the only levers that can raise reliability act NARROWLY — only at the bear bottoms
the losing cohorts ride into — and leave the bull cohorts untouched. This feature is
that narrow trigger: a liquidation-cascade / capitulation score, high ONLY when three
things coincide on a bar (all knowable at that bar's close, so it is causal):

  - a VOLUME SPIKE (causal EWMA z-score of volume is high) — forced selling,
  - a recent DROP (price is down over the last `drop_span` bars) — we are in a decline,
  - a LOWER-WICK REJECTION (close sits high in the bar's range) — buyers absorbed the
    flush, the classic capitulation candle.

The score is bounded in [0, 1) and is 0 on calm bars and in uptrends. It is a FEATURE
only here — not wired into the live ensemble. It must be shown offline to help
bear-entry cohorts without clipping the bull before it can enter the decision path.

Long-only, research-only, spot OHLCV — no derivatives, no leverage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-9


def capitulation_score(high, low, close, volume, *, vol_span: int = 96,
                       drop_span: int = 16, vol_gain: float = 1.0,
                       drop_gain: float = 8.0) -> np.ndarray:
    """Per-bar capitulation score in [0, 1), causal (bar i uses only bars <= i).

    High only when a volume spike, a recent drop, and a lower-wick rejection coincide.
    """
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    volume = np.asarray(volume, dtype=float)
    n = close.shape[0]
    if n == 0:
        return np.zeros(0)

    # Causal volume z-score via EWMA mean/var (only past+current volume).
    v = pd.Series(volume)
    mean = v.ewm(span=vol_span, min_periods=1).mean()
    var = v.ewm(span=vol_span, min_periods=1).var(bias=True).fillna(0.0)
    std = np.sqrt(var.to_numpy()) + EPS
    vol_z = (v.to_numpy() - mean.to_numpy()) / std

    # Recent drop magnitude over drop_span bars (causal); 0 when flat/up.
    ret_k = np.zeros(n)
    if n > drop_span:
        ret_k[drop_span:] = close[drop_span:] / close[:-drop_span] - 1.0
    drop = np.maximum(0.0, -ret_k)

    # Lower-wick rejection: where the close sits in the bar's range (1 = at the high).
    rng = high - low
    rejection = np.where(rng > 0, (close - low) / (rng + EPS), 0.5)

    score = rejection * np.tanh(vol_gain * np.maximum(0.0, vol_z)) * np.tanh(drop_gain * drop)
    return np.clip(score, 0.0, 1.0)
