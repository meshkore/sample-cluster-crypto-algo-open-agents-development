"""What the model is allowed to look at, and what it must never look at.

The 79 indicator columns the laboratory already computes are the raw material.
They are not usable as they stand, for two reasons that both produce a model
that scores well and cannot trade.

**Levels are not features.** `sma_200` is about 400 on ETH and about 60,000 on
BTC, and 60,000 in 2021 is a different market from 60,000 in 2026. A tree
splitting on a raw level learns *which asset and which year* it is looking at,
which is available in training and worthless afterwards. Everything here is made
scale-free: a price-like column becomes its distance from the close in units of
volatility, a volume-like column becomes a ratio to its own recent average, and
a bounded oscillator is already dimensionless and passes through.

**The cross-section is the part a single-asset model cannot see.** Whether ETH is
up 2% matters much less than whether ETH is up 2% while everything else is flat.
Per-bar ranks across the traded universe carry that, and they are the one family
of features here that no amount of per-symbol history can reconstruct.

Nothing in this file reads a bar after the one being described. The rule is
enforced by construction -- every transform is either pointwise or a trailing
window -- and `test_ml_features.py` pins it by truncating the tape and checking
the features for the surviving rows are identical.
"""

from __future__ import annotations

import numpy as np

# Columns whose value is a PRICE. Expressed as (close - column) / (close * sigma):
# how far away it is, in units of what this asset moves in a bar. A tree can then
# use "price is two volatility units above its 200-period mean" as one fact about
# every asset in every year, which is what it actually is.
PRICE_LIKE = (
    "sma_20",
    "sma_50",
    "sma_200",
    "ema_12",
    "ema_26",
    "ema_50",
    "bb_upper",
    "bb_mid",
    "bb_lower",
    "keltner_upper",
    "keltner_mid",
    "keltner_lower",
    "donchian_upper",
    "donchian_lower",
    "vwap_20",
    "supertrend",
    "psar",
    "ichimoku_conversion",
    "ichimoku_base",
)
# Columns already dimensionless and bounded. Passed through untouched.
BOUNDED = (
    "rsi_14",
    "rsi_2",
    "stoch_k",
    "stoch_d",
    "cci",
    "mfi",
    "williams_r",
    "adx",
    "di_plus",
    "di_minus",
    "aroon_up",
    "aroon_down",
    "chaikin_money_flow",
    "internal_bar_strength",
    "bb_percent_b",
    "vortex_plus",
    "vortex_minus",
    "ultimate_oscillator",
)
# Columns that are a SIZE -- a volume, a range, a dollar turnover. Expressed as a
# log ratio to their own trailing mean, so "twice the usual volume" is one number
# on an asset trading millions and on one trading billions.
SIZE_LIKE = (
    "volume",
    "volume_sma_20",
    "quote_volume",
    "atr_14",
    "natr_14",
    "true_range",
    "range_vs_atr",
    "volume_ratio_20",
    "obv",
)


def _trailing_mean(values: np.ndarray, window: int) -> np.ndarray:
    """Causal rolling mean: bar `i` sees bars `i-window+1 .. i` and no others."""
    values = np.asarray(values, dtype=float)
    out = np.full_like(values, np.nan)
    if len(values) == 0:
        return out
    filled = np.nan_to_num(values, nan=0.0)
    valid = (~np.isnan(values)).astype(float)
    cumulative = np.concatenate([[0.0], np.cumsum(filled)])
    counts = np.concatenate([[0.0], np.cumsum(valid)])
    for i in range(len(values)):
        start = max(0, i - window + 1)
        n = counts[i + 1] - counts[start]
        if n > 0:
            out[i] = (cumulative[i + 1] - cumulative[start]) / n
    return out


def scale_free(
    panel_columns: dict[str, np.ndarray],
    close: np.ndarray,
    volatility: np.ndarray,
    window: int = 288,
) -> dict[str, np.ndarray]:
    """Every usable indicator column, in units that mean the same thing anywhere.

    A column absent from all three lists is DROPPED rather than passed through.
    That is deliberate: a column nobody has classified is a column nobody has
    checked for a level, and one leaked level is enough to make a whole study
    about which year it is.
    """
    close = np.asarray(close, dtype=float)
    volatility = np.asarray(volatility, dtype=float)
    safe_sigma = np.where(
        np.isfinite(volatility) & (volatility > 0), volatility, np.nan
    )
    out: dict[str, np.ndarray] = {}

    for name in PRICE_LIKE:
        column = panel_columns.get(name)
        if column is None:
            continue
        values = np.asarray(column, dtype=float)
        out[f"d_{name}"] = (close - values) / (close * safe_sigma)

    for name in BOUNDED:
        column = panel_columns.get(name)
        if column is not None:
            out[name] = np.asarray(column, dtype=float)

    for name in SIZE_LIKE:
        column = panel_columns.get(name)
        if column is None:
            continue
        values = np.asarray(column, dtype=float)
        reference = _trailing_mean(np.abs(values), window)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(reference > 0, values / reference, np.nan)
        # Log, because these are ratios: "half the usual" and "twice the usual"
        # should be the same distance from normal, and on a raw ratio they are
        # 0.5 and 2.0 -- a tree would need two splits to learn one fact.
        out[f"r_{name}"] = np.sign(ratio) * np.log1p(np.abs(ratio))
    return out


