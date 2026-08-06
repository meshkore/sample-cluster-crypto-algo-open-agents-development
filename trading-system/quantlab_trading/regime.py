"""Market-wide regime detection: the first of the four pieces.

This module answers one question and nothing else: **what major trend is the
whole crypto market in right now?** It never looks at a tradable candidate, it
never emits a position, and it is deliberately kept out of `strategies.py` so
it can be evaluated, tuned and published on its own -- a regime call is either
right or wrong regardless of what any strategy does with it.

Three design commitments, each of which exists because the obvious alternative
is wrong:

1. **The regime is a property of the market, not of an asset.** It is computed
   from an equal-weighted composite of a declared reference basket plus the
   breadth of that basket, never from the asset being traded. H-REGIME-001
   (QUANT12) put a 200-bar SMA regime filter on each asset's own bars and
   traded 8 assets out of 386, because a per-asset filter is a second trend
   rule wearing a regime's name.

2. **Causality is structural, not a convention.** A label for day D is derived
   only from bars that closed on or before D, and `RegimeTimeline.at()` will
   only hand out a label whose source bar had *fully closed* before the
   timestamp asking for it. Cycle regimes are the single easiest place in this
   laboratory to leak the future: a top is obvious in hindsight and invisible
   in real time, and any rule written while looking at a chart of the whole
   history has already seen the answer.

3. **Hysteresis over responsiveness.** A raw reading must persist for
   `confirmation_bars` before the state changes. Without it the label
   oscillates around every threshold crossing and the downstream router churns
   positions on noise -- paying costs for a regime call that reverses next bar.

What the labels are worth is measured, not asserted: `separation()` reports the
forward return of the composite conditional on each label, which is the
instrument that showed the first version of this rule was labelling every
post-top recovery as BEAR.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Iterable

from quantlab_backtester.models import Bar


class MarketRegime(str, Enum):
    """`UNKNOWN` is a first-class state, not a missing value.

    Every rule here needs a long trailing window, so the market genuinely has
    no regime for the first ~220 bars of any history. Emitting BULL or
    SIDEWAYS there would be an unearned claim; emitting UNKNOWN lets the router
    stand aside until the detector has the history it needs, which is the
    honest behaviour and what the operator asked for -- trading does not start
    on day one.
    """

    UNKNOWN = "UNKNOWN"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    BULL = "BULL"


@dataclass(frozen=True)
class RegimeParameters:
    """Defaults are deliberately conventional, not tuned.

    200 periods is the most standard long-term trend window in technical
    analysis and 0.50/0.35 breadth are the natural majority/minority splits.
    They are defaults so that the first measurement of this detector is a
    measurement of the *mechanism*; the select-at-deployment-scope decision
    (2026-08-04) governs any subsequent search over them, and that search runs
    on the basket the system will actually deploy on.
    """

    trend_period: int = 200
    slope_period: int = 20
    breadth_period: int = 200
    bull_breadth: float = 0.50
    bear_breadth: float = 0.35
    confirmation_bars: int = 20

    def __post_init__(self) -> None:
        if min(self.trend_period, self.slope_period, self.breadth_period) < 2:
            raise ValueError("regime windows must span at least two bars")
        if self.confirmation_bars < 1:
            raise ValueError("confirmation_bars must be at least one bar")
        if not 0.0 <= self.bear_breadth <= self.bull_breadth <= 1.0:
            # An inverted pair would make both branches reachable at once and
            # the classification order -- not the rule -- would decide the
            # label. Fail at construction rather than produce a silent artifact.
            raise ValueError("bear_breadth must not exceed bull_breadth")

    @property
    def warmup_bars(self) -> int:
        return max(self.trend_period + self.slope_period, self.breadth_period)


@dataclass(frozen=True)
class RegimeEpisode:
    regime: MarketRegime
    start: datetime
    end: datetime
    bars: int
    index_start: float
    index_end: float

    @property
    def index_return(self) -> float:
        return self.index_end / self.index_start - 1 if self.index_start else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "bars": self.bars,
            "index_return": self.index_return,
        }


@dataclass(frozen=True)
class RegimeTimeline:
    """A causal, queryable regime history.

    `labels` is aligned with `stamps`, one entry per reference bar. `at()` is
    the only supported lookup and it enforces the closing rule below, so a
    consumer cannot accidentally read a label from a bar that had not finished
    forming when it asked.
    """

    stamps: list[datetime]
    labels: list[MarketRegime]
    index: list[float]
    breadth: list[float]
    bar_seconds: float
    parameters: RegimeParameters
    reference_symbols: tuple[str, ...] = ()

    def at(self, moment: datetime) -> MarketRegime:
        """The regime usable by a strategy acting at `moment`.

        A daily bar stamped D covers [D, D+1) and is only complete at D+1, so a
        strategy trading at any point inside that day cannot know D's label.
        This returns the latest bar whose whole span ended at or before
        `moment`, which is what makes the detector safe to consume from a
        faster timeframe: an hourly strategy reads yesterday's daily regime all
        day, and gets today's only once today has closed.
        """
        if moment.tzinfo is None:
            raise ValueError("regime lookups require timezone-aware timestamps")
        cutoff = moment - timedelta(seconds=self.bar_seconds)
        position = bisect_right(self.stamps, cutoff) - 1
        if position < 0:
            return MarketRegime.UNKNOWN
        return self.labels[position]

    def _position_for(self, moment: datetime) -> int:
        if moment.tzinfo is None:
            raise ValueError("regime lookups require timezone-aware timestamps")
        cutoff = moment - timedelta(seconds=self.bar_seconds)
        return bisect_right(self.stamps, cutoff) - 1

    def depth_at(self, moment: datetime) -> float:
        """How far the composite sits below its own running high, at `moment`.

        A bear market is not one environment. Pre-2026, inside BEAR regimes,
        mean forward 30-day return of liquid assets by composite depth:

        | composite below its high | forward 30d | n      | hit |
        |--------------------------|-------------|--------|-----|
        | 30-50%                   | **-32.30%** | 3,336  |  9% |
        | 50-70%                   | -11.78%     | 6,572  | 26% |
        | 70-100%                  | **+6.86%**  | 10,728 | 52% |

        The shallow part of a bear is the most destructive place this
        laboratory has measured anywhere -- a 9% hit rate over 30 days. The deep
        part is positive. Same regime label, opposite expectation, which is why
        the label alone was never enough.

        Causal like everything else here: the running high uses only bars that
        closed at or before the same cutoff `at()` enforces.
        """
        position = self._position_for(moment)
        if position < 0:
            return 0.0
        peak = max(self.index[: position + 1])
        return max(0.0, 1 - self.index[position] / peak) if peak else 0.0

    def episode_age_at(self, moment: datetime) -> int:
        """Bars elapsed inside the current regime episode, at `moment`.

        The same story as `depth_at` on a different axis: 0-60 bars into a bear
        returns -12.71% over the next 30, while 240+ bars in returns +8.20%.
        Known in real time -- it counts backwards from now, not forwards to a
        bottom nobody can see yet.
        """
        position = self._position_for(moment)
        if position < 0:
            return 0
        label, age = self.labels[position], 0
        while position - age - 1 >= 0 and self.labels[position - age - 1] is label:
            age += 1
        return age

    def episodes(self) -> list[RegimeEpisode]:
        episodes: list[RegimeEpisode] = []
        start_position = 0
        for position, label in enumerate(self.labels):
            is_last = position == len(self.labels) - 1
            changes = not is_last and self.labels[position + 1] is not label
            if not (changes or is_last):
                continue
            episodes.append(
                RegimeEpisode(
                    regime=label,
                    start=self.stamps[start_position],
                    end=self.stamps[position],
                    bars=position - start_position + 1,
                    index_start=self.index[start_position],
                    index_end=self.index[position],
                )
            )
            start_position = position + 1
        return episodes

    def separation(self, horizon: int = 20) -> dict[str, dict[str, float]]:
        """Does the label order the future? The detector's own scorecard.

        For every bar, the forward return of the composite over `horizon` bars
        is bucketed by the label known at that bar. A useful detector produces
        BULL > SIDEWAYS > BEAR; a detector that produces anything else is
        lagging, mislabelling, or both, and no amount of downstream strategy
        work repairs that. This is reported next to every regime result rather
        than kept as a private diagnostic, because "the regime call was right"
        is precisely the claim that needs evidence.
        """
        if horizon < 1:
            raise ValueError("horizon must be at least one bar")
        buckets: dict[str, list[float]] = {}
        for position, label in enumerate(self.labels):
            target = position + horizon
            if target >= len(self.index) or not self.index[position]:
                continue
            buckets.setdefault(label.value, []).append(
                self.index[target] / self.index[position] - 1
            )
        return {
            label: {
                "bars": float(len(values)),
                "mean_forward_return": sum(values) / len(values),
                "positive_share": sum(1 for v in values if v > 0) / len(values),
            }
            for label, values in sorted(buckets.items())
            if values
        }

    def summary(self) -> dict[str, Any]:
        counts = Counter(label.value for label in self.labels)
        total = len(self.labels) or 1
        episodes = [e for e in self.episodes() if e.regime is not MarketRegime.UNKNOWN]
        return {
            "reference_symbols": list(self.reference_symbols),
            "bars": len(self.labels),
            "first_bar": self.stamps[0].isoformat() if self.stamps else None,
            "last_bar": self.stamps[-1].isoformat() if self.stamps else None,
            "current_regime": self.labels[-1].value if self.labels else None,
            "share_by_regime": {k: v / total for k, v in sorted(counts.items())},
            "episodes": len(episodes),
            "median_episode_bars": (
                sorted(e.bars for e in episodes)[len(episodes) // 2] if episodes else 0
            ),
            "parameters": {
                "trend_period": self.parameters.trend_period,
                "slope_period": self.parameters.slope_period,
                "breadth_period": self.parameters.breadth_period,
                "bull_breadth": self.parameters.bull_breadth,
                "bear_breadth": self.parameters.bear_breadth,
                "confirmation_bars": self.parameters.confirmation_bars,
            },
        }


@dataclass
class MarketContext:
    """What a regime-aware strategy is allowed to know about the wider market.

    Deliberately one field. A strategy given a whole `DataManager` would be
    free to read any asset's future; a strategy given a `RegimeTimeline` can
    only ask "what regime was in force when this bar opened", and the timeline
    itself enforces the answer's causality.
    """

    regimes: RegimeTimeline
    notes: dict[str, Any] = field(default_factory=dict)


def _composite_index(
    bars_by_symbol: dict[str, list[Bar]], stamps: list[datetime]
) -> list[float]:
    """Equal-weighted chained composite of the reference basket's log returns.

    Chaining returns rather than averaging prices is what makes the index
    survive listings: an asset joins the average on the first bar where it has
    both a close and a previous close, and its absent history neither dilutes
    nor rebases the index. A price-average index would jump the day a new
    reference asset appears -- a level change with no market event behind it.

    Equal weight rather than turnover weight is a real choice: a turnover
    weighting is BTC plus noise, and the alt breadth that distinguishes a late
    bull from an early one would be invisible.
    """
    closes = {
        symbol: {bar.timestamp: bar.close for bar in bars}
        for symbol, bars in bars_by_symbol.items()
    }
    level, index = 100.0, []
    for position, stamp in enumerate(stamps):
        if position:
            previous = stamps[position - 1]
            returns = [
                math.log(series[stamp] / series[previous])
                for series in closes.values()
                if stamp in series
                and previous in series
                and series[previous] > 0
                and series[stamp] > 0
            ]
            if returns:
                level *= math.exp(sum(returns) / len(returns))
        index.append(level)
    return index


def _breadth(
    bars_by_symbol: dict[str, list[Bar]], stamps: list[datetime], period: int
) -> list[float]:
    """Share of reference assets trading above their own trailing average.

    Each asset is measured on its own bars, so an asset that has not yet
    accumulated `period` observations is absent from both numerator and
    denominator rather than counted as a negative. Counting an unlisted or
    short-history asset as "not above its average" would manufacture a bearish
    breadth reading out of missing data, most severely in 2017-2018 where the
    reference basket is still filling in.
    """
    per_symbol_flags: dict[str, dict[datetime, bool]] = {}
    for symbol, bars in bars_by_symbol.items():
        flags: dict[datetime, bool] = {}
        running = 0.0
        closes = [bar.close for bar in bars]
        for position, bar in enumerate(bars):
            running += bar.close
            if position >= period:
                running -= closes[position - period]
            if position + 1 >= period:
                flags[bar.timestamp] = bar.close > running / period
        per_symbol_flags[symbol] = flags

    breadth: list[float] = []
    for stamp in stamps:
        live = [flags[stamp] for flags in per_symbol_flags.values() if stamp in flags]
        breadth.append(sum(1 for flag in live if flag) / len(live) if live else 0.0)
    return breadth


def _modal_step_seconds(stamps: list[datetime]) -> float:
    """The reference timeframe, inferred rather than declared.

    `at()` needs to know when a bar finished to refuse labels that had not
    formed yet, and taking the modal gap makes that robust to the occasional
    missing bar an exchange feed contains. A mean would be dragged by any gap
    and would quietly shrink the safety margin.
    """
    if len(stamps) < 2:
        return 86_400.0
    gaps = Counter(
        (stamps[i] - stamps[i - 1]).total_seconds() for i in range(1, len(stamps))
    )
    return max(gaps.items(), key=lambda item: (item[1], -item[0]))[0]


def build_market_timeline(
    bars_by_symbol: dict[str, list[Bar]],
    parameters: RegimeParameters | None = None,
) -> RegimeTimeline:
    """Classify every bar of the reference basket into a major-trend regime.

    The rule is symmetric by construction -- BULL and BEAR are the same three
    tests with the inequalities flipped -- because the first version was not:
    it defined BEAR as a drawdown from the running all-time high, which stays
    true through every recovery and duly labelled the 2020 and 2023 rebounds
    (+54% and +38% on the composite) as bear markets. Drawdown describes where
    the market has *been*; the trend of the composite, its slope and breadth
    describe where it is.
    """
    parameters = parameters or RegimeParameters()
    usable = {
        symbol: sorted(bars, key=lambda bar: bar.timestamp)
        for symbol, bars in bars_by_symbol.items()
        if bars
    }
    if not usable:
        raise ValueError("a regime timeline needs at least one reference asset")
    stamps = sorted({bar.timestamp for bars in usable.values() for bar in bars})
    index = _composite_index(usable, stamps)
    breadth = _breadth(usable, stamps, parameters.breadth_period)

    labels: list[MarketRegime] = []
    current, pending, streak = MarketRegime.UNKNOWN, None, 0
    trend, slope = parameters.trend_period, parameters.slope_period
    running = 0.0
    for position, _ in enumerate(stamps):
        running += index[position]
        if position >= trend:
            running -= index[position - trend]
        if position + 1 < parameters.warmup_bars:
            labels.append(MarketRegime.UNKNOWN)
            continue
        average = running / trend
        prior_window = index[position - trend - slope + 1 : position - slope + 1]
        prior_average = sum(prior_window) / len(prior_window)
        share = breadth[position]
        if (
            index[position] > average
            and average > prior_average
            and share >= parameters.bull_breadth
        ):
            raw = MarketRegime.BULL
        elif (
            index[position] < average
            and average < prior_average
            and share <= parameters.bear_breadth
        ):
            raw = MarketRegime.BEAR
        else:
            raw = MarketRegime.SIDEWAYS

        # Hysteresis: the raw reading has to hold for `confirmation_bars`
        # consecutive bars before the state moves. A single threshold touch
        # never flips the regime, so the router is not asked to rebuild the
        # portfolio because breadth crossed 0.50 for one afternoon.
        if raw is current:
            pending, streak = None, 0
        elif raw is pending:
            streak += 1
            if streak >= parameters.confirmation_bars:
                current, pending, streak = raw, None, 0
        else:
            pending, streak = raw, 1
        labels.append(current)

    return RegimeTimeline(
        stamps=stamps,
        labels=labels,
        index=index,
        breadth=breadth,
        bar_seconds=_modal_step_seconds(stamps),
        parameters=parameters,
        reference_symbols=tuple(sorted(usable)),
    )


# The reference basket. Six assets with the longest continuous Binance spot
# history available, which is what lets the composite reach back to 2017 and
# cover more than one full cycle. It is intentionally NOT the tradable universe:
# the regime must not change because a new asset was listed or a delisted one
# dropped out, and a fixed basket is the cheapest way to guarantee that.
#
# The survivorship caveat is real and is stated rather than hidden: these six
# are all still listed today, so the basket is a picture of the market's
# survivors, not of the market. It biases the composite upward, which makes
# BULL slightly easier to reach than the honest market would justify.
REFERENCE_BASKET: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "LTCUSDT",
    "ADAUSDT",
)
REFERENCE_INTERVAL = "1d"


def market_context_from(
    loader: Callable[[list[str], str], dict[str, list[Bar]]],
    parameters: RegimeParameters | None = None,
    symbols: tuple[str, ...] = REFERENCE_BASKET,
    interval: str = REFERENCE_INTERVAL,
) -> MarketContext:
    """Build the context from whatever loader the calling phase already owns.

    Taking a loader instead of a `DataManager` keeps this module free of I/O
    and, more usefully, keeps the phase split where it belongs: the historical
    evaluator passes a loader that physically cannot return 2026 bars, and the
    forward evaluator passes one that splices them on. Neither can leak into
    the other by accident here, because this function never chooses.

    A forward context is built over history *plus* the forward window on
    purpose. The detector needs its 220-bar warmup before it can label
    2026-01-01 at all, and including later bars in the array is safe by
    construction: a label at time T is computed from bars up to T and `at()`
    refuses any bar that had not closed. The prefix-equality test pins that.
    """
    bars = loader(list(symbols), interval)
    if not bars:
        raise ValueError(
            f"no reference data for the regime basket {list(symbols)} at {interval}"
        )
    return MarketContext(
        regimes=build_market_timeline(bars, parameters),
        notes={
            "requested_symbols": list(symbols),
            "loaded_symbols": sorted(bars),
            "interval": interval,
        },
    )


def regime_shares(labels: Iterable[MarketRegime]) -> dict[str, float]:
    counts = Counter(label.value for label in labels)
    total = sum(counts.values()) or 1
    return {label: count / total for label, count in sorted(counts.items())}
