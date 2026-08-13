"""The model, and the filter that decides whether its opinion is worth 30 bps.

**It predicts which barrier gets hit, not the return.** Three classes -- target
first, stop first, timed out -- because the payoff of the first two is KNOWN at
entry: the barriers are volatility multiples, so a target hit pays
`target * sigma` and a stop pays `-stop * sigma` whatever the asset and whatever
the year. That turns a probability into an expected value without asking the
model to predict a magnitude, which is the part it is worst at.

    E[net] = p_up * target * sigma  -  p_down * stop * sigma  -  round_trip

**The filter is the strategy.** A 2026 walk-forward over 70k hourly BTC bars
found sign prediction profitable gross and dead at 10 bps, recovering only when
trades were restricted to forecasts large enough to clear the cost -- turnover
collapses and what is left pays (arXiv 2606.00060). This laboratory charges 30
bps, so the same logic applies three times harder. `E[net] > margin` is the whole
execution rule and there is deliberately nothing else in it.

**Gradient-boosted trees, not a network.** The same study compared XGBoost, LSTM
and iTransformer on this exact problem and the neural models lost, without
statistical dominance either way. On tabular features of this size that is the
expected result, and a model an operator can interrogate for feature importance
is worth more here than one that cannot be.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .splits import Fold, purged_walk_forward, thin_to_independent

# Classes in a fixed order. Written down because the probability columns are
# indexed by it downstream, and a silent reordering would swap the sign of every
# expected value while every metric kept reporting normally.
CLASSES = (-1, 0, 1)


@dataclass
class FoldResult:
    fold: int
    train_rows: int
    test_rows: int
    taken: int
    accuracy: float
    mean_net: float
    mean_net_taken: float
    t_star: float
    independent: int
    purged: int
    embargoed: int

    def document(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class WalkForward:
    folds: list[FoldResult] = field(default_factory=list)
    importance: list[tuple[str, float]] = field(default_factory=list)
    margin: float = 0.0

    def summary(self) -> dict[str, Any]:
        if not self.folds:
            return {"folds": 0}
        taken = np.array([f.taken for f in self.folds], dtype=float)
        net = np.array([f.mean_net_taken for f in self.folds], dtype=float)
        weighted = float((net * taken).sum() / taken.sum()) if taken.sum() else 0.0
        return {
            "folds": len(self.folds),
            "margin": self.margin,
            "trades_taken": int(taken.sum()),
            "take_rate": float(taken.sum() / sum(f.test_rows for f in self.folds)),
            "mean_net_per_trade": weighted,
            "folds_positive": int((net > 0).sum()),
            "worst_fold_net": float(net.min()),
            "best_fold_net": float(net.max()),
            "mean_t_star": float(np.mean([f.t_star for f in self.folds])),
            "accuracy": float(np.mean([f.accuracy for f in self.folds])),
        }


def build_classifier(seed: int = 42, **kwargs: Any):
    """The estimator, in one place so every fold is fitted identically."""
    from xgboost import XGBClassifier

    params = dict(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        # Financial features are collinear and the signal is faint. Regularise
        # hard: the failure mode here is a model that fits the training folds
        # beautifully and produces a take-rate of zero out of sample.
        reg_lambda=5.0,
        min_child_weight=50,
        tree_method="hist",
        random_state=seed,
        n_jobs=-1,
    )
    params.update(kwargs)
    return XGBClassifier(**params)


def expected_net(
    probabilities: np.ndarray,
    sigma: np.ndarray,
    target: float,
    stop: float,
    round_trip: float,
) -> np.ndarray:
    """Turn class probabilities into the number the filter compares to zero.

    The timed-out class contributes nothing to the payoff: its return is whatever
    the drift did, which is not knowable at entry and is small next to the
    barriers. Leaving it at zero is the conservative reading -- it makes the
    filter demand that the barriers themselves justify the trade.
    """
    down = probabilities[:, CLASSES.index(-1)]
    up = probabilities[:, CLASSES.index(1)]
    # `sigma` must already carry the sqrt(horizon) scaling the barriers were set
    # with. Pricing a one-bar sigma against a barrier placed at sigma*sqrt(H)
    # understates the payoff by a factor of ~29 at five minutes, and the filter
    # then refuses every trade while every other metric reads normally.
    return up * target * sigma - down * stop * sigma - round_trip


def evaluate(
    observations: Any,
    sigma: np.ndarray,
    margin: float = 0.0,
    folds: int = 6,
    embargo: int = 864,
    minimum_train: int = 20_000,
    seed: int = 42,
    **model_kwargs: Any,
) -> WalkForward:
    """Fit and test fold by fold, and report what a trader would have earned.

    `accuracy` is reported and is close to meaningless on its own -- a model
    predicting "stop" every time scores well when stops are common and earns
    nothing. `mean_net_per_trade` over the rows the filter TOOK is the number
    that matters, and `t_star` is computed on non-overlapping rows only, because
    an overlapping t-statistic is what turned a -1.4 into a 6.7 in this
    laboratory once already.
    """
    X, y, ret, ends_at = (
        observations.X,
        observations.y,
        observations.ret,
        observations.ends_at,
    )
    barriers = observations.meta.get("barriers", {})
    target = float(barriers.get("target", 2.0))
    stop = float(barriers.get("stop", 1.0))
    round_trip = float(observations.meta.get("round_trip", 0.003))

    out = WalkForward(margin=margin)
    importance = np.zeros(X.shape[1])
    splits: list[Fold] = purged_walk_forward(
        ends_at, folds=folds, embargo=embargo, minimum_train=minimum_train
    )

    for fold in splits:
        model = build_classifier(seed=seed, **model_kwargs)
        # XGBoost requires labels 0..k-1 over the classes ACTUALLY PRESENT, and
        # at an 864-bar horizon with 2-sigma barriers the timeout class never
        # occurs -- so the present classes are {-1, +1} and a fixed 0/1/2 mapping
        # hands it [0, 2] and it refuses. Mapping per fold, then widening the
        # probabilities back to the full CLASSES order with zeros for whatever
        # was absent, keeps `expected_net` indexable by a constant and keeps a
        # fold that happens to contain a timeout from silently shifting columns.
        present = sorted({int(v) for v in y[fold.train]})
        encode = {label: i for i, label in enumerate(present)}
        model.fit(X[fold.train], np.array([encode[int(v)] for v in y[fold.train]]))
        narrow = model.predict_proba(X[fold.test])
        probabilities = np.zeros((len(narrow), len(CLASSES)))
        for label, column in encode.items():
            probabilities[:, CLASSES.index(label)] = narrow[:, column]
        value = expected_net(probabilities, sigma[fold.test], target, stop, round_trip)
        take = value > margin
        predicted = np.array([CLASSES[i] for i in probabilities.argmax(axis=1)])

        taken_returns = ret[fold.test][take]
        # The error bar, on non-overlapping rows only. BOTH arguments are in
        # absolute table-row space: the taken rows themselves and the rows their
        # labels end on. Rebasing one and not the other -- which this line used
        # to do -- compares a position in the 15% subset against an index over
        # the whole fold and produces a statistic that measures nothing.
        rows = fold.test[take]
        independent = (
            thin_to_independent(ends_at[rows], rows) if len(rows) else np.array([], int)
        )
        sample = taken_returns[independent] if len(independent) else np.array([])
        t_star = (
            float(sample.mean() / (sample.std(ddof=1) / np.sqrt(len(sample))))
            if len(sample) > 2 and sample.std(ddof=1) > 0
            else 0.0
        )

        out.folds.append(
            FoldResult(
                fold=fold.index,
                train_rows=len(fold.train),
                test_rows=len(fold.test),
                taken=int(take.sum()),
                accuracy=float((predicted == y[fold.test]).mean()),
                mean_net=float(np.nanmean(ret[fold.test])),
                mean_net_taken=float(np.nanmean(taken_returns)) if take.any() else 0.0,
                t_star=t_star,
                independent=len(independent),
                purged=fold.purged,
                embargoed=fold.embargoed,
            )
        )
        booster = getattr(model, "feature_importances_", None)
        if booster is not None:
            importance += np.asarray(booster, dtype=float)

    order = np.argsort(importance)[::-1]
    out.importance = [
        (observations.names[i], float(importance[i] / max(len(splits), 1)))
        for i in order[:25]
    ]
    return out
