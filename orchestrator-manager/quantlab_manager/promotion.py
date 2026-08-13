"""What a system must do to become the record. One rule, checkable, in one place.

Written after a candidate was announced as the record on its sealed 2026 figure
alone. `itsm-h04` returned +10.77% in the sealed window against the incumbent's
+5.05% and was published as the winner -- while its training half had breached the
drawdown mandate and stopped **in July 2021**, three and a half years into an
eight-year era. It had no evidence at all for 2021-07 to 2025-12, and the
month-by-month table said so plainly: 21 months up, 19 down, 49% of traded months
positive, and then nothing.

The operator's rule, and it is the right one: **a system has to win in both
periods.** Not one, not the average. The three tests below are that rule.

**1. It must survive the whole research era.** A run that aborts has not been
measured on the years after it aborted, and the missing years are not neutral --
they are the years the rule could not survive. This is the test the previous three
records all failed.

**2. It must beat the incumbent in the sealed window.** 2026 is untouched forward
data, which is what makes it the evaluation, and a candidate that cannot beat the
standing record there has not earned the seat.

**3. It must be within 15% of the best training result.** Not the best -- within
tolerance of it. A rule that survives the whole era at slightly lower return is
worth more than one that scores higher over half of it, and demanding the maximum
on both axes would select for a curve that happens to fit both, which is how a
laboratory ends up with a champion that dies in year four.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

# How far below the best training return a candidate may sit and still qualify.
# The operator's number: near the previous winner is good enough when the rest of
# the record is better.
TRAINING_TOLERANCE = 0.15

# The research era's last day. A training run whose last activity is well before
# this did not survive it, whatever its status column says.
RESEARCH_ENDS = "2025-12-31"

# How much of the final year a surviving run must reach. A run that stops in
# November 2025 is not meaningfully different from one that reaches December;
# one that stops in 2021 is a different strategy from the one being claimed.
SURVIVAL_GRACE_DAYS = 120


@dataclass(frozen=True)
class Verdict:
    """Why a candidate is or is not the record. Every clause reported."""

    survives_training: bool
    beats_incumbent: bool
    training_within_tolerance: bool
    reasons: tuple[str, ...]

    @property
    def promotable(self) -> bool:
        return (
            self.survives_training
            and self.beats_incumbent
            and self.training_within_tolerance
        )

    def document(self) -> dict[str, Any]:
        return {
            "promotable": self.promotable,
            "survives_training": self.survives_training,
            "beats_incumbent": self.beats_incumbent,
            "training_within_tolerance": self.training_within_tolerance,
            "reasons": list(self.reasons),
        }


def _days_short(last_active: str | None) -> int | None:
    """How many days before the end of the research era the run went quiet."""
    if not last_active:
        return None
    try:
        stopped = datetime.fromisoformat(str(last_active).replace("Z", "+00:00"))
        ends = datetime.fromisoformat(f"{RESEARCH_ENDS}T00:00:00+00:00")
    except ValueError:
        return None
    return (ends - stopped.replace(tzinfo=ends.tzinfo)).days


def judge(
    training: dict[str, Any],
    sealed: dict[str, Any],
    incumbent_sealed_return: float,
    best_training_return: float,
) -> Verdict:
    """Apply the three tests. `training` and `sealed` are stored run rows.

    `best_training_return` is the best among systems that SURVIVE the era, not the
    best overall -- comparing a survivor against a run that aborted at its peak
    would hold the honest candidate to a number the other one only reached by
    stopping before it gave it back.
    """
    reasons: list[str] = []

    aborted = bool(training.get("aborted")) or training.get("status") in (
        "stopped",
        "aborted",
    )
    short = _days_short(training.get("last_active_timestamp"))
    survives = not aborted and (short is None or short <= SURVIVAL_GRACE_DAYS)
    if aborted:
        reasons.append(
            f"training aborted ({training.get('abort_reason') or 'no reason recorded'})"
        )
    elif short is not None and short > SURVIVAL_GRACE_DAYS:
        reasons.append(
            f"training went quiet {short} days before {RESEARCH_ENDS}, "
            f"so the last years are unmeasured"
        )

    sealed_return = float(sealed.get("return_pct") or 0.0)
    beats = sealed_return > incumbent_sealed_return
    if not beats:
        reasons.append(
            f"sealed {sealed_return:+.2%} does not beat the incumbent's "
            f"{incumbent_sealed_return:+.2%}"
        )

    training_return = float(training.get("return_pct") or 0.0)
    floor = best_training_return - abs(best_training_return) * TRAINING_TOLERANCE
    within = training_return >= floor
    if not within:
        reasons.append(
            f"training {training_return:+.2%} is more than "
            f"{TRAINING_TOLERANCE:.0%} below the best survivor's "
            f"{best_training_return:+.2%}"
        )

    if not reasons:
        reasons.append("passes all three tests")
    return Verdict(survives, beats, within, tuple(reasons))
