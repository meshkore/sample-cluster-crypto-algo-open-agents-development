"""Rank a candidate on windows it was never fitted to.

`RESEARCH_CHARTER.md` names this the laboratory's central methodology problem.
Phase 1 sweeps parameters across 2017-2025 and then ranks that sweep on the same
2017-2025 bars, so fitting and selection read one dataset and the ranking
measures memorisation rather than edge. The measured cost is a +0.06 rank
correlation between Phase-1 rank and 2026 forward rank across 216 paired runs,
which is what drawing the winner at random would look like.

The replacement is deliberately plain: cut the history into consecutive
train/test folds, leave an embargo between them so a position open across the
boundary cannot carry information backwards, and score a candidate only on the
test halves. Aggregation is by median rather than mean because one spectacular
fold is the exact artefact the current protocol keeps promoting.

Two boundaries hold. Nothing here reads 2026; folds are built from a caller
supplied window and `HistoricalUniverseEvaluator` already stops at the lock.
And `rank_correlation` is reporting only, so a diagnostic computed against
forward results can never travel back into selection.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Sequence

from .backtest import CostModel
from .models import ENGINE_VERSION, Bar, utc_now
from .portfolio import LongOnlyPortfolioBacktester, MoneyManagement


# Starting estimates, not results. Charter open question 1 asks how long an edge
# survives before it decays, and these are the numbers that question is asked
# with: two years of training is long enough to cover a full crypto cycle leg,
# six months of testing is long enough to accumulate trades at daily bars.
DEFAULT_TRAIN_DAYS = 730
DEFAULT_TEST_DAYS = 182

# The charter describes Phase 1 as sweeping "the whole 2017-2025 history", so
# fold plans start where that history does. Assets listed later simply produce
# no bars in the early folds and are dropped from them.
HISTORY_START = datetime(2017, 1, 1, tzinfo=timezone.utc)

# Trade durations implied by the stop and take-profit distances sit well under
# three weeks, so an embargo of that length covers a position that was open when
# the training window ended.
DEFAULT_EMBARGO_DAYS = 21

# Below three folds the median is not a summary of anything, it is one number
# wearing a disguise.
MINIMUM_FOLDS = 3

# A candidate profitable in fewer than half its folds is a lottery ticket. This
# is a floor rather than a weight on purpose: weighting lets a single enormous
# fold buy back the failures, which is the behaviour being replaced.
MINIMUM_CONSISTENCY = 0.5


@dataclass(frozen=True)
class Fold:
    """One train window, an embargo, then the test window that scores it."""

    index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime

    @property
    def embargo(self) -> timedelta:
        return self.test_start - self.train_end

    def covers(self, moment: datetime) -> bool:
        """True when a bar falls inside the scored window."""
        return self.test_start <= moment < self.test_end


def rolling_folds(
    start: datetime,
    end: datetime,
    train_days: int = DEFAULT_TRAIN_DAYS,
    test_days: int = DEFAULT_TEST_DAYS,
    embargo_days: int = DEFAULT_EMBARGO_DAYS,
) -> tuple[Fold, ...]:
    """Consecutive train/test pairs over ``[start, end)``, oldest first.

    Boundaries come from the calendar and the arguments alone. They never
    depend on a result, so the fold plan cannot be tuned after seeing which
    split flatters a candidate.
    """
    if train_days <= 0 or test_days <= 0:
        raise ValueError("train and test windows must both be positive")
    if embargo_days < 0:
        raise ValueError("the embargo cannot be negative")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("fold boundaries must be timezone-aware")
    if start >= end:
        raise ValueError("the history window is empty")

    train = timedelta(days=train_days)
    test = timedelta(days=test_days)
    embargo = timedelta(days=embargo_days)

    folds: list[Fold] = []
    train_start = start
    while True:
        train_end = train_start + train
        test_start = train_end + embargo
        test_end = test_start + test
        if test_end > end:
            break
        folds.append(
            Fold(len(folds), train_start, train_end, test_start, test_end)
        )
        # Stepping by the test length makes the scored windows partition the
        # history instead of overlapping, so no bar is counted twice.
        train_start = train_start + test
    return tuple(folds)


@dataclass(frozen=True)
class FoldOutcome:
    """What one test window measured. Failures are kept, never discarded."""

    fold_index: int
    test_start: datetime
    test_end: datetime
    return_pct: float
    max_drawdown: float
    trades: int
    aborted: bool = False

    @property
    def score(self) -> float:
        """Criterion 10's risk-adjusted score, read out-of-sample."""
        return self.return_pct - self.max_drawdown

    @property
    def profitable(self) -> bool:
        return self.return_pct > 0 and not self.aborted


