"""Market-state features: let the net SEE the market it trades in.

Idea A59, and the first attack on the measured deep constraint. All 44 existing
features are per-symbol - the net knows its own coin's trend, volatility, candles
and flow, and nothing about the market around it. Breadth, BTC's state and the
symbol's standing among its peers exist only as POST-HOC filters (breadth gate,
meta) that the net cannot learn from. Three measurements cohere with that hole:
the cross-asset horse-race lever bolted on after the net was null; the meta
filter, which implicitly sees market-wide outcomes, is worth more than every
sizing overlay combined; and the net's edge collapses precisely in the years
whose character is market-wide (the 2022 bear, the 2025 chop).

Six columns, all causal by construction (a value at bar t uses only closes at
bars <= t, via positional lags within each symbol's own series):

  mkt_frac_up_96     fraction of the universe above its close of 1 day ago
  mkt_frac_up_2880   the same at 30 days - a slow breadth
  mkt_btc_ret_96     BTC's 1-day return (the market's anchor asset)
  mkt_btc_ret_2880   BTC's 30-day return
  mkt_disp_96        cross-sectional stdev of 1-day returns - DISPERSION, which
                     this repository already measured to be the precondition other
                     mechanisms live or die by
  mkt_mom_rank_96    THIS symbol's 1-day-return rank within the universe, in [0,1]

The first five are shared across symbols at each timestamp; the last is
per-symbol. Warm-up rows and timestamps with fewer than MIN_CROSS symbols are
NaN, which `finite_rows` already excludes - the same mechanism every warm-up
uses. The whole thing is OFF unless a `MarketTable` is passed to `build_matrix`,
so the default path is byte-identical to every result on record.
"""

from __future__ import annotations

import numpy as np

MARKET_FEATURE_COLUMNS: tuple[str, ...] = (
    "mkt_frac_up_96", "mkt_frac_up_2880", "mkt_btc_ret_96", "mkt_btc_ret_2880",
    "mkt_disp_96", "mkt_mom_rank_96",
)

FAST_LAG = 96        # 1 day of 15m bars
SLOW_LAG = 2880      # 30 days
MIN_CROSS = 3        # fewer symbols than this at a timestamp -> NaN row
BTC = "BTCUSDT"


def _ns(ts) -> int:
    return int(np.datetime64(ts.replace(tzinfo=None), "ns").astype("int64"))


class MarketTable:
    """Per-timestamp market columns, built once from every symbol's bars."""

    def __init__(self, bars_by_symbol: dict[str, list]):
        per_sym: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        for sym, bars in bars_by_symbol.items():
            if not bars:
                continue
            ts = np.array([_ns(b.timestamp) for b in bars], dtype=np.int64)
            close = np.array([b.close for b in bars], dtype=float)
            r_fast = np.full(len(close), np.nan)
            r_slow = np.full(len(close), np.nan)
            if len(close) > FAST_LAG:
                r_fast[FAST_LAG:] = close[FAST_LAG:] / close[:-FAST_LAG] - 1.0
            if len(close) > SLOW_LAG:
                r_slow[SLOW_LAG:] = close[SLOW_LAG:] / close[:-SLOW_LAG] - 1.0
            per_sym[sym] = (ts, r_fast, r_slow)

        # Shared columns per timestamp + this-symbol rank per (timestamp, symbol).
        shared: dict[int, np.ndarray] = {}
        rank: dict[int, dict[str, float]] = {}
        cursor = {s: 0 for s in per_sym}
        all_ts = sorted({int(t) for ts, _, _ in per_sym.values() for t in ts})
        # Advance a cursor per symbol instead of searching, since bars are sorted.
        for t in all_ts:
            fasts, slows, syms = [], [], []
            btc_fast = btc_slow = np.nan
            for s, (ts, rf, rs) in per_sym.items():
                i = cursor[s]
                if i < len(ts) and ts[i] == t:
                    cursor[s] = i + 1
                    if np.isfinite(rf[i]):
                        fasts.append(rf[i])
                        syms.append((s, rf[i]))
                    if np.isfinite(rs[i]):
                        slows.append(rs[i])
                    if s == BTC:
                        btc_fast, btc_slow = rf[i], rs[i]
            if len(fasts) < MIN_CROSS:
                continue
            fr96 = float(np.mean([1.0 if x > 0 else 0.0 for x in fasts]))
            fr2880 = (float(np.mean([1.0 if x > 0 else 0.0 for x in slows]))
                      if len(slows) >= MIN_CROSS else np.nan)
            disp = float(np.std(fasts)) if len(fasts) >= MIN_CROSS else np.nan
            shared[t] = np.array([fr96, fr2880, btc_fast, btc_slow, disp], dtype=float)
            order = sorted(syms, key=lambda kv: kv[1])
            n = len(order)
            rank[t] = {s: (i / (n - 1) if n > 1 else 0.5) for i, (s, _) in enumerate(order)}
        self._shared = shared
        self._rank = rank

    def matrix_for(self, symbol: str, timestamps: np.ndarray) -> np.ndarray:
        """The six market columns aligned to one symbol's bar timestamps.

        `timestamps` is `build_matrix`'s datetime64[ns] output. Rows whose timestamp
        the table does not cover (warm-up, thin cross-sections) are NaN and fall to
        `finite_rows` exactly as per-symbol warm-ups already do.
        """
        ts_int = timestamps.astype("datetime64[ns]").astype("int64")
        out = np.full((len(ts_int), len(MARKET_FEATURE_COLUMNS)), np.nan)
        for row, t in enumerate(ts_int.tolist()):
            sh = self._shared.get(t)
            if sh is None:
                continue
            out[row, :5] = sh
            out[row, 5] = self._rank.get(t, {}).get(symbol, np.nan)
        return out
