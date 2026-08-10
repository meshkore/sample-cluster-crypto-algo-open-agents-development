"""Rules from the literature, so the search starts from knowledge.

A genetic search that begins from random trees has to rediscover, by mutation,
things people wrote down decades ago. That is expensive and it is unnecessary:
a seed is not an answer, it is a starting point the search is free to move away
from, and a population that contains one good idea converges faster than one
that contains none.

These are seeds and NOT defaults. Nothing here is adopted because it is
famous. Each was measured on this laboratory's own folds before it was written
down (`orchestrator-manager/scripts/bounce_shootout.py`, recorded as H-L078B),
and the thresholds are round numbers taken from the source rather than fitted
values -- which is exactly why they belong in a population that will move them.

WHAT THE MEASUREMENT SAID, 2018-2026, eight years, all three branches, so the
regime label could not gate the answer:

    variant                8yr total  worst dd  legal   2024-2026
    Kotegawa naive              6.7%     40.8%  no         -9.55%
    + strong close            -43.7%     36.9%  no        -20.43%
    + heavy volume             48.3%     24.7%  YES       -21.25%
    + both                     15.0%     18.5%  YES        -3.67%
    Connors RSI(2)             26.7%     35.6%  no         +7.77%
    capitulation reversal       0.4%     15.0%  YES        +2.04%
    engulfing in a dip          4.2%     24.5%  YES       -11.36%

Three readings, and the second one surprised me:

  * VOLUME is the confirmation that makes the deviation trade legal. Kotegawa's
    dislocation alone breaches the 30% mandate; the same trade filtered by
    heavy volume is the best performer in the set and inside the mandate.
  * THE STRONG CLOSE ALONE MAKES IT WORSE, -43.7% against +6.7%. Candle shape
    is a risk control, not a return generator: added ON TOP of volume it takes
    drawdown from 24.7% to 18.5% and return from 48.3% to 15.0%.
  * ONLY THE CAPITULATION REVERSAL is both legal and positive in the falling
    fold. It is also nearly inert -- forty trades in eight years for +0.4%.

So none of these is a strategy yet. They are the shapes worth breeding from.
"""

from __future__ import annotations

from typing import Any


def col(name: str) -> dict[str, Any]:
    return {"t": "col", "name": name}


def num(value: float) -> dict[str, Any]:
    return {"t": "num", "v": value}


def below(name: str, value: float) -> dict[str, Any]:
    return {"t": "lt", "a": col(name), "b": num(value)}


def above(name: str, value: float) -> dict[str, Any]:
    return {"t": "gt", "a": col(name), "b": num(value)}


def every(*terms: dict[str, Any]) -> dict[str, Any]:
    return {"t": "and", "xs": list(terms)}


def either(*terms: dict[str, Any]) -> dict[str, Any]:
    return {"t": "or", "xs": list(terms)}


# Entry seeds by module. The exit half is deliberately not seeded: an entry is
# a claim about when an edge appears, and this laboratory has measured that the
# exit is worth more than the entry (QUANT13, +26.7 points on exit distance
# alone). Handing the search a fixed exit alongside a good entry would pin the
# more valuable half.
BOUNCE_SEEDS: tuple[dict[str, Any], ...] = (
    # The one that survived the falling fold. Big one-bar drop, heavy volume,
    # closed in the upper half of its range: capitulation with a buyer in it.
    every(
        below("return_1", -0.08),
        above("volume_ratio_20", 3.0),
        above("internal_bar_strength", 0.5),
    ),
    # Kotegawa's deviation rate with the confirmation that made it legal.
    every(below("distance_to_sma_20", -0.25), above("volume_ratio_20", 2.5)),
    # The same, with the risk control on top: lower return, lower drawdown.
    every(
        below("distance_to_sma_20", -0.25),
        above("internal_bar_strength", 0.6),
        above("volume_ratio_20", 2.0),
    ),
    # Connors. Illegal as written -- 35.6% drawdown -- and the best performer
    # in the falling fold by a distance, which makes it exactly the kind of
    # thing a search should be allowed to tame rather than be denied.
    below("rsi_2", 5.0),
    # Two down closes into a dislocation: Connors' trigger and Kotegawa's
    # setup, which the catalogue could not express before VERSION 4.
    every(above("down_streak", 2.0), below("distance_to_sma_20", -0.15)),
    # The band touch with participation, rather than the band touch alone.
    every(below("bb_percent_b", 0.05), above("volume_ratio_20", 2.0)),
)

TREND_SEEDS: tuple[dict[str, Any], ...] = (
    # Breakout with trend structure and strength behind it.
    every(
        {"t": "cross_up", "a": {"t": "px", "name": "close"}, "b": col("high_20")},
        {"t": "gt", "a": col("ema_50"), "b": col("ema_200")},
        above("adx", 25.0),
    ),
    # Reclaiming the long average on volume: the start of a trend rather than
    # the middle of one.
    every(
        {"t": "cross_up", "a": {"t": "px", "name": "close"}, "b": col("sma_200")},
        above("volume_ratio_20", 1.5),
    ),
)

BY_MODULE: dict[str, tuple[dict[str, Any], ...]] = {
    # The bear branch is where a bounce belongs, and where the operator asked
    # for it.
    "BEAR": BOUNCE_SEEDS,
    # A dislocation in a range reverts to the middle of the range, which is the
    # same trade with a nearer target.
    "SIDEWAYS": BOUNCE_SEEDS,
    "BULL": TREND_SEEDS,
}


def seeds_for(module: str, limit: int = 4) -> list[dict[str, Any]]:
    """Starting points for this module's search, or nothing if it has none.

    DETECTOR and POLICY move numbers rather than rule trees, so they get an
    empty list rather than an irrelevant one.
    """
    return list(BY_MODULE.get(module.upper(), ())[:limit])
