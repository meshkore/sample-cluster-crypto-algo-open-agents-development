"""Train/test splits that do not hand the model its own answer.

This is the file where machine learning on financial time series usually goes
wrong, and it goes wrong quietly: the model scores beautifully, the split is the
reason, and nothing in the metrics says so.

**Two leaks, both fatal, both invisible.**

*Overlap.* A label built with an 864-bar horizon depends on the 864 bars after
its observation. Bar 1,000 and bar 1,500 therefore share most of their future.
Put the first in train and the second in test and the model has seen the test
set's answer -- not approximately, literally, because the same price path
produced both labels. This laboratory has already been bitten by the same
arithmetic from the other direction: `edge.py` reported a signal at t = 6.7 that
was -1.4 once overlapping observations were thinned, because a 288-bar horizon
counted one day's move up to 288 times.

*Adjacency.* Even with overlap purged, the bar immediately after the training
cut is nearly the same market state as the bar immediately before it. An embargo
drops a band after each training block so the test set starts somewhere the
model has not effectively already seen.

**Walk-forward, never shuffled and never K-fold.** A random split trains on 2025
to predict 2019. It will score well. It is answering a question nobody can trade:
what a model would know if it already knew the future.

Both mechanisms are Lopez de Prado's (Advances in Financial Machine Learning,
ch. 7). The implementation is ours because the discipline has to be readable
here rather than trusted to a dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Fold:
    """One walk-forward fold, as index arrays into the observation table."""

    index: int
    train: np.ndarray
    test: np.ndarray
    purged: int
    embargoed: int

    def document(self) -> dict[str, int]:
        return {
            "fold": self.index,
            "train": int(len(self.train)),
            "test": int(len(self.test)),
            "purged": self.purged,
            "embargoed": self.embargoed,
        }


def purged_walk_forward(
    ends_at: np.ndarray,
    folds: int = 6,
    embargo: int = 864,
    minimum_train: int = 20_000,
) -> list[Fold]:
    """Expanding-window folds with overlapping labels purged and a gap embargoed.

    `ends_at[i]` is the bar observation `i`'s label was decided on -- the field
    `labels.triple_barrier` exists to produce. A training observation is dropped
    when its label resolves at or after the first bar of the test block: its
    outcome is partly the test set's price path, so keeping it is training on the
    answer.

    `embargo` additionally drops training observations in a band immediately
    before the test block. Adjacent bars are near-duplicates and purging alone
    does not remove them.

    Expanding rather than rolling: each fold trains on everything allowed so far.
    A rolling window would answer a different question -- how fast the edge decays
    -- which is worth asking separately and not by accident.
    """
    n = len(ends_at)
    ends_at = np.asarray(ends_at, dtype=np.int64)
    if folds < 1:
        raise ValueError("a walk-forward needs at least one fold")
    if n < minimum_train + folds:
        raise ValueError(
            f"{n} observations cannot support {folds} folds with a "
            f"{minimum_train}-observation minimum training block"
        )

    # Test blocks tile the tail of the series evenly. The first `minimum_train`
    # observations are training-only, because a fold whose model saw four
    # thousand bars is not a measurement of anything.
    span = (n - minimum_train) // folds
    out: list[Fold] = []
    for k in range(folds):
        test_start = minimum_train + k * span
        test_stop = n if k == folds - 1 else test_start + span
        test = np.arange(test_start, test_stop)

        candidate = np.arange(0, test_start)
        # PURGE: drop training rows whose label resolves inside the test block.
        resolves_before = ends_at[candidate] < test_start
        purged = int((~resolves_before).sum())
        candidate = candidate[resolves_before]
        # EMBARGO: drop the band immediately before the test block.
        embargoed = 0
        if embargo > 0 and len(candidate):
            keep = candidate < max(0, test_start - embargo)
            embargoed = int((~keep).sum())
            candidate = candidate[keep]
        if len(candidate) < minimum_train // 2:
            # A fold with almost no training data left is not a fold. Say so
            # rather than fitting on a thousand rows and reporting a score.
            continue
        out.append(
            Fold(
                index=k,
                train=candidate,
                test=test,
                purged=purged,
                embargoed=embargoed,
            )
        )
    if not out:
        raise ValueError(
            "every fold was emptied by purging; the label horizon is probably "
            "long relative to the data"
        )
    return out


def thin_to_independent(ends_at: np.ndarray) -> np.ndarray:
    """Indices of observations whose label windows do not overlap each other.

    For reporting a statistic, not for training. A model may train on
    overlapping observations -- it gains from the density and loses only
    efficiency -- but a t-statistic computed over them divides by a sample size
    that does not exist. When this package quotes a number with an error bar, it
    quotes it over these rows.
    """
    ends_at = np.asarray(ends_at, dtype=np.int64)
    kept: list[int] = []
    free_from = -1
    for i in range(len(ends_at)):
        if i > free_from:
            kept.append(i)
            free_from = int(ends_at[i])
    return np.array(kept, dtype=np.int64)