@dataclass(frozen=True)
class WalkForwardScore:
    folds_evaluated: int
    folds_profitable: int
    folds_aborted: int
    consistency: float
    median_score: float
    worst_score: float
    total_trades: int
    eligible: bool
    reason: str


def evaluate_folds(
    outcomes: Iterable[FoldOutcome],
    minimum_folds: int = MINIMUM_FOLDS,
    minimum_consistency: float = MINIMUM_CONSISTENCY,
    disqualify_on_abort: bool = True,
) -> WalkForwardScore:
    """Summarise test-fold outcomes into one selection score.

    ``disqualify_on_abort`` defaults to refusing any candidate that breached the
    25% drawdown stop in any fold. Criterion 7 already bars a breached trial from
    becoming a mutation parent; applying it per fold keeps that rule true
    out-of-sample rather than only on the aggregate.
    """
    ordered = sorted(outcomes, key=lambda item: item.fold_index)
    if not ordered:
        return WalkForwardScore(
            0, 0, 0, 0.0, 0.0, 0.0, 0, False, "no fold was evaluated"
        )

    scores = [item.score for item in ordered]
    profitable = sum(item.profitable for item in ordered)
    aborted = sum(item.aborted for item in ordered)
    consistency = profitable / len(ordered)

    enough_folds = len(ordered) >= minimum_folds
    survived = not (disqualify_on_abort and aborted)
    consistent = consistency >= minimum_consistency
    eligible = enough_folds and survived and consistent

    if not enough_folds:
        reason = f"only {len(ordered)} folds, {minimum_folds} required"
    elif not survived:
        reason = f"breached the drawdown stop in {aborted} of {len(ordered)} folds"
    elif not consistent:
        reason = (
            f"profitable in {profitable} of {len(ordered)} folds, "
            f"below the {minimum_consistency:.0%} floor"
        )
    else:
        reason = f"profitable in {profitable} of {len(ordered)} test folds"
    return WalkForwardScore(
        folds_evaluated=len(ordered),
        folds_profitable=profitable,
        folds_aborted=aborted,
        consistency=consistency,
        median_score=statistics.median(scores),
        worst_score=min(scores),
        total_trades=sum(item.trades for item in ordered),
        eligible=eligible,
        reason=reason,
    )


