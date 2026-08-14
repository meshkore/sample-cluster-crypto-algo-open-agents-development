"""How good a curve is for someone who did NOT invest on the first day.

Every score this laboratory has used ranks on final return, and final return
answers exactly one question: what happened to the person who bought at the
start and never looked. The operator asked the question that actually matters --
*what happens to someone who buys at the worst possible moment* -- and pointed at
the curve that made it obvious: flat for three years, everything earned in the
2021 bull run, 24% given back from the peak, four consecutive losing months, and
an ending below the high. Its final return was the best on the board.

Ranked by these measures that curve is what it looks like: a leveraged bet on one
year, not a strategy.

**The five properties, and why each is here.**

`worst_entry_return` -- the return of the UNLUCKIEST possible investor: buy at
the highest point, hold to the end. This is the operator's question stated
arithmetically, and it is the headline. A curve that ends below its own high has
a negative one, however large its total return.

`maximum_drawdown` -- the deepest peak-to-trough fall anywhere. What that
unluckiest investor lived through, and the operator's 25% mandate.

`ulcer_index` -- the root-mean-square of every drawdown, over every bar. A
maximum only records the single worst moment; the ulcer index records how much
of the whole life of the curve was spent underwater and how deep. Two curves can
share a maximum drawdown while one recovers in a week and the other stays down
for three years. Introduced by Martin and McCann (1989) for precisely this.

`longest_losing_months` -- the longest run of consecutive negative months. The
operator counted four on the champion, which is the kind of thing a single
annual figure hides completely.

`log_stability` -- the R-squared of log equity against time. Compounding at a
steady rate is a straight line in log space; a flat stretch followed by a spike
is not. This is what separates "grew" from "grew steadily", and no return-based
measure can see the difference.

**The score is a geometric mean, not a sum.** A weighted sum lets a spectacular return
buy its way past a catastrophic drawdown, which is how the current champion got
its seat. Multiplying means every property has a veto: anything near zero drags
the whole score there, and a curve has to be decent at all five to score at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

# The operator's mandate, and the point at which a curve stops being a candidate
# however well it scores elsewhere.
MANDATE = 0.25


@dataclass(frozen=True)
class Quality:
    """What a curve is worth to someone who might have bought at any point."""

    final_return: float
    worst_entry_return: float
    worst_entry_at: str | None
    maximum_drawdown: float
    ulcer_index: float
    longest_losing_months: int
    positive_months: float
    log_stability: float
    months: int

    @property
    def breaches_mandate(self) -> bool:
        return self.maximum_drawdown >= MANDATE

    def terms(self) -> dict[str, float]:
        """Each property on a 0-to-1 scale: 0 unacceptable, 1 excellent.

        Reported individually because a single number cannot tell an operator
        WHICH property failed, and every one of these is separately actionable.
        """
        return {
            "growth": _clamp(self.final_return / 3.0),
            "unlucky": _clamp((self.worst_entry_return + 0.10) / 0.60),
            "shallow": _clamp(1.0 - self.maximum_drawdown / MANDATE),
            "dry": _clamp(1.0 - self.ulcer_index / 0.15),
            "steady": _clamp(self.log_stability),
            "patient": _clamp(1.0 - (self.longest_losing_months - 1) / 6.0),
        }

    @property
    def score(self) -> float:
        """The GEOMETRIC MEAN of the six terms, so every property holds a veto.

        A weighted sum would let a spectacular return buy its way past a
        catastrophic drawdown -- which is exactly how a curve that gave back 24%
        from its peak and ended below its own high came to be called the
        champion. Multiplying removes that: anything near zero drags the whole
        score down, and a curve has to be decent at all six to score at all.

        The mean rather than the raw product because six fractions multiplied
        together land everything within a rounding error of zero, and a ranking
        that cannot separate its candidates is not a ranking. Same veto, readable
        scale: 0.5 means "middling at everything", not "excellent at five things
        and catastrophic at one".
        """
        if self.months < 12:
            return 0.0
        values = list(self.terms().values())
        if any(value <= 0.0 for value in values):
            return 0.0
        return math.exp(sum(math.log(value) for value in values) / len(values))

    def document(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "final_return": round(self.final_return, 4),
            "worst_entry_return": round(self.worst_entry_return, 4),
            "worst_entry_at": self.worst_entry_at,
            "maximum_drawdown": round(self.maximum_drawdown, 4),
            "ulcer_index": round(self.ulcer_index, 4),
            "longest_losing_months": self.longest_losing_months,
            "positive_months": round(self.positive_months, 3),
            "log_stability": round(self.log_stability, 3),
            "months": self.months,
            "breaches_mandate": self.breaches_mandate,
        }


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def worst_entry(equity: Sequence[float]) -> tuple[float, int]:
    """The return of the unluckiest investor, and the bar they bought on.

    Buy at some bar, hold to the end. The worst such buyer is the one who bought
    at the highest point -- so this is `final / max - 1`, and it is negative for
    any curve that ends below its own high.

    Reported as its own number rather than folded into drawdown because they
    answer different questions: a curve can have a deep drawdown in year two and
    still be far above it by year eight, and that investor was made whole. The
    one who bought at the peak was not.
    """
    if not equity:
        return 0.0, 0
    peak = max(equity)
    return equity[-1] / peak - 1.0, equity.index(peak)


def ulcer(equity: Sequence[float]) -> float:
    """Root-mean-square drawdown across every bar of the curve.

    Depth AND duration. A maximum drawdown is one moment; this is how much of the
    curve's whole life was spent below its high, which is what "invested at any
    point" actually exposes you to. Martin and McCann, 1989.
    """
    if not equity:
        return 0.0
    peak = equity[0]
    total = 0.0
    for value in equity:
        peak = max(peak, value)
        drop = 1.0 - value / peak if peak > 0 else 0.0
        total += drop * drop
    return math.sqrt(total / len(equity))


def monthly(stamps: Sequence[str], equity: Sequence[float]) -> list[tuple[str, float]]:
    """Month-end equity turned into monthly returns."""
    if not stamps or len(stamps) != len(equity):
        return []
    ends: dict[str, float] = {}
    for stamp, value in zip(stamps, equity):
        ends[str(stamp)[:7]] = value
    months = sorted(ends)
    out: list[tuple[str, float]] = []
    previous = None
    for month in months:
        value = ends[month]
        if previous is not None and previous > 0:
            out.append((month, value / previous - 1.0))
        previous = value
    return out


def losing_streak(returns: Sequence[tuple[str, float]]) -> int:
    """The longest run of consecutive negative months.

    The operator counted four on the champion. An annual figure cannot show it,
    and a maximum drawdown does not either -- a fall can be one violent week or
    four grinding months, and they are very different to live through.
    """
    longest = run = 0
    for _, value in returns:
        run = run + 1 if value < 0 else 0
        longest = max(longest, run)
    return longest


def stability(equity: Sequence[float]) -> float:
    """R-squared of log equity against time: is the growth a line or a spike?

    Steady compounding is a straight line in log space. A curve that is flat for
    three years, leaps in one, and gives a quarter of it back is not, and this is
    the only measure here that can tell those apart -- both can share a final
    return, a drawdown, even an ulcer index.
    """
    points = [
        (index, math.log(value)) for index, value in enumerate(equity) if value > 0
    ]
    if len(points) < 3:
        return 0.0
    n = len(points)
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in points)
    sxx = sum((x - mean_x) ** 2 for x, _ in points)
    syy = sum((y - mean_y) ** 2 for _, y in points)
    if sxx <= 0 or syy <= 0:
        return 0.0
    r_squared = (sxy * sxy) / (sxx * syy)
    # A curve that trends DOWN fits a line beautifully and deserves nothing.
    return r_squared if sxy > 0 else 0.0


def judge(stamps: Sequence[str], equity: Sequence[float]) -> Quality:
    """Score one equity curve on all five properties."""
    if not equity:
        return Quality(0.0, 0.0, None, 0.0, 0.0, 0, 0.0, 0.0, 0)
    unlucky, at = worst_entry(equity)
    months = monthly(stamps, equity)
    positive = (
        sum(1 for _, value in months if value > 0) / len(months) if months else 0.0
    )
    peak = equity[0]
    deepest = 0.0
    for value in equity:
        peak = max(peak, value)
        deepest = max(deepest, 1.0 - value / peak if peak > 0 else 0.0)
    return Quality(
        final_return=equity[-1] / equity[0] - 1.0 if equity[0] > 0 else 0.0,
        worst_entry_return=unlucky,
        worst_entry_at=str(stamps[at])[:10] if at < len(stamps) else None,
        maximum_drawdown=deepest,
        ulcer_index=ulcer(equity),
        longest_losing_months=losing_streak(months),
        positive_months=positive,
        log_stability=stability(equity),
        months=len(months),
    )
