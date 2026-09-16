"""Turn a probability track into a position track — with hysteresis, to stop churn.

The net predicts P(hold) per bar. Thresholding it at 0.5 makes the position flip
on every wobble across the line, and at 15 minutes that is thousands of round
trips a symbol — the 0.30% toll then eats everything, whatever the signal's edge.

Hysteresis fixes it the way a thermostat does: enter only when conviction is high
(`enter`), stay in until it is clearly gone (`exit_`, below `enter`), and never
sell within `min_hold` bars of buying. One band, one dead time, and the trade
count collapses from thousands to a number the toll can survive. The same
function scores validation in training and drives the brain live, so selection
and execution can never disagree about what the model would have done.
"""

from __future__ import annotations

import numpy as np


def positions_from_prob(
    prob: np.ndarray, enter: float = 0.5, exit_: float = 0.5, min_hold: int = 1
) -> np.ndarray:
    """1 while held, 0 while flat, walking the probabilities in time order.

    `enter >= exit_` is the hysteresis band; `min_hold` is a floor in bars on how
    long a position stays open once taken. With `enter == exit_ == 0.5` and
    `min_hold == 1` this is exactly the old 0.5 threshold, so the default changes
    nothing and the knobs only ever reduce trading.
    """
    prob = np.asarray(prob, dtype=float)
    n = len(prob)
    pos = np.zeros(n, dtype=np.int8)
    holding = False
    entry = -1
    for i in range(n):
        p = prob[i]
        if holding:
            if p <= exit_ and (i - entry) >= min_hold:
                holding = False
        elif p >= enter:
            holding = True
            entry = i
        pos[i] = 1 if holding else 0
    return pos
