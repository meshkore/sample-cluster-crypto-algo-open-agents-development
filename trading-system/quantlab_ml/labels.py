"""What a bar is worth, labelled the way a real position actually resolves.

**Why not "the return over the next N bars".** That is the dominant labelling in
published work and it is what produced this laboratory's most expensive mistake
in miniature: it learns from a number no position ever earns. A real trade ends
when it hits a target, hits a stop, or runs out of time -- whichever comes FIRST
-- and the order those three arrive in is most of the outcome. Two bars with the
same 72-hour return can be a comfortable winner and a stop-out that happened to
recover, and a model trained on the horizon return cannot tell them apart.

So: the triple barrier (Lopez de Prado 2018). Each observation is labelled by
which of three barriers the path touches first, walking the tape forward bar by
bar rather than sampling its endpoint.

**The barriers are scaled by volatility, not fixed in percent.** This is the
direct lesson of the sealed window: a fixed 3% entry bar is a different rule in a
quiet year than in a violent one, and 2026 refused 319,662 entries for exactly
that reason. A 2% target is a routine hour in one regime and an unreachable month
in another, so a label built on fixed percentages is really a label about the
volatility regime wearing a disguise.

**Every label carries the bar it ends on.** Nothing else in this package can
build an honest train/test split without it: two observations whose barrier
windows overlap share their outcome, so they are not two facts. `splits.py`
purges on this field and it is not optional.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Barriers:
    """The three ways a position can end, in units of the asset's own volatility.

    `target` and `stop` are multiples of the volatility estimate at entry.
    `horizon` is in bars and is the barrier that fires when neither price
    barrier does -- without it a quiet stretch produces labels that never
    resolve, and dropping those observations silently selects for volatility.
    """

    target: float = 2.0
    stop: float = 1.0
    horizon: int = 864  # three days at five minutes


def realised_volatility(close: np.ndarray, span: int = 288) -> np.ndarray:
    """An exponentially weighted estimate of one-bar return volatility.

    Exponential rather than a flat window because the barrier has to be set from
    what volatility is doing NOW; a 30-day flat mean lags a regime change by
    about fifteen days, which is precisely the interval where a fixed barrier
    stops meaning what it meant.

    Computed causally: the value at bar `i` uses returns up to and including `i`
    and never a bar after it. The recursion below is the whole reason this is
    written by hand rather than taken from a library call -- a centred or
    two-pass estimator would leak the future into every label built on it, and
    it would leak invisibly.
    """
    close = np.asarray(close, dtype=float)
    returns = np.zeros_like(close)
    returns[1:] = np.diff(close) / np.maximum(close[:-1], 1e-12)
    alpha = 2.0 / (span + 1.0)
    variance = np.zeros_like(close)
    running = 0.0
    for index in range(1, len(close)):
        running = alpha * returns[index] ** 2 + (1 - alpha) * running
        variance[index] = running
    # The first `span` bars have not seen enough returns for the estimate to
    # mean anything. NaN rather than a small number, so a caller that forgets to
    # drop them gets an error instead of a confident label built on nothing.
    volatility = np.sqrt(variance)
    volatility[:span] = np.nan
    return volatility


def triple_barrier(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volatility: np.ndarray,
    barriers: Barriers = Barriers(),
) -> dict[str, np.ndarray]:
    """Walk each bar's future forward until one of the three barriers is hit.

    Returns, per observation:

        label     +1 target first, -1 stop first, 0 time ran out
        ends_at   the bar index the outcome was decided on
        ret       the return actually earned by that resolution
        touched   False when the tape ran out before the horizon did

    **Highs and lows, not closes.** A stop is hit intrabar or it is not hit at
    all; scanning closes reports a position surviving a move that would have
    ended it, which is the flattering direction of the error and the reason
    backtests built this way do not reproduce.

    **The stop is checked before the target on the same bar.** When a single bar
    spans both barriers this is unknowable from OHLC alone -- the path inside the
    bar is not recorded -- so the assumption has to be chosen and stated rather
    than left to the order of two `if`s. The pessimistic reading is chosen: at
    five minutes a bar spanning both barriers is a violent one, and violent bars
    are exactly where an optimistic assumption does the most damage.
    """
    return _vectorised(high, low, close, volatility, barriers)


# THE BARRIER IS SCALED BY THE SQUARE ROOT OF THE HORIZON, and getting this
# wrong is not a detail -- it is the difference between a strategy and none.
#
# `volatility` is a ONE-BAR estimate. At five minutes that is about 0.002, so
# an unscaled "2 sigma" target is 0.4% against a 0.30% round trip: the toll
# eats three quarters of the prize and the cost filter correctly refuses
# almost everything. Measured, before this line existed: eight trades taken
# out of 319,000 test rows.
#
# Volatility accumulates with the square root of time, so a position held for
# `horizon` bars is exposed to sigma * sqrt(horizon) -- about 5.9% here, and
# a 2-sigma target becomes 11.7% against the same 0.30% toll. That is a trade
# worth paying for, and it is the same quantity the barriers were always
# meant to express.
#
# Rows processed per vectorised block. The working set is `block x horizon`
# booleans four times over -- about 70 MB at these defaults -- and the whole
# table at once would be 3.4 billion, so the chunking is what makes the
# vectorised path possible rather than merely tidier.
BLOCK = 20_000


def _vectorised(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volatility: np.ndarray,
    barriers: Barriers,
) -> dict[str, np.ndarray]:
    """The same walk, done with sliding windows instead of a nested loop.

    `_reference` below is the readable statement of the rule and the oracle this
    is tested against on random data. This exists because the loop was 37% of the
    time spent building an observation table -- 3.97 million rows by up to 864
    bars each -- and every experiment in this package pays it.

    The equivalence is not obvious, so here it is written out. Scanning j upward
    and checking the stop before the target is the same as: let `jd` be the first
    bar whose low breaches the stop and `ju` the first whose high reaches the
    target; the stop wins when `jd <= ju` and the target when `ju < jd`. The `<=`
    is where "stop checked first on the same bar" lives, and inverting it to `<`
    is a silently more flattering label set.

    The last `horizon` rows fall back to the reference: their window runs off the
    end of the tape and `min(i + horizon, n - 1)` makes each one a different
    length, which is exactly what a fixed-width sliding view cannot express. It is
    at most 864 rows of Python.
    """
    from numpy.lib.stride_tricks import sliding_window_view

    n = len(close)
    horizon = int(barriers.horizon)
    label = np.zeros(n, dtype=np.int8)
    ends_at = np.full(n, -1, dtype=np.int64)
    ret = np.full(n, np.nan)
    touched = np.zeros(n, dtype=bool)
    if n == 0:
        return {"label": label, "ends_at": ends_at, "ret": ret, "touched": touched}

    scale = np.sqrt(max(horizon, 1))
    sigma = np.asarray(volatility, dtype=float) * scale
    entry = np.asarray(close, dtype=float)
    usable = np.isfinite(sigma) & (sigma > 0) & np.isfinite(entry) & (entry > 0)

    up = entry * (1.0 + barriers.target * sigma)
    down = entry * (1.0 - barriers.stop * sigma)

    # Rows whose full window exists. `i + horizon <= n - 1`, so the window
    # low[i+1 .. i+horizon] is always `horizon` wide.
    full = n - 1 - horizon
    if full > 0 and horizon > 0:
        low_windows = sliding_window_view(np.asarray(low, dtype=float), horizon)
        high_windows = sliding_window_view(np.asarray(high, dtype=float), horizon)
        for start in range(0, full, BLOCK):
            stop_at = min(start + BLOCK, full)
            rows = np.arange(start, stop_at)
            rows = rows[usable[rows]]
            if not len(rows):
                continue
            # Window for row i starts at i+1. `sliding_window_view(x, h)[k]` is
            # x[k .. k+h-1], so the window wanted is at index i+1.
            lows = low_windows[rows + 1]
            highs = high_windows[rows + 1]
            hit_down = lows <= down[rows, None]
            hit_up = highs >= up[rows, None]
            any_down, any_up = hit_down.any(axis=1), hit_up.any(axis=1)
            # argmax on a boolean row is the first True, and 0 when there is
            # none -- which is why `any_*` is carried separately rather than
            # inferred from the index.
            first_down = np.where(any_down, hit_down.argmax(axis=1), horizon)
            first_up = np.where(any_up, hit_up.argmax(axis=1), horizon)

            stopped = any_down & (first_down <= first_up)
            targeted = any_up & ~stopped
            timed = ~stopped & ~targeted

            j_stop = rows[stopped] + 1 + first_down[stopped]
            label[rows[stopped]] = -1
            ends_at[rows[stopped]] = j_stop
            ret[rows[stopped]] = down[rows[stopped]] / entry[rows[stopped]] - 1
            touched[rows[stopped]] = True

            j_target = rows[targeted] + 1 + first_up[targeted]
            label[rows[targeted]] = 1
            ends_at[rows[targeted]] = j_target
            ret[rows[targeted]] = up[rows[targeted]] / entry[rows[targeted]] - 1
            touched[rows[targeted]] = True

            last = rows[timed] + horizon
            label[rows[timed]] = 0
            ends_at[rows[timed]] = last
            ret[rows[timed]] = close[last] / entry[rows[timed]] - 1
            touched[rows[timed]] = True

    # The tail, and any row the block loop skipped as unusable, by the reference.
    tail = _reference(
        high, low, close, volatility, barriers, first=max(full, 0), last=n - 1
    )
    edge = np.arange(max(full, 0), n)
    for key, values in (
        ("label", label),
        ("ends_at", ends_at),
        ("ret", ret),
        ("touched", touched),
    ):
        values[edge] = tail[key][edge]
    return {"label": label, "ends_at": ends_at, "ret": ret, "touched": touched}


def _reference(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volatility: np.ndarray,
    barriers: Barriers = Barriers(),
    first: int = 0,
    last: int | None = None,
) -> dict[str, np.ndarray]:
    """The rule as a nested loop: readable, slow, and the oracle for the fast path.

    Kept in the module rather than in the test file on purpose. It is the
    definition of the label, and a definition that lives only in a test is one
    that gets edited to match the implementation the day they disagree.
    """
    n = len(close)
    label = np.zeros(n, dtype=np.int8)
    ends_at = np.full(n, -1, dtype=np.int64)
    ret = np.full(n, np.nan)
    touched = np.zeros(n, dtype=bool)
    scale = np.sqrt(max(barriers.horizon, 1))
    stop_row = n - 1 if last is None else min(last, n - 1)

    for i in range(max(first, 0), stop_row + 1):
        sigma = volatility[i] * scale
        if not np.isfinite(sigma) or sigma <= 0:
            continue
        entry = close[i]
        if not np.isfinite(entry) or entry <= 0:
            continue
        up = entry * (1.0 + barriers.target * sigma)
        down = entry * (1.0 - barriers.stop * sigma)
        # Named `final` rather than `last`: `last` is now this function's own
        # parameter, and shadowing it worked only because `stop_row` happens to
        # be computed before the loop.
        final = min(i + barriers.horizon, n - 1)
        for j in range(i + 1, final + 1):
            if low[j] <= down:
                label[i], ends_at[i], ret[i], touched[i] = -1, j, down / entry - 1, True
                break
            if high[j] >= up:
                label[i], ends_at[i], ret[i], touched[i] = 1, j, up / entry - 1, True
                break
        else:
            # The horizon barrier. `touched` stays False only when the SERIES
            # ended early -- those observations are unresolved rather than
            # neutral, and training on them teaches the model that the end of
            # the dataset is a flat market.
            ends_at[i] = final
            ret[i] = close[final] / entry - 1
            touched[i] = final == i + barriers.horizon
            label[i] = 0
    return {"label": label, "ends_at": ends_at, "ret": ret, "touched": touched}


def net_of_costs(ret: np.ndarray, round_trip: float = 0.003) -> np.ndarray:
    """What the label is worth after the toll every real trade pays.

    0.30% is this project's invariant: 10 bps commission plus 5 bps slippage on
    each side. It belongs in the LABEL rather than only in the backtest, because
    a model trained on gross returns spends its capacity learning to predict
    moves too small to be worth taking, and then a cost filter throws away
    everything it learned. Teach it the net move and the small ones stop looking
    like opportunities.
    """
    return np.asarray(ret, dtype=float) - round_trip
