"""Which language model may be asked about a given date, and which is the best one.

THE PROBLEM THIS EXISTS TO PREVENT

The operator wants a frontier model consulted at each rebalance: hand it a photograph of the
world - our indicators, the state of the book, the news, macro, collateral - and ask it to
validate or veto the trade. It is a good idea and it has one failure mode that would destroy
the entire project silently.

A language model has a knowledge cutoff. Ask a model whose training ran to May 2026 to
validate a trade dated February 2026 and it is not forecasting; it read what happened. The
backtest would be spectacular and worth nothing, and unlike every other form of look-ahead
this one is INVISIBLE IN THE CODE. There is no window to check, no timestamp to audit. The
leakage lives in the model's weights and nothing in a diff would ever show it.

THE OPERATOR'S SOLUTION, which is the right one

Route by date. For any date D, use the most capable model whose knowledge ENDS before D.
Early in a forward test only older models qualify; as the simulated clock advances past a
newer model's cutoff, that model becomes usable and the router upgrades to it. By the time
the test reaches the present, the best available model is legitimately in play - and in live
trading, where D is today, the newest model is always eligible because today is always after
every cutoff.

TWO RULES THAT MAKE THIS HONEST RATHER THAN DECORATIVE

  A CUTOFF MUST BE VERIFIED, NOT ASSUMED. An entry whose cutoff nobody has confirmed is
  marked unverified and the router REFUSES to return it, at any date. Guessing a cutoff to
  unlock a stronger model is the same mistake as reading the future, performed by hand.

  A CUTOFF IS A SMUDGE, NOT A WALL. Published cutoffs are approximate: data collected near
  the boundary, later documents describing earlier events, and post-training updates all
  blur it. So a model is eligible only once the date has cleared its cutoff by SAFETY_MONTHS.
  The buffer costs us the strongest model for a few extra months and removes the class of
  error we cannot detect afterwards.

This module decides eligibility only. It sends nothing, calls nothing and has no network
dependency, so it can be tested exhaustively without a key.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


# How far past a model's stated cutoff a date must be before that model may see it.
# Three months is a judgement, and it is deliberately generous: the cost of being wrong is
# a silently fraudulent backtest, and the cost of being conservative is using a slightly
# weaker model for one quarter.
SAFETY_MONTHS = 3


@dataclass(frozen=True)
class Model:
    """One candidate validator.

    `capability` orders models against each other - higher is stronger - and is used only to
    pick among those already eligible. It can never make an ineligible model eligible.

    `cutoff` is the last month the model's training data covers. `verified` records whether
    that date was actually confirmed rather than inferred from a version number or a release
    announcement, and an unverified entry is never returned.
    """

    model_id: str
    cutoff: date
    capability: int
    verified: bool
    source: str

    def eligible_for(self, day: date, safety_months: int = SAFETY_MONTHS) -> bool:
        if not self.verified:
            return False
        return day >= _add_months(self.cutoff, safety_months)


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    return date(year, month, 1)


# THE TABLE. Every row needs a verified cutoff and a source before it can be used, and most
# of these do not have one yet - which is why they are marked unverified and the router will
# refuse them. Filling this in is a research task, not a guess: the question to answer for
# each model is "what is the last month its training data covers, according to its own
# publisher", and the answer belongs in `source`.
#
# claude-opus-5 is the one row this agent can state first-hand rather than second-hand: its
# own operating context declares a knowledge cutoff of May 2026.
MODELS: tuple[Model, ...] = (
    Model("claude-opus-5", date(2026, 5, 1), capability=100, verified=True,
          source="stated in this agent's own operating context, 2026-09"),
    Model("claude-fable-5-1", date(2026, 5, 1), capability=95, verified=False,
          source="UNVERIFIED - asked blackmac-fable5 on the cluster; awaiting its answer"),
    Model("claude-haiku-4-5-20251001", date(2025, 10, 1), capability=60, verified=False,
          source="UNVERIFIED - the id is date-stamped 2025-10-01, which is a RELEASE date "
                 "and not a training cutoff; the two are routinely months apart"),
)


def eligible(day: date, models: tuple[Model, ...] = MODELS,
             safety_months: int = SAFETY_MONTHS) -> list[Model]:
    """Every model that may legitimately be asked about `day`, strongest first."""
    ok = [m for m in models if m.eligible_for(day, safety_months)]
    return sorted(ok, key=lambda m: (-m.capability, m.model_id))


def model_for(day: date, models: tuple[Model, ...] = MODELS,
              safety_months: int = SAFETY_MONTHS) -> Model | None:
    """The strongest model that cannot have read about `day`, or None if there is none.

    None is a real and expected answer, not a failure. It means this date cannot be
    validated by any model we have confirmed, and the honest response is to run the day
    WITHOUT the overlay rather than to reach for a model that might have seen it.
    """
    ok = eligible(day, models, safety_months)
    return ok[0] if ok else None


def coverage(start: date, end: date, models: tuple[Model, ...] = MODELS,
             safety_months: int = SAFETY_MONTHS) -> dict[str, int]:
    """How many months of a span each model would cover. For planning, before spending.

    Reported as months per model id, plus "none" for the months no verified model may see.
    A span whose "none" count is most of it is a span where this overlay cannot be tested
    honestly yet, and knowing that BEFORE paying for tokens is the point.
    """
    out: dict[str, int] = {}
    cur = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while cur <= last:
        m = model_for(cur, models, safety_months)
        key = m.model_id if m else "none"
        out[key] = out.get(key, 0) + 1
        cur = _add_months(cur, 1)
    return out
