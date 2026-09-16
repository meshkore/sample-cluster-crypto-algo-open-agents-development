"""What one 15-minute candle says, and whether it says enough to pay for itself.

Everything here is a function of columns the instrument already serves. Nothing
is recomputed and nothing is remembered: a `Reading` is derived from one tick's
candle and one tick's indicator row, so it cannot look forward even by
accident. The stateful part of the system -- the volatility history and the
bar counters -- lives in `context.py` and `reversion.py`, where it can be
reset and reasoned about separately.

**The mechanism, stated so it can be refuted.** A 15-minute bar that closes
near its low, well below its own 20-bar VWAP, on a range wide against its ATR,
is a bar in which market orders consumed the resting bids. Whoever replaces
that liquidity is paid for it over the following bars. That is a *liquidity
premium*, not a directional forecast, and the distinction is the whole reason
this system exists: a liquidity premium is paid by impatient traders in any
market, while the daily system's edge needs a trend to lean on and therefore
cannot work in the half of the cycle that falls.

The prediction that makes it falsifiable: the edge should be roughly as large
in bear blocks as in bull blocks. If it is not, this is the daily system again
in an expensive disguise, and the honest move is to say so.

**Why every threshold is in ATR units rather than percent.** BTC's typical
15-minute range in 2018 and in 2026 differ by more than a factor of three. A
percentage threshold is therefore a different rule in each era and would fit
itself to whichever era it was chosen in; an ATR multiple is the same rule
everywhere. The one threshold that is NOT in ATR units is the cost hurdle, and
for the opposite reason: costs are quoted in percent and do not care about
volatility, so comparing them to anything else would be the mistake.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Reading:
    """One symbol, one bar, reduced to the six numbers the rule needs."""

    symbol: str
    close: float
    atr: float
    # Distance below the anchor, expressed twice: in ATR units for the rule,
    # in percent for the cost comparison. Positive means the close is BELOW
    # the anchor, which is the direction this system buys.
    displacement_atr: float
    displacement_pct: float
    # Where the close sits inside the bar's own range. 0.0 is a close on the
    # low. This is the served `internal_bar_strength` column: a continuous
    # measure of the thing a candlestick pattern only names.
    ibs: float
    rsi_fast: float
    turnover: float

    @property
    def anchor_gap(self) -> float:
        """What the trade is trying to capture, in percent of price."""
        return self.displacement_pct


@dataclass(frozen=True)
class Verdict:
    """Whether a bar qualifies, and -- when it does not -- which gate refused.

    The reason is not decoration. A run that takes no trades and a run whose
    every candidate failed the cost hurdle look identical in the summary, and
    this laboratory has already lost time to that ambiguity once. The counts
    are reported at the end of every run.
    """

    ok: bool
    reason: str


def _value(row: dict[str, Any], key: str) -> float | None:
    """A served column, or None while its window is still filling.

    `None` is never coerced to zero here. A rule comparing a warm-up bar
    against zero reads it as a screaming signal, which is exactly how a
    laboratory manufactures an edge that does not exist.
    """
    value = row.get(key)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def read(
    symbol: str,
    candle: dict[str, Any],
    row: dict[str, Any],
    anchor_key: str = "vwap_rolling",
    atr_key: str = "atr_14",
    rsi_key: str = "rsi_2",
    turnover_key: str = "dollar_volume_20",
) -> Reading | None:
    """Reduce a tick to a `Reading`, or None if any column is still warming."""
    close = _value(candle, "close")
    anchor = _value(row, anchor_key)
    atr = _value(row, atr_key)
    rsi = _value(row, rsi_key)
    turnover = _value(row, turnover_key)
    if close is None or anchor is None or atr is None or rsi is None:
        return None
    if close <= 0 or atr <= 0:
        return None
    ibs = _value(row, "internal_bar_strength")
    if ibs is None:
        # The one fallback in this module, and it is exact rather than
        # approximate: IBS is a function of this bar's own high, low and close,
        # so deriving it from the candle is the same arithmetic the panel does.
        high, low = _value(candle, "high"), _value(candle, "low")
        if high is None or low is None or high <= low:
            return None
        ibs = (close - low) / (high - low)
    return Reading(
        symbol=symbol,
        close=close,
        atr=atr,
        displacement_atr=(anchor - close) / atr,
        displacement_pct=(anchor - close) / close,
        ibs=ibs,
        rsi_fast=rsi,
        turnover=turnover if turnover is not None else 0.0,
    )


def qualifies(
    reading: Reading,
    *,
    minimum_displacement_atr: float,
    maximum_ibs: float,
    maximum_rsi: float,
    cost_hurdle_pct: float,
    minimum_turnover: float,
) -> Verdict:
    """Does this bar qualify as a liquidity event worth paying to absorb?

    The four gates are deliberately independent, and the order they are checked
    in is the order of how much each one costs to be wrong about.

    1. **Turnover.** The capacity invariant. Never relaxed to make a thin-asset
       result look good.
    2. **The cost hurdle.** What the trade is trying to capture must be worth
       more than a multiple of what the round trip costs. This is the gate that
       does not exist in the daily system and without which a 15-minute rule
       trades a guaranteed loss with a random overlay -- and it is checked
       before the shape gates because a bar that cannot pay is not a candidate
       whatever it looks like.
    3. **Displacement.** How far below fair value, in the bar's own volatility
       units. This is the size of the dislocation.
    4. **Exhaustion.** Where the close sits in the bar, and the fast RSI. This
       is the evidence that the sellers are done rather than starting -- the
       difference between absorbing a liquidity demand and catching a knife.
    """
    if reading.turnover < minimum_turnover:
        return Verdict(False, "turnover")
    if reading.displacement_pct < cost_hurdle_pct:
        return Verdict(False, "cost_hurdle")
    if reading.displacement_atr < minimum_displacement_atr:
        return Verdict(False, "displacement")
    if reading.ibs > maximum_ibs:
        return Verdict(False, "ibs")
    if reading.rsi_fast > maximum_rsi:
        return Verdict(False, "rsi")
    return Verdict(True, "qualified")
