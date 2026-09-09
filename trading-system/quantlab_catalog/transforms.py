"""Causal transforms: the normalisation primitives, shared and fitted on nothing.

This is the piece the laboratory did not have, and the audit on 2026-09-09 found it by
looking rather than assuming. What existed was:

  * `quantlab_backtester.indicators` - ~91 CLASSICAL TA columns (RSI, MACD, Bollinger,
    ADX, Ichimoku, SuperTrend...), causal and cached. Real, shared, and precisely the
    "bag of indicators" the alpha specification rejects in its section 3. Inheriting it
    because it exists would be dragging in the thing we were told not to build on.
  * `quantlab_system06.features` - a curated subset of that panel plus a standardiser
    whose mean/std are FITTED on a training slice and shipped with one model. Correct
    for that system, useless to another, and not a library.

What no system could reuse was the arithmetic underneath: rolling z-scores, robust
z-scores, rolling percentiles, signed logs. Every system re-derived them inside its own
feature file, which is how the same operation ends up with three implementations and
one of them wrong.

THE RULE ALL OF THESE OBEY, and it is the only rule that matters here: a value at index
`i` is computed from `x[:i+1]` and nothing else. There is no fitting step, no stored
mean, no training slice - the statistics travel WITH the series, recomputed from its own
past at every point. That is what makes them safe to apply to the whole history at once
without the fit/apply split that leaks when somebody forgets it.

    "Do not normalize using mean/std calculated over the entire dataset. That leaks
     future distribution information."  - alpha spec, section 7

Every function here is tested against a brute-force reference implementation that
recomputes each point from a truncated copy of the series, because the fast cumulative
forms are exactly where an off-by-one becomes a look-ahead nobody can see.
"""

from __future__ import annotations

import numpy as np

EPS = 1e-12
# 1 / Phi^-1(0.75). Scales the median absolute deviation so that, for normally
# distributed data, robust_z and rolling_z agree. Without it the two are on different
# scales and a threshold tuned on one silently means something else on the other.
MAD_TO_SIGMA = 1.4826


def _as_float(x) -> np.ndarray:
    arr = np.asarray(x, dtype=float).ravel()
    if arr.size == 0:
        raise ValueError("an empty series has no causal statistics")
    return arr


def rolling_mean(x, window: int) -> np.ndarray:
    """Trailing mean of the `window` values ENDING at each index. NaN until full."""
    a = _as_float(x)
    if window < 1:
        raise ValueError("window must be at least 1")
    out = np.full(a.size, np.nan)
    if a.size < window:
        return out
    c = np.concatenate([[0.0], np.cumsum(a)])
    out[window - 1:] = (c[window:] - c[:a.size - window + 1]) / window
    return out


def rolling_std(x, window: int) -> np.ndarray:
    """Trailing population standard deviation, same window convention.

    Computed on the series SHIFTED by its own first value, which is the whole reason
    this function is longer than one line. The textbook form `mean(x^2) - mean(x)^2`
    subtracts two nearly equal large numbers: on a constant series near 12,345 it
    returns a standard deviation of 5e-4 instead of 0, because x^2 is ~1.5e8 and the
    difference is lost in the mantissa. A test caught it here on flat data; on a price
    series with genuine small variation that same noise floor would sit underneath every
    z-score in the system and nothing would ever complain.

    Shifting by `a[0]` fixes it and costs nothing. Standard deviation is
    translation-invariant, so the result is unchanged mathematically, and `a[0]` is the
    one constant that is already known at every index - shifting by the series MEAN
    would have been faster to write and would have made the output depend on data the
    point cannot see.
    """
    a = _as_float(x)
    d = a - a[0]
    mean = rolling_mean(d, window)
    mean_sq = rolling_mean(d * d, window)
    var = np.maximum(mean_sq - mean * mean, 0.0)   # clipped: float error goes negative
    return np.sqrt(var)


