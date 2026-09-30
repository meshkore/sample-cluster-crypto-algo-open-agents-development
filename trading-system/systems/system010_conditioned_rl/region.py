"""R(t): the causal region where the best trades live. Task S10-6 fills this in.

The operator's idea, 2026-09-27: *"instead of applying it to the whole chart, to every
candle, to every moment of history, apply it only in the places and above all the CONDITIONS
in which 80% of the best trades have occurred."*

So the region is **fitted from the teacher, not from the learner's results**: run system 06's
zigzag oracle over the research years, take the top quantile of its swings by net return
after the 0.30% round trip, and ask which causal conditions hold on 80% of them. Everything
in that sentence is a constraint:

* **Causal.** The predicate reads only features available at the bar it judges. The oracle
  is hindsight and is the teacher; R must be computable live or it is not a region, it is a
  label.
* **Interpretable.** A shallow tree or a threshold set, printable as rules. The operator
  asked to see the conditions, and `tools/refusals.py` has to be able to price what R
  excludes. An opaque region would make the exclusion unauditable.
* **Fitted on years <= N-1** for each walk-forward year N, like everything else here.
* **Wide enough to trade.** The coverage per year is a deliverable: fraction of bars inside
  R, fraction of the best swings inside R, and the return actually capturable inside R under
  06's shipped exit rule. If the 80% region is too narrow for a three-slot book to deploy,
  it is widened until the feasibility bootstrap inside it passes, and the fraction of best
  trades given up is reported rather than quietly absorbed.

**Version zero already exists and must be scored first.** System 06's gates - the slow-trend
bit, breadth, the meta veto and Fear & Greed - are a hand-built region, and
`research/system06/tools/refusals.py` has already priced them: the entries they admit
returned +0.64% a trade against +0.19% (trend), +0.56% (breadth) and +0.38% (meta) for the
cohorts they refused, and in the sealed year every refused cohort was negative. A learned
region that cannot beat that table has not earned the name.
"""

from __future__ import annotations

def fit(years, quantile: float = 0.2, coverage: float = 0.8):
    """Fit R on the oracle's top-`quantile` swings in `years`, covering >= `coverage`."""
    raise NotImplementedError(_TODO)


def holds(features, at) -> bool:
    """Whether the region holds at one bar. Causal: reads only what `at` could have seen."""
    raise NotImplementedError(_TODO)


def coverage_table(years):
    """Per year: bars inside R, best swings inside R, and the return capturable inside R."""
    raise NotImplementedError(_TODO)


_TODO = (
    "S10-6 implements the region learner. Read .meshkore/context/system10-design.md and "
    ".meshkore/modules/trading-system/tasks/S10-6-locate-the-conditions.md first."
)