def _average_ranks(values: Sequence[float]) -> list[float]:
    """Ranks with ties averaged, which is what makes the correlation Spearman."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        last = position
        while last + 1 < len(order) and values[order[last + 1]] == values[order[position]]:
            last += 1
        shared = (position + last) / 2 + 1
        for index in range(position, last + 1):
            ranks[order[index]] = shared
        position = last + 1
    return ranks


def rank_correlation(pairs: Sequence[tuple[float, float]]) -> float | None:
    """Spearman correlation between a selection score and a later outcome.

    This is the instrument the laboratory is missing. The current protocol was
    caught by exactly this number (+0.06 against forward rank); any replacement
    should be held to it too. Returns ``None`` when there is too little data or
    one side never varies, because a correlation would be fabricated there.
    """
    if len(pairs) < 3:
        return None
    left = _average_ranks([pair[0] for pair in pairs])
    right = _average_ranks([pair[1] for pair in pairs])
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    covariance = sum(
        (a - mean_left) * (b - mean_right) for a, b in zip(left, right)
    )
    spread_left = sum((a - mean_left) ** 2 for a in left) ** 0.5
    spread_right = sum((b - mean_right) ** 2 for b in right) ** 0.5
    if spread_left == 0 or spread_right == 0:
        return None
    return covariance / (spread_left * spread_right)


def window_bars(
    bars_by_symbol: dict[str, list[Bar]], start: datetime, end: datetime
) -> dict[str, list[Bar]]:
    """Bars in ``[start, end)``, dropping assets too thin to simulate."""
    sliced: dict[str, list[Bar]] = {}
    for symbol, bars in bars_by_symbol.items():
        kept = [bar for bar in bars if start <= bar.timestamp < end]
        if len(kept) >= 3:
            sliced[symbol] = kept
    return sliced


class WalkForwardEvaluator:
    """Runs one candidate through every fold and reports the test windows only.

    Each fold is simulated from ``train_start`` so indicators warm on training
    bars, while ``trading_start`` holds the first fill back to ``test_start``.
    That is the same separation Phase 2 uses against the 2026 lock, which is why
    warm-up cannot become a trade in the window that scores the candidate.
    """

    def __init__(
        self,
        costs: CostModel,
        policy: MoneyManagement,
        initial_capital: float,
        folds: Sequence[Fold],
    ):
        if initial_capital <= 0:
            raise ValueError("positive capital is required")
        self.costs = costs
        self.policy = policy
        self.initial_capital = initial_capital
        self.folds = tuple(folds)

    def run(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        strategy_factory: Callable[[], Any],
        on_fold: Callable[[FoldOutcome], None] | None = None,
    ) -> list[FoldOutcome]:
        outcomes: list[FoldOutcome] = []
        for fold in self.folds:
            available = window_bars(
                bars_by_symbol, fold.train_start, fold.test_end
            )
            scored = window_bars(bars_by_symbol, fold.test_start, fold.test_end)
            # A fold with no tradable bar is skipped rather than recorded as a
            # flat result, which would otherwise read as a candidate that chose
            # to stay out of the market.
            if not available or not scored:
                continue
            engine = LongOnlyPortfolioBacktester(self.costs, self.policy)
            result = engine.run(
                available,
                strategy_factory,
                self.initial_capital,
                trading_start=fold.test_start,
            )
            outcome = FoldOutcome(
                fold_index=fold.index,
                test_start=fold.test_start,
                test_end=fold.test_end,
                return_pct=result.return_pct,
                max_drawdown=result.max_drawdown,
                trades=len(result.trades),
                aborted=result.aborted,
            )
            outcomes.append(outcome)
            if on_fold:
                on_fold(outcome)
        return outcomes


def record(
    memory: Any,
    strategy_number: int,
    outcomes: Sequence[FoldOutcome],
    score: WalkForwardScore,
    engine_version: int = ENGINE_VERSION,
) -> None:
    """Persist the fold evidence and its summary in one transaction.

    Individual folds are replaced rather than appended so a re-run of the same
    strategy cannot silently double its fold count, which would inflate
    consistency. The engine version travels with the rows because results from
    before a sizing fix stay readable for audit without staying eligible.
    """
    stamp = utc_now()
    with memory.transaction() as db:
        db.execute(
            "DELETE FROM walkforward_folds WHERE strategy_number=?",
            (strategy_number,),
        )
        for outcome in outcomes:
            db.execute(
                "INSERT INTO walkforward_folds VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    strategy_number,
                    outcome.fold_index,
                    outcome.test_start.isoformat(),
                    outcome.test_end.isoformat(),
                    outcome.return_pct,
                    outcome.max_drawdown,
                    outcome.trades,
                    int(outcome.aborted),
                    engine_version,
                    stamp,
                ),
            )
        db.execute(
            "INSERT OR REPLACE INTO walkforward_scores VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                strategy_number,
                score.folds_evaluated,
                score.folds_profitable,
                score.folds_aborted,
                score.consistency,
                score.median_score,
                score.worst_score,
                score.total_trades,
                int(score.eligible),
                score.reason,
                engine_version,
                stamp,
            ),
        )


def stored_score(memory: Any, strategy_number: int) -> WalkForwardScore | None:
    with memory.session() as db:
        row = db.execute(
            "SELECT * FROM walkforward_scores WHERE strategy_number=?",
            (strategy_number,),
        ).fetchone()
    if row is None:
        return None
    return WalkForwardScore(
        folds_evaluated=int(row["folds_evaluated"]),
        folds_profitable=int(row["folds_profitable"]),
        folds_aborted=int(row["folds_aborted"]),
        consistency=float(row["consistency"]),
        median_score=float(row["median_score"]),
        worst_score=float(row["worst_score"]),
        total_trades=int(row["total_trades"]),
        eligible=bool(row["eligible"]),
        reason=str(row["reason"]),
    )


def selection_diagnostic(memory: Any) -> dict[str, Any]:
    """Compare both selection protocols against the same forward outcomes.

    This is reporting, and the caller must keep it that way. The 2026 numbers
    read here rank the two protocols against each other; criterion 12 forbids
    them reaching training, parameters or mutation, and nothing in this function
    writes back.
    """
    with memory.session() as db:
        rows = db.execute(
            """SELECT f.strategy_number AS number, f.return_pct AS forward_return,
                      p.return_pct AS phase1_return, p.max_drawdown AS phase1_drawdown,
                      w.median_score AS walkforward_score, w.eligible AS eligible
               FROM forward_portfolio_runs f
               JOIN portfolio_backtest_runs p USING(strategy_number)
               LEFT JOIN walkforward_scores w USING(strategy_number)
               WHERE f.status='COMPLETE' AND p.status='COMPLETE'"""
        ).fetchall()

    in_sample = [
        (float(row["phase1_return"]) - float(row["phase1_drawdown"]),
         float(row["forward_return"]))
        for row in rows
    ]
    out_of_sample = [
        (float(row["walkforward_score"]), float(row["forward_return"]))
        for row in rows
        if row["walkforward_score"] is not None
    ]
    return {
        "paired_runs": len(rows),
        "in_sample_rank_correlation": rank_correlation(in_sample),
        "walkforward_paired_runs": len(out_of_sample),
        "walkforward_rank_correlation": rank_correlation(out_of_sample),
        "walkforward_eligible": sum(bool(row["eligible"]) for row in rows),
    }