def rolling_z(x, window: int) -> np.ndarray:
    """(x - trailing mean) / trailing std. The workhorse.

    NaN for the first `window - 1` points rather than 0.0: a z-score of zero means
    "exactly average", and filling the warm-up with it tells the model something false
    at precisely the points where it knows least.
    """
    a = _as_float(x)
    return (a - rolling_mean(a, window)) / (rolling_std(a, window) + EPS)


def robust_z(x, window: int) -> np.ndarray:
    """Median/MAD z-score, for the heavy tails that make a plain z-score useless.

    One 20-sigma print moves a rolling mean and inflates a rolling std, so the bars
    AFTER a crash get scored against a distribution the crash itself created. The median
    barely notices it. Crypto returns, funding and liquidation notionals are all in this
    category.
    """
    a = _as_float(x)
    n = a.size
    out = np.full(n, np.nan)
    if n < window:
        return out
    # No cumulative trick exists for a median; the strided view is the honest cost.
    view = np.lib.stride_tricks.sliding_window_view(a, window)
    med = np.median(view, axis=1)
    mad = np.median(np.abs(view - med[:, None]), axis=1)
    out[window - 1:] = (a[window - 1:] - med) / (MAD_TO_SIGMA * mad + EPS)
    return out


def rolling_percentile(x, window: int) -> np.ndarray:
    """Where the current value sits within its own trailing window, in [0, 1].

    Bounded by construction, which is why it is the right transform for a REGIME
    variable: "volatility is at its 95th percentile of the last month" survives a change
    of scale that would make a z-score of the same series incomparable across years.
    """
    a = _as_float(x)
    n = a.size
    out = np.full(n, np.nan)
    if n < window:
        return out
    view = np.lib.stride_tricks.sliding_window_view(a, window)
    # Strictly-less plus half the ties: the midrank convention, so a constant series
    # scores 0.5 everywhere instead of 1.0.
    current = a[window - 1:, None]
    below = (view < current).sum(axis=1)
    equal = (view == current).sum(axis=1)
    out[window - 1:] = (below + 0.5 * equal) / window
    return out


def signed_log1p(x) -> np.ndarray:
    """sign(x) * log(1 + |x|). Compresses tails while keeping direction and zero.

    For quantities that are signed and span orders of magnitude - net flow, order
    imbalance, liquidation notional - where a plain log cannot take the sign and a
    raw value lets one print dominate a whole training batch.
    """
    a = _as_float(x)
    return np.sign(a) * np.log1p(np.abs(a))


def relative_change(x, window: int) -> np.ndarray:
    """x_t / x_(t-window) - 1. NaN where the base is missing or non-positive."""
    a = _as_float(x)
    out = np.full(a.size, np.nan)
    if a.size <= window:
        return out
    base = a[:-window]
    with np.errstate(divide="ignore", invalid="ignore"):
        out[window:] = np.where(np.abs(base) > EPS, a[window:] / base - 1.0, np.nan)
    return out


def log_change(x, window: int) -> np.ndarray:
    """log(x_t / x_(t-window)), for strictly positive series such as price."""
    a = _as_float(x)
    out = np.full(a.size, np.nan)
    if a.size <= window:
        return out
    base, cur = a[:-window], a[window:]
    ok = (base > EPS) & (cur > EPS)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[window:] = np.where(ok, np.log(cur / base), np.nan)
    return out


def efficiency(x, window: int) -> np.ndarray:
    """Directional efficiency: net move divided by the path walked to make it.

    Near 1 means the move was a straight line; near 0 means price travelled a long way
    and ended where it started. The alpha spec uses it as the primary trend-versus-range
    variable in place of ADX, and it is the one transform here that is not a pure
    normalisation - it is included because every branch of that spec needs it and each
    would otherwise write its own.
    """
    a = _as_float(x)
    n = a.size
    out = np.full(n, np.nan)
    if n <= window:
        return out
    steps = np.abs(np.diff(a, prepend=a[0]))
    walked = rolling_mean(steps, window) * window
    net = np.full(n, np.nan)
    net[window:] = np.abs(a[window:] - a[:-window])
    return np.divide(net, walked + EPS, out=out, where=np.isfinite(net))
