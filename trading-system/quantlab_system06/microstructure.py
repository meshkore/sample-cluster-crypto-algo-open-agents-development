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


def build_from_funding(signals_path: str, funding_dir: str = "research/system06/external",
                       span: int = 96) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Build the micro channel from FUNDING ALONE, aligned to each symbol's signal bars.

    What this is and is not, stated because the difference matters: `contrarian_score`
    fuses funding, open interest and liquidations. Only funding has a public long
    history - Binance exposes open interest for about a month and does not publish
    historical liquidations at all - so this builds the funding term by itself.

    That keeps one honest half of the idea: persistently positive funding means longs
    are paying to stay long, which is crowding, and a crowded book is a fragile place
    for a spot strategy to open a NEW position. It drops the other half entirely - the
    capitulation flush that only liquidations can see - so a negative result here
    refutes crowding-by-funding, not the microstructure thesis.

    Two readings of "crowded", combined, because the first one alone is wrong:

      * a SURGE - funding unusual against its own recent history (z-score). Written
        first and then caught failing its own test: a z-score erases funding that has
        been high for months, since the trailing mean simply follows it up. Sustained
        expensive funding is exactly the crowded state the idea is about, so a surge
        term alone measures the opposite of the thing.
      * a LEVEL - funding expensive in absolute terms, normalised by 0.05% per 8h.
        That constant is external, not fitted here: Binance's baseline funding is
        0.01% per 8h, so 0.05% is five times what a balanced book pays, and a
        position paying it is being taxed hard to stay long.

    Causality: a bar reads only settlements strictly before it, and the sign is flipped
    so that crowded reads NEGATIVE, matching the channel's contract.
    """
    import json
    from pathlib import Path

    data = np.load(signals_path)
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for key in data.files:
        if not key.endswith("__epoch_ns"):
            continue
        symbol = key[: -len("__epoch_ns")]
        rows_path = Path(funding_dir) / f"funding_{symbol}.json"
        if not rows_path.is_file():
            continue                       # no perp history -> the module abstains here
        rows = sorted(json.loads(rows_path.read_text(encoding="utf-8")),
                      key=lambda r: int(r["t_ms"]))
        if len(rows) < span:
            continue
        f_ns = np.array([int(r["t_ms"]) for r in rows], dtype=np.int64) * 1_000_000
        f_rate = np.array([float(r["rate"]) for r in rows], dtype=float)
        f_z = _zscore(f_rate, span)
        bar_ns = data[key].astype(np.int64)
        # index of the last settlement STRICTLY before each bar
        idx = np.searchsorted(f_ns, bar_ns, side="left") - 1
        safe = np.clip(idx, 0, len(f_z) - 1)
        surge = f_z[safe]
        level = f_rate[safe] / 0.0005        # 5x Binance's baseline funding = 1.0
        score = np.where(idx >= 0, np.tanh(-(0.5 * surge + level)), 0.0)
        out[symbol] = (bar_ns, score.astype(np.float32))
    return out
