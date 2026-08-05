"""The three regime-conditional branches and the router that composes them.

Pieces two, three and four of the four-piece system. `regime.py` answers *what
market are we in*; this module answers *what do we do about it*, and keeps the
two separable on purpose: the detector can be scored on its own labels, each
branch can be swept on its own parameters, and the router can be measured
against a single-rule strategy to show whether switching earned anything.

**What the branches contain, and why it is not what it looks like.**

The intuitive assignment is trend-following in a bull, range-trading sideways,
and bounce-hunting in a bear. The bounce-hunting half of that is contradicted
by this laboratory's own data. Pooled across the six reference assets over
2017-2025, mean forward return on days each tactic was long, bucketed by the
regime in force that day:

| tactic                | BEAR   | SIDEWAYS | BULL   |  (20-bar forward)
|-----------------------|--------|----------|--------|
| buy and hold          | +1.77% | +5.81%   | +3.76% |
| trend (20 over 50)    | +4.39% | +4.06%   | +5.93% |
| 20-bar breakout       | +3.97% | +10.94%  | +10.06%|
| RSI < 30 bounce       | -0.20% | +4.76%   | +2.26% |
| 5% single-bar drop    | -0.17% | +5.65%   | +4.80% |

Buying weakness is the **worst** thing to do in a bear regime and one of the
better things to do in a bull one -- the dip is worth buying only when there is
an uptrend to recover into. H-REGIME-001 (QUANT12) put an RSI-oversold bounce
in its bear branch and returned -8.46% with a 23.97% drawdown; this table is
why, and it is the reason the bear branch here buys strength cautiously instead
of buying weakness confidently.

The second reading of the same table is that regime does **not** select the
tactic among these rules: the 20-bar breakout is the strongest cell in both
SIDEWAYS and BULL. What regime separates here is *magnitude* -- every tactic
earns less in BEAR.

**The exception, and it is the one that pays: Kotegawa's deviation rate.**
Buying a 25-35% collapse below the 25-day average returns +10.13% over the next
120 hours in a bull regime, +5.21% in a sideways one, and **-1.57% in a bear
one** -- a twelve-point spread decided entirely by the regime label, on
thousands of observations. That is a rule the regime call genuinely selects
for, unlike everything above it, and it is why `_DeviationReversionBranch`
exists and why it is not in the bear branch.

Which rule occupies which regime is data, not doctrine: see `BRANCHES` for the
current assignment and `RULES` for the alternatives, each swappable per run so
the operator's four pieces stay independently tunable.
"""

from __future__ import annotations

from typing import Any

from .models import Bar
from .regime import MarketContext, MarketRegime
from .strategies import _rsi, _sma


class _BullTrendBranch:
    """Ride the confirmed trend, enter on strength that is not yet exhausted.

    This is the H-SMARSI-001 mechanism, deliberately unchanged: it is the only
    rule in this laboratory with a positive walk-forward record (9 of 12 folds,
    consistency 0.75) and reusing it verbatim means any difference this router
    produces is attributable to the *switching*, not to a new bull rule
    smuggled in alongside it.
    """

    def __init__(self, params: dict[str, Any], prefix: str = "bull_"):
        self.params, self.prefix = params, prefix
        self.reset()

    def _get(self, name: str, default: float) -> float:
        return float(self.params.get(f"{self.prefix}{name}", default))

    def reset(self) -> None:
        self.active = False

    def on_bar(self, bars: list[Bar]) -> float:
        fast_period = int(self._get("fast_period", 50))
        slow_period = int(self._get("slow_period", 200))
        rsi_period = int(self._get("rsi_period", 14))
        floor, ceiling = self._get("rsi_floor", 55.0), self._get("rsi_ceiling", 90.0)
        i = len(bars) - 1
        if i < max(fast_period, slow_period, rsi_period):
            return 0.0
        fast, slow = _sma(bars, i, fast_period), _sma(bars, i, slow_period)
        rsi, trend_up = _rsi(bars, i, rsi_period), None
        trend_up = fast > slow
        if self.active:
            if not trend_up or rsi > ceiling:
                self.active = False
        elif trend_up and floor < rsi <= ceiling and bars[i].close > fast:
            self.active = True
        return 1.0 if self.active else 0.0


