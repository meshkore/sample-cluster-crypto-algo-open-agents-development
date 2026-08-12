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
    n = len(close)
    label = np.zeros(n, dtype=np.int8)
    ends_at = np.full(n, -1, dtype=np.int64)
    ret = np.full(n, np.nan)
    touched = np.zeros(n, dtype=bool)

    for i in range(n):
        sigma = volatility[i]
        if not np.isfinite(sigma) or sigma <= 0:
            continue
        entry = close[i]
        if not np.isfinite(entry) or entry <= 0:
            continue
        up = entry * (1.0 + barriers.target * sigma)
        down = entry * (1.0 - barriers.stop * sigma)
        last = min(i + barriers.horizon, n - 1)
        for j in range(i + 1, last + 1):
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
            ends_at[i] = last
            ret[i] = close[last] / entry - 1
            touched[i] = last == i + barriers.horizon
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