def calendar(timestamps: np.ndarray) -> dict[str, np.ndarray]:
    """Hour and weekday, encoded so that 23:00 is adjacent to 00:00.

    The 06:00 UTC hour is the entire basis of the incumbent rule, so the model
    is entitled to see the clock. It gets it as sine and cosine rather than as an
    integer, because an integer makes midnight maximally distant from 23:00 and a
    tree then needs two splits to express "the night", spending capacity on an
    artefact of the encoding.
    """
    hours = np.asarray([t.hour + t.minute / 60.0 for t in timestamps], dtype=float)
    days = np.asarray([t.weekday() for t in timestamps], dtype=float)
    return {
        "hour_sin": np.sin(2 * np.pi * hours / 24.0),
        "hour_cos": np.cos(2 * np.pi * hours / 24.0),
        "dow_sin": np.sin(2 * np.pi * days / 7.0),
        "dow_cos": np.cos(2 * np.pi * days / 7.0),
        "session_progress": hours / 24.0,
    }


def session_shape(
    close: np.ndarray, timestamps: np.ndarray, volatility: np.ndarray
) -> dict[str, np.ndarray]:
    """Where this bar sits inside its own UTC day, in volatility units.

    The incumbent rule is one number from this family -- the day's return so far
    at 06:00 -- and it is included so the model can find that rule if it is real,
    reject it if it is not, and find its neighbours either way. Expressed against
    volatility rather than in percent, which is precisely the correction the
    sealed window forced.
    """
    close = np.asarray(close, dtype=float)
    volatility = np.asarray(volatility, dtype=float)
    day = np.asarray([t.strftime("%Y-%m-%d") for t in timestamps])
    open_price = np.empty_like(close)
    high_so_far = np.empty_like(close)
    low_so_far = np.empty_like(close)
    current = None
    o = h = low = close[0] if len(close) else 0.0
    for i in range(len(close)):
        if day[i] != current:
            current, o, h, low = day[i], close[i], close[i], close[i]
        h, low = max(h, close[i]), min(low, close[i])
        open_price[i], high_so_far[i], low_so_far[i] = o, h, low
    sigma = np.where(np.isfinite(volatility) & (volatility > 0), volatility, np.nan)
    day_return = close / open_price - 1
    # `np.where` evaluates BOTH branches, so a guard written as its condition
    # does not stop the division it is guarding -- it only hides the result. The
    # span is made safe first and the guard applied afterwards.
    span = high_so_far - low_so_far
    safe_span = np.where(span > 0, span, np.nan)
    position = np.where(span > 0, (close - low_so_far) / safe_span, 0.5)
    return {
        "day_return_sigma": day_return / sigma,
        "day_range_sigma": span / (open_price * sigma),
        "position_in_day_range": position,
    }


def cross_sectional_rank(
    values_by_symbol: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    """Each symbol's percentile against the others, bar by bar.

    The one family of features a per-symbol model cannot reconstruct from its own
    history: "up 2% while everything else is flat" and "up 2% with the whole
    market" are the same number per symbol and different events. Ranks rather
    than z-scores, because one asset having a violent day should not move every
    other asset's feature.

    Requires the arrays to be aligned on a shared timeline -- `dataset.py` does
    that alignment, and passing ragged series here silently compares different
    moments in time.
    """
    symbols = sorted(values_by_symbol)
    if not symbols:
        return {}
    stacked = np.vstack([values_by_symbol[s] for s in symbols])
    ranks = np.full_like(stacked, np.nan, dtype=float)
    for column in range(stacked.shape[1]):
        slice_ = stacked[:, column]
        finite = np.isfinite(slice_)
        count = int(finite.sum())
        if count < 2:
            continue
        order = np.argsort(np.argsort(slice_[finite]))
        ranks[finite, column] = order / (count - 1)
    return {symbol: ranks[i] for i, symbol in enumerate(symbols)}