class _SidewaysBreakoutBranch:
    """Wait for the range to break, then follow it.

    A sideways regime here is rarely a textbook flat channel -- it is mostly
    the unconfirmed ground between a bottom and a trend, which is exactly where
    the 20-bar breakout posts the strongest cell in the table above (+10.94%
    over 20 bars). Mean-reverting *inside* the range was the intuitive choice
    and the same table rates it lower (+4.76% for RSI-30, +3.78% for a
    below-band entry), so this branch trades the exit from the range rather
    than the interior of it.

    The exit is the channel midpoint rather than the opposing low: a full
    Donchian round trip gives back most of a range-sized move before it admits
    the breakout failed, and in a regime whose defining feature is that moves
    do not persist, that round trip is the whole move.
    """

    def __init__(self, params: dict[str, Any], prefix: str = "sideways_"):
        self.params, self.prefix = params, prefix
        self.reset()

    def _get(self, name: str, default: float) -> float:
        return float(self.params.get(f"{self.prefix}{name}", default))

    def reset(self) -> None:
        self.active = False

    def on_bar(self, bars: list[Bar]) -> float:
        entry_period = int(self._get("entry_period", 20))
        exit_period = int(self._get("exit_period", 20))
        i = len(bars) - 1
        if i < max(entry_period, exit_period):
            return 0.0
        # Both windows END at the previous bar, matching H-DONCH-001. Including
        # the current bar makes the entry unreachable rather than merely
        # stricter: this bar's own high is by definition at or above its own
        # close, so `close > max(high)` over a window containing it can only be
        # true on a doji. The first version of this branch did include it and
        # silently never traded.
        entry_window = bars[i - entry_period : i]
        exit_window = bars[i - exit_period : i]
        highest = max(bar.high for bar in entry_window)
        lowest = min(bar.low for bar in exit_window)
        midpoint = (highest + lowest) / 2
        if self.active:
            if bars[i].close < midpoint:
                self.active = False
        elif bars[i].close > highest:
            self.active = True
        return 1.0 if self.active else 0.0


class _BearParticipationBranch:
    """Participate only in a confirmed counter-trend advance. Never buy the dip.

    The plan this system came from called for "chasing the bounces" in a bear
    market. The measurement rejects it: RSI-30 bounces return -0.20% over the
    following 20 bars inside a bear regime, and a 5% single-bar drop -0.17%.
    Both are solidly positive in the other two regimes. A bear market is a
    sequence of failed bounces, and a rule that buys every one of them is
    buying the failure.

    So the bear branch is the same trend confirmation the other branches use,
    with a shorter memory (a bear rally is measured in weeks, not quarters) and
    a hard requirement that the advance is already underway. It exits the
    moment that stops being true rather than waiting for a target, because the
    base rate here is that the advance ends.
    """

    def __init__(self, params: dict[str, Any], prefix: str = "bear_"):
        self.params, self.prefix = params, prefix
        self.reset()

    def _get(self, name: str, default: float) -> float:
        return float(self.params.get(f"{self.prefix}{name}", default))

    def reset(self) -> None:
        self.active = False

    def on_bar(self, bars: list[Bar]) -> float:
        fast_period = int(self._get("fast_period", 20))
        slow_period = int(self._get("slow_period", 50))
        rsi_period = int(self._get("rsi_period", 14))
        rsi_floor = self._get("rsi_floor", 50.0)
        i = len(bars) - 1
        if i < max(fast_period, slow_period, rsi_period):
            return 0.0
        fast, slow = _sma(bars, i, fast_period), _sma(bars, i, slow_period)
        advancing = fast > slow and bars[i].close > fast
        if self.active:
            if not advancing:
                self.active = False
        elif advancing and _rsi(bars, i, rsi_period) > rsi_floor:
            self.active = True
        return 1.0 if self.active else 0.0


class _DeviationReversionBranch:
    """Kotegawa's deviation rate: buy capitulation, sell the reversion.

    Takashi Kotegawa (BNF) traded the 25-day moving-average deviation rate --
    buying liquid names 20-35% BELOW their 25-day average and exiting as price
    reverted toward it. That is not the RSI-30 dip this laboratory already
    rejected; it is one to two orders of magnitude more extreme, a capitulation
    filter rather than a pullback filter, and it had never been measured here.

    Measured now, pooled across the basket 2017-2025, forward return from the
    -35%..-25% band by the regime in force:

    |                  | BEAR   | SIDEWAYS | BULL    |
    |------------------|--------|----------|---------|
    | hourly, +120 bars| -1.57% | +5.21%   | +10.13% |
    | hourly, +480 bars| -0.60% | +18.44%  | +13.86% |
    | daily,  +20 bars | +2.16% | +14.04%  | -1.99%  |

    The edge is real and it is large -- and it is absent in a bear market, at
    every horizon, on 2,463 hourly observations. So this rule is exactly what
    the operator asked for and exactly not where they asked to put it: the
    deviation trade belongs in the regimes where there is something to revert
    to. A 30% drop in a bull market is a dislocation; the same 30% drop in a
    bear market is the trend.

    The period defaults to 600 bars because this family trades hourly and 600
    hours is 25 days -- the deviation then means what it meant on his charts.
    Running it on a 25-BAR hourly average would be a one-day mean reversion
    wearing his name.
    """

    def __init__(self, params: dict[str, Any], prefix: str = "sideways_"):
        self.params, self.prefix = params, prefix
        self.reset()

    def _get(self, name: str, default: float) -> float:
        return float(self.params.get(f"{self.prefix}{name}", default))

    def reset(self) -> None:
        self.active = False

    def on_bar(self, bars: list[Bar]) -> float:
        period = int(self._get("deviation_period", 600))
        entry = self._get("entry_deviation", -0.25)
        exit_level = self._get("exit_deviation", -0.05)
        i = len(bars) - 1
        if i + 1 < period:
            return 0.0
        average = _sma(bars, i, period)
        if not average:
            return 0.0
        deviation = bars[i].close / average - 1
        if self.active:
            # Exit on reversion toward the average, not at a fixed profit
            # target: the trade's thesis is the gap closing, so the gap closing
            # IS the exit. A target unrelated to the signal would leave the
            # position open after its reason had expired.
            if deviation >= exit_level:
                self.active = False
        elif deviation <= entry:
            self.active = True
        return 1.0 if self.active else 0.0


