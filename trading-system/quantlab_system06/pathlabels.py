"""Path-true labels: a bar is a good entry only if it survives OUR exit machinery.

The zigzag oracle labels (idea A60's diagnosis) are PATH-blind: a bar is labelled
"in-swing" if the swing it belongs to ends higher, even when the route passes
through a dip the shipped book's stop-loss would have realised as a loss. The net
is therefore trained to admire trades the strategy cannot hold.

This labeller replays the book's own exits forward from every bar: enter at the
bar's close, then exit at the FIRST touch of
  - the hard stop (`stop`, the shipped book's 8%),
  - the trailing stop (`trail`, 12% below the running peak since entry), or
  - the vertical barrier (`horizon` bars later),
and label the bar 1 only when the exit's net return clears `min_gain`. That is
the triple-barrier construction with our barriers: a positive label certifies
survival of the risk machinery the book actually runs.

Close-to-close simplification, stated: barriers are evaluated on closes, like the
zigzag labels, not on intrabar lows - both labellers see the same price series.
Fully causal in the training sense labels always are: label[i] uses only bars > i,
and training walk-forward split/embargo handles the leakage discipline.
"""

from __future__ import annotations

import numpy as np

# The shipped book's exit machinery (research/system06 best.json risk block).
STOP = 0.08
TRAIL = 0.12
HORIZON = 960          # 10 days of 15m bars - the champion's holds run days-weeks
MIN_GAIN = 0.01        # an exit must clear round-trip cost with margin to count

_BLOCK = 8192          # entries per vectorised block (memory: ~60MB per matrix)


def path_true_labels(close: np.ndarray, *, stop: float = STOP, trail: float = TRAIL,
                     horizon: int = HORIZON, min_gain: float = MIN_GAIN) -> np.ndarray:
    """Per-bar int8 labels: 1 = entering here survives our exits with net > min_gain.

    The last bars of the series have shortened forward windows (padded with the
    final close), which only makes their vertical barrier arrive early - the same
    trades the walk-forward's embargo excludes from training anyway.
    """
    close = np.asarray(close, dtype=float)
    n = close.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.int8)
    if n == 1:
        return np.zeros(1, dtype=np.int8)

    padded = np.concatenate([close, np.full(horizon, close[-1])])
    labels = np.zeros(n, dtype=np.int8)
    for i0 in range(0, n, _BLOCK):
        i1 = min(i0 + _BLOCK, n)
        rows = np.arange(i0, i1)
        # Forward windows start the bar AFTER entry: shape (block, horizon).
        idx = rows[:, None] + 1 + np.arange(horizon)[None, :]
        w = padded[idx]
        entry = close[rows][:, None]
        runmax = np.maximum.accumulate(np.maximum(w, entry), axis=1)
        hit = (w <= entry * (1.0 - stop)) | (w <= runmax * (1.0 - trail))
        first = np.argmax(hit, axis=1)
        any_hit = hit[np.arange(len(rows)), first]
        exit_i = np.where(any_hit, first, horizon - 1)
        ret = w[np.arange(len(rows)), exit_i] / close[rows] - 1.0
        labels[rows] = (ret >= min_gain).astype(np.int8)
    return labels
