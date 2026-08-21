"""Build the microstructure contrarian-sentiment channel from derivatives data.

The score fuses three public perpetual-market series into one causal number in
[-1, 1] per bar, all measured relative to their own trailing regime so a "high"
reading means high *for this asset now*, not a fixed threshold:

  - **funding rate** — persistently high positive funding means longs are paying to
    stay long: a crowded, expensive long. Contrarian-bearish.
  - **open-interest surge** — leverage piling on fast (OI rising well above trend),
    especially alongside high funding, is a fragile build-up. Contrarian-bearish.
  - **long/short liquidations** — a burst of LONG liquidations is forced selling by
    over-levered longs: capitulation, and contrarian-BULLISH for a spot buyer. SHORT
    liquidations (a squeeze) are mildly bearish once the crowd is already long.

  score = tanh( w_liq·liq_flush − w_fund·funding_z − w_oi·oi_surge )

**We do not fetch this here.** The laboratory is research-only with local data; wiring
a live exchange feed is out of scope (and the project forbids exchange credentials).
This module computes the score from arrays an operator supplies (a data job writes one
`.npz` of funding/OI/liquidations per symbol aligned to the 15 m bars); until that feed
exists the microstructure lever stays off and the ensemble is unchanged. The scoring is
unit-tested so it is ready the day the data is.
"""

from __future__ import annotations

import numpy as np


def _zscore(x: np.ndarray, span: int) -> np.ndarray:
    """Causal EWMA z-score: (x - trailing mean) / trailing std, bounded input to std."""
    import pandas as pd

    s = pd.Series(np.asarray(x, dtype=float))
    mean = s.ewm(span=span, min_periods=1).mean()
    var = s.ewm(span=span, min_periods=1).var(bias=False).fillna(0.0)
    std = np.sqrt(np.maximum(var.to_numpy(), 1e-12))
    return ((s.to_numpy() - mean.to_numpy()) / std)


def contrarian_score(
    funding: np.ndarray,
    open_interest: np.ndarray,
    liq_long: np.ndarray,
    liq_short: np.ndarray,
    span: int = 96,
    w_fund: float = 0.5,
    w_oi: float = 0.3,
    w_liq: float = 0.7,
) -> np.ndarray:
    """Fuse funding / OI / liquidations into a causal contrarian score in [-1, 1].

    All inputs are per-bar arrays on the same clock as the price bars. Positive score
    = contrarian-bullish (flushed longs), negative = contrarian-bearish (crowded longs).
    """
    funding = np.asarray(funding, dtype=float)
    oi = np.asarray(open_interest, dtype=float)
    liq_long = np.asarray(liq_long, dtype=float)
    liq_short = np.asarray(liq_short, dtype=float)

    funding_z = _zscore(funding, span)
    # OI surge: z-score of the OI growth rate — fast build-up reads high.
    oi_growth = np.zeros_like(oi)
    oi_growth[1:] = np.diff(oi) / np.maximum(oi[:-1], 1e-12)
    oi_surge = np.clip(_zscore(oi_growth, span), 0.0, None)  # only the build-up side
    # Liquidation flush: net long-minus-short liquidation pressure, z-scored. A burst of
    # long liquidations (capitulation) is the bullish contrarian signal.
    net_liq = liq_long - liq_short
    liq_flush = _zscore(net_liq, span)

    raw = w_liq * liq_flush - w_fund * funding_z - w_oi * oi_surge
    return np.tanh(raw)


def write_micro(scores: dict[str, tuple[np.ndarray, np.ndarray]], out_path: str) -> None:
    """Write per-symbol `(bar_ns, score)` to the `.npz` the Channels loader reads."""
    payload: dict[str, np.ndarray] = {}
    for sym, (ns, score) in scores.items():
        payload[f"{sym}__micro_ns"] = np.asarray(ns, dtype=np.int64)
        payload[f"{sym}__micro"] = np.asarray(score, dtype=np.float32)
    np.savez(out_path, **payload)