# Which rule runs in which regime. Every entry is a measurement, not a
# preference, and the mapping is overridable per run (`bull_rule`,
# `sideways_rule`, `bear_rule`) so each of the operator's four pieces can be
# swapped and scored on its own without touching the other three.
RULES: dict[str, type] = {
    "trend": _BullTrendBranch,
    "breakout": _SidewaysBreakoutBranch,
    "participation": _BearParticipationBranch,
    "deviation": _DeviationReversionBranch,
}

BRANCHES: dict[MarketRegime, str] = {
    MarketRegime.BULL: "trend",
    MarketRegime.SIDEWAYS: "deviation",
    MarketRegime.BEAR: "participation",
}

# Regime exposure, expressed as signal confidence because that is the dial the
# existing money-management layer already scales position size by. Read the
# warning in `_RegimeRouter.on_bar` before changing these: a weight below the
# policy's `minimum_confidence` does not reduce the branch's exposure, it
# deletes the branch.
DEFAULT_WEIGHTS: dict[MarketRegime, float] = {
    MarketRegime.BULL: 1.0,
    MarketRegime.SIDEWAYS: 0.6,
    MarketRegime.BEAR: 0.3,
}


class _RegimeRouter:
    """H-ROUTER-001: one detector, three branches, one live at a time.

    Two behaviours here are not obvious and both are load-bearing.

    **Only the live branch is evaluated, and that is safe because the warmup
    lives in the bars, not in the branch.** Each branch recomputes its
    indicators from the full observed history on every call and carries no
    state beyond an `active` flag, so a branch that has been dormant for two
    years is not cold when it takes over -- its first call already sees 200
    bars of history. Feeding all three every bar would triple the indicator
    cost to change nothing, since the dormant branches' `active` flags are
    cleared at the switch anyway.

    **A regime change forces flat for one bar.** When the label moves, the
    router emits 0.0 regardless of what the incoming branch wants, which the
    portfolio reads as a signal exit. A bull trend position does not ride into
    a confirmed bear on the incoming branch's say-so, and the handover is
    visible in the trade ledger as its own closed trade rather than being
    silently inherited.
    """

    requires_market_context = True

    def __init__(self, params: dict[str, Any], context: MarketContext | None = None):
        if context is None:
            # Refusing is the point. A router that quietly fell back to a
            # single rule would report a regime-switching result produced
            # without a regime, which is the kind of number this laboratory
            # spent eight months unable to interpret.
            raise ValueError(
                "regime_router requires a MarketContext; build it with "
                "regime.build_market_timeline() over the reference basket"
            )
        self.params, self.context = params, context
        self.weights = {
            regime: float(params.get(f"{regime.value.lower()}_weight", default))
            for regime, default in DEFAULT_WEIGHTS.items()
        }
        self.rule_names = {
            regime: str(params.get(f"{regime.value.lower()}_rule", default))
            for regime, default in BRANCHES.items()
        }
        unknown = {n for n in self.rule_names.values() if n not in RULES}
        if unknown:
            raise ValueError(
                f"unknown branch rule(s) {sorted(unknown)}; available: {sorted(RULES)}"
            )
        self.branches = {
            # Each branch reads its own `<regime>_` parameter prefix, so the
            # same rule placed in two regimes is still two independently
            # tunable pieces rather than one shared configuration.
            regime: RULES[name](params, f"{regime.value.lower()}_")
            for regime, name in self.rule_names.items()
        }
        self.reset()

    def reset(self) -> None:
        self.last_regime: MarketRegime | None = None
        for branch in self.branches.values():
            branch.reset()

    def on_bar(self, bars: list[Bar]) -> float:
        regime = self.context.regimes.at(bars[-1].timestamp)
        changed = self.last_regime is not None and regime is not self.last_regime
        self.last_regime = regime
        if changed:
            # Flat through the handover, and every branch's state is cleared so
            # none of them resumes mid-position if its regime returns later.
            for branch in self.branches.values():
                branch.reset()
            return 0.0
        if regime is MarketRegime.UNKNOWN:
            return 0.0
        signal = self.branches[regime].on_bar(bars)
        # The weight multiplies the branch's confidence, and the portfolio
        # vetoes any signal below `minimum_confidence` (0.25 by default) before
        # sizing it. A bear weight of 0.3 therefore sizes at 30%; a bear weight
        # of 0.2 does not size at 20%, it never trades at all. The failure is
        # silent -- the branch simply shows no trades -- so weights are checked
        # against the policy floor in the family's tests rather than trusted.
        return signal * self.weights[regime]

    def diagnostics(self) -> dict[str, Any]:
        return {
            "rules": {r.value: name for r, name in self.rule_names.items()},
            "weights": {r.value: w for r, w in self.weights.items()},
            "regime_summary": self.context.regimes.summary(),
        }
