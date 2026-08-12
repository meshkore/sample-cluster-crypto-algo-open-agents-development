"""When NOT to buy the dislocation: the vetoes, and why each is allowed to exist.

A reversion system dies in exactly one way, and it is well enough known that
designing without a guard against it would be negligent: it keeps buying while
a real repricing runs, averaging into a move that is information rather than
liquidity demand. Every gate in this module exists to refuse that trade, and
each one is a *veto* -- it can only stop a trade the signal already wanted, and
never create one.

**The one assumption this system is entitled to make.** The mechanism claims a
liquidity premium, which is paid when inventory has to be rebalanced. In a
genuine crash there is no inventory being rebalanced; there is a new price and
everyone agreeing to it. So volatility far outside a symbol's own recent
distribution is the state where the premise is false, not merely the state
where it is risky. That is a prediction of the hypothesis, not a comfort
filter, which is why it is on by default while the trend gate below is not.

**The trend gate is off by default, on purpose.** This laboratory has measured
that buying weakness inside a daily BEAR regime is the worst cell in its own
tactic table, so a trend filter here would look obviously justified. It is not
obviously justified: that table was measured at a 20-*day* horizon, where the
question is whether there is an uptrend to recover into. This system's horizon
is four hours. Cycle-agnosticism is the claim under test, and switching on a
cycle filter by default would answer the question by assuming it. The gate
exists so the sweep can measure what it costs.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VolatilityWatch:
    """Each symbol's own recent volatility, so "violent" means violent FOR IT.

    A fixed NATR threshold would be a different rule on BTC than on XRP and a
    different rule in 2018 than in 2026 -- which is the same reason every other
    threshold in this system is a multiple of something rather than a constant.
    The comparison is to the symbol's own trailing distribution.

    Causal by construction: the window only ever contains bars at or before the
    one being judged, so the verdict for bar N cannot change when bar N+1
    arrives. That prefix-equality property is a rule of this repository and the
    test suite checks it rather than trusting this paragraph.
    """

    window: int = 480  # five days of 15-minute bars
    minimum_samples: int = 192  # two days: below this the distribution is noise
    history: dict[str, deque] = field(default_factory=dict)

    def observe(self, symbol: str, natr: float | None) -> None:
        if natr is None:
            return
        series = self.history.get(symbol)
        if series is None:
            series = self.history[symbol] = deque(maxlen=self.window)
        series.append(float(natr))

    def elevated(self, symbol: str, natr: float | None, quantile: float) -> bool:
        """Is this bar's volatility above the symbol's own `quantile`?

        Returns False while the sample is too small to have an opinion. That is
        a deliberate choice and it is the permissive one: a veto that cannot be
        evaluated must not silently become a veto that fires, or a run would
        take no trades for its first two days and the reason would appear
        nowhere. The cost is bounded and stated -- the first ~2 days of any
        window are unprotected by this gate.
        """
        if natr is None or quantile >= 1.0:
            return False
        series = self.history.get(symbol)
        if series is None or len(series) < self.minimum_samples:
            return False
        ordered = sorted(series)
        index = min(len(ordered) - 1, int(quantile * (len(ordered) - 1)))
        return float(natr) > ordered[index]

    def reset(self) -> None:
        self.history.clear()


def trend_allows(row: dict[str, Any], mode: str, close: float, key: str) -> bool:
    """The optional cycle gate. `none` is the default and means no opinion.

    - `none`: buy the dislocation wherever it happens. The claim under test.
    - `above_slow`: only when the close is above its own slow average -- the
      daily system's premise, imported and made measurable at this horizon.
    - `below_slow`: the deliberate opposite. It is here because "the filter
      helps" is only evidence if its inverse hurts; a gate that improves the
      result in both directions is measuring overfitting, not trend.
    """
    if mode == "none":
        return True
    slow = row.get(key)
    if slow is None:
        # The slow average has not warmed up. A gate that cannot be evaluated
        # refuses, here, because unlike the volatility veto this one is opt-in:
        # a caller who asked for a trend filter should not silently get bars
        # that were never filtered.
        return False
    return close > float(slow) if mode == "above_slow" else close < float(slow)


def hour_allows(timestamp: str, hours: tuple[int, ...] | None) -> bool:
    """Time-of-day gate, off by default.

    Crypto has a documented intraday seasonality and it is tempting to encode
    it. It is not encoded: an hour list chosen from the same history it is
    scored on is twenty-four free parameters, and this laboratory's central
    measured problem is that in-sample selection correlates +0.06 with forward
    rank. The gate exists so a *stated* hypothesis about hours can be tested,
    not so the sweep can discover one.
    """
    if not hours:
        return True
    try:
        return int(timestamp[11:13]) in hours
    except (TypeError, ValueError, IndexError):
        return True
