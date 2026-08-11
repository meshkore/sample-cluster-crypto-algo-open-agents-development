"""Market-wide regime detection: the first of the four pieces.

This module answers one question and nothing else: **what major trend is the
whole crypto market in right now?** It never looks at a tradable candidate, it
never emits a position, and it is deliberately kept out of the router so it can
be evaluated and published on its own -- a regime call is either right or wrong
regardless of what any strategy does with it.

**It reads the tape, not the disk.** The detector is fed one bar at a time from
the backtester's tick stream, exactly as the router sees it: closes for the
reference basket, and whether each reference asset is above its own long
average -- a column the backtester has already computed. It owns no files, no
`DataManager` and no lookahead, because it structurally cannot see a bar that
has not been served yet. The previous version built a whole timeline from a bar
archive and then policed itself with a `bisect` on timestamps; the pulled clock
makes that policing unnecessary and the class of bug it guarded against
unreachable.

Three design commitments, each of which exists because the obvious alternative
is wrong:

1. **The regime is a property of the market, not of an asset.** It is computed
   from an equal-weighted composite of a declared reference basket plus the
   breadth of that basket, never from the asset being traded. H-REGIME-001
   (QUANT12) put a 200-bar SMA regime filter on each asset's own bars and
   traded 8 assets out of 386, because a per-asset filter is a second trend
   rule wearing a regime's name.

2. **A label costs one bar of history and never more.** The tick the router is
   deciding on has closed; the fills it earns happen at the next bar's open. So
   labelling bar N from bar N's close is safe, and it is the *only* thing this
   class can do -- there is no later bar in scope to leak.

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
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Iterable


class MarketRegime(str, Enum):
    """`UNKNOWN` is a first-class state, not a missing value.

    The composite needs a long trailing window, so the market genuinely has no
    regime for the first ~220 bars the detector is shown. Emitting BULL or
    SIDEWAYS there would be an unearned claim; emitting UNKNOWN lets the router
    stand aside until the detector has the history it needs, which is the
    honest behaviour and what the operator asked for -- trading does not start
    on day one.
    """

    UNKNOWN = "UNKNOWN"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    BULL = "BULL"


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


@dataclass(frozen=True)
class RegimeParameters:
    """These defaults are MEASURED, and they replace conventional ones that were
    measured to be inverted.

    The previous defaults -- a 200-bar trend, its slope, breadth on `sma_200`,
    20-bar confirmation -- were chosen because they are the textbook settings,
    on the argument that the first measurement should be of the mechanism
    rather than of a fit. That argument was right and the measurement it asked
    for came back against them
    (`orchestrator-manager/scripts/detector_diagnosis.py`, H-L081D, on the
    reference basket 2017-08-17 to 2025-12-31):

      * The label ordered the future BACKWARDS. Forward 20-bar composite return
        was +1.27% under BEAR against +2.64% under BULL and +4.88% under
        SIDEWAYS, and BEAR beat BULL in every one of the four folds. A BEAR
        label that predicts a RISE is not a conservative detector, it is a
        wrong one.
      * On the three falls it named at all, BEAR arrived 56%, 77% and 104% of
        the way from peak to trough -- in 2025, three days after the bottom.
      * In the 2024-2026 fold, the one that falls, BEAR covered 1.4% of bars.
        The bear branch had almost no tape to be selected on.

    All three came from one term. Requiring the SLOPE of a 200-bar average to
    have turned cannot be satisfied inside a two-month crash, and by the time
    it is, the crash is over. So `require_slope` exists, and defaults to off.

    What the shootout measured over ten mechanisms
    (`orchestrator-manager/scripts/detector_shootout.py`):

        variant            BEAR fwd   ordered   median lag   BEAR in 24-26
        incumbent            +1.27%        no          77%            1.4%
        best reachable       +0.81%       YES          22%           21.8%
        + breadth on sma_50  +0.20%       YES          25%           24.7%
        THESE DEFAULTS       -0.31%       YES           8%           34.0%

    "best reachable" is the winner's shape built only from levers the search
    already had. It still cannot make BEAR negative, which is why this is a
    code change and not a wider range: the mandatory slope AND was a cage the
    search could not open from inside.

    `breadth_key` names the served column breadth is read from, so the breadth
    window is not a second thing to keep in sync with the backtester: asking
    for `sma_100` here asks for a 100-bar breadth and nothing else changes.

    Every one of these is a searchable dimension, so none of them is a claim
    that this is the optimum -- only that it is the first setting whose BEAR
    label points downhill.
    """

    trend_period: int = 100
    slope_period: int = 20
    bull_breadth: float = 0.50
    bear_breadth: float = 0.35
    confirmation_bars: int = 5
    breadth_key: str = "sma_50"
    # Off by default, and the single change that flips the separation negative.
    # Kept as a parameter rather than deleted because the slope test is the
    # right instinct on a slower instrument -- on weekly bars, or on a trend
    # window short enough for its own slope to turn inside a fall, it costs
    # nothing and rejects chop. The search decides, per deployment.
    require_slope: bool = False

    def __post_init__(self) -> None:
        if min(self.trend_period, self.slope_period) < 2:
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
        """Bars of tape before a label can be earned.

        Breadth contributes nothing here: it arrives already computed on the
        tick, so the only thing that has to accumulate is the composite and its
        own trailing average.

        The slope term is charged for only when it is required. Holding the
        router flat for an extra `slope_period` bars to warm a statistic no
        branch consults is dead time, not caution.
        """
        return self.trend_period + (self.slope_period if self.require_slope else 0)


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


class MarketDetector:
    """The major-trend detector, advanced one served bar at a time.

    The rule is symmetric by construction -- BULL and BEAR are the same three
    tests with the inequalities flipped -- because the first version was not:
    it defined BEAR as a drawdown from the running all-time high, which stays
    true through every recovery and duly labelled the 2020 and 2023 rebounds
    (+54% and +38% on the composite) as bear markets. Drawdown describes where
    the market has *been*; the trend of the composite, its slope and breadth
    describe where it is.

    Feed it with `observe()` once per tick and read `regime`, `depth` and
    `episode_age`. It keeps the composite series so a finished run can be
    scored with `separation()`, and nothing else.
    """

    def __init__(
        self,
        parameters: RegimeParameters | None = None,
        reference: Iterable[str] = REFERENCE_BASKET,
    ):
        self.parameters = parameters or RegimeParameters()
        self.reference = tuple(sorted(set(reference)))
        if not self.reference:
            raise ValueError("a regime detector needs at least one reference asset")
        self.reset()

    def reset(self) -> None:
        self.stamps: list[datetime] = []
        self.index: list[float] = []
        self.breadth: list[float] = []
        self.labels: list[MarketRegime] = []
        self.regime = MarketRegime.UNKNOWN
        self.depth = 0.0
        self.episode_age = 0
        self.seen_symbols: set[str] = set()
        self._level = 100.0
        self._high = 100.0
        self._previous_closes: dict[str, float] = {}
        self._trend_sum = 0.0
        self._trend_window: deque[float] = deque()
        self._averages: list[float | None] = []
        self._pending: MarketRegime | None = None
        self._streak = 0

    # -- the tape ------------------------------------------------------------ #

    def observe(
        self,
        timestamp: datetime,
        closes: dict[str, float],
        above_trend: dict[str, bool],
    ) -> MarketRegime:
        """Advance the detector by one bar of the reference basket.

        `closes` are this bar's reference closes and `above_trend` says, per
        reference asset, whether it closed above its own long average -- read
        straight off the backtester's `breadth_key` column. An asset missing
        from either map is absent from that side of the calculation rather than
        counted as a zero or a `False`: counting an unlisted or short-history
        asset as "not above its average" would manufacture a bearish breadth
        reading out of missing data, most severely in 2017-2018 where the
        basket is still filling in.
        """
        usable = {
            symbol: float(close)
            for symbol, close in closes.items()
            if symbol in self.reference and close and float(close) > 0
        }
        self.seen_symbols.update(usable)

        # Chaining the mean log return rather than averaging prices is what
        # makes the composite survive listings: an asset joins the average on
        # the first bar where it has both a close and a previous close, and its
        # absent history neither dilutes nor rebases the index. A price-average
        # index would jump the day a new reference asset appears -- a level
        # change with no market event behind it.
        #
        # Equal weight rather than turnover weight is a real choice: a turnover
        # weighting is BTC plus noise, and the alt breadth that distinguishes a
        # late bull from an early one would be invisible.
        returns = [
            math.log(close / previous)
            for symbol, close in usable.items()
            if (previous := self._previous_closes.get(symbol))
        ]
        if returns:
            self._level *= math.exp(sum(returns) / len(returns))
        self._previous_closes.update(usable)

        flags = [
            bool(above_trend[symbol])
            for symbol in usable
            if above_trend.get(symbol) is not None
        ]
        share = sum(1 for flag in flags if flag) / len(flags) if flags else 0.0

        self.stamps.append(timestamp)
        self.index.append(self._level)
        self.breadth.append(share)
        self._high = max(self._high, self._level)
        self.depth = max(0.0, 1 - self._level / self._high) if self._high else 0.0

        self._advance_average()
        raw = self._classify(share)
        self._apply_hysteresis(raw)
        self.labels.append(self.regime)
        self.episode_age = (
            self.episode_age + 1
            if len(self.labels) > 1 and self.labels[-2] is self.regime
            else 0
        )
        return self.regime

    def _advance_average(self) -> None:
        period = self.parameters.trend_period
        self._trend_window.append(self._level)
        self._trend_sum += self._level
        if len(self._trend_window) > period:
            self._trend_sum -= self._trend_window.popleft()
        self._averages.append(
            self._trend_sum / period if len(self._trend_window) == period else None
        )

    def _classify(self, share: float) -> MarketRegime:
        """Two tests, or three when `require_slope` is on.

        Price against its own long average is a FAST statistic: it crosses on
        the day the market crosses. The average's slope is that same statistic
        smoothed a second time, on top of a window already `trend_period` bars
        long, and it is where the months of lag measured in H-L081D came from.
        Breadth is never optional -- without it one deep reference asset could
        carry the label for the whole market.
        """
        average = self._averages[-1]
        if average is None:
            return MarketRegime.UNKNOWN

        rising = falling = True
        if self.parameters.require_slope:
            position = len(self._averages) - 1 - self.parameters.slope_period
            prior = self._averages[position] if position >= 0 else None
            if prior is None:
                return MarketRegime.UNKNOWN
            rising, falling = average > prior, average < prior

        if self._level > average and rising and share >= self.parameters.bull_breadth:
            return MarketRegime.BULL
        if self._level < average and falling and share <= self.parameters.bear_breadth:
            return MarketRegime.BEAR
        return MarketRegime.SIDEWAYS

    def _apply_hysteresis(self, raw: MarketRegime) -> None:
        """A raw reading has to hold for `confirmation_bars` before the state moves.

        A single threshold touch never flips the regime, so the router is not
        asked to rebuild the portfolio because breadth crossed 0.50 for one
        afternoon.

        UNKNOWN is exempt in one direction only: the first real reading is
        adopted immediately rather than after a confirmation streak, because
        waiting 20 bars to admit the warmup finished is not hysteresis, it is
        just a longer warmup applied twice.
        """
        if raw is MarketRegime.UNKNOWN:
            return
        if self.regime is MarketRegime.UNKNOWN:
            self.regime, self._pending, self._streak = raw, None, 0
            return
        if raw is self.regime:
            self._pending, self._streak = None, 0
        elif raw is self._pending:
            self._streak += 1
            if self._streak >= self.parameters.confirmation_bars:
                self.regime, self._pending, self._streak = raw, None, 0
        else:
            self._pending, self._streak = raw, 1

    # -- what the detector is worth ------------------------------------------ #

    def episodes(self) -> list[RegimeEpisode]:
        episodes: list[RegimeEpisode] = []
        start = 0
        for position, label in enumerate(self.labels):
            last = position == len(self.labels) - 1
            if not (last or self.labels[position + 1] is not label):
                continue
            episodes.append(
                RegimeEpisode(
                    regime=label,
                    start=self.stamps[start],
                    end=self.stamps[position],
                    bars=position - start + 1,
                    index_start=self.index[start],
                    index_end=self.index[position],
                )
            )
            start = position + 1
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

        It reads forward through the recorded composite, so it is a *post-run*
        measurement and never something the router can consult.
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
            "reference_symbols": list(self.reference),
            "observed_symbols": sorted(self.seen_symbols),
            "bars": len(self.labels),
            "first_bar": self.stamps[0].isoformat() if self.stamps else None,
            "last_bar": self.stamps[-1].isoformat() if self.stamps else None,
            "current_regime": self.regime.value,
            "composite_index": self.index[-1] if self.index else None,
            "composite_depth": self.depth,
            "episode_age": self.episode_age,
            "share_by_regime": {k: v / total for k, v in sorted(counts.items())},
            "episodes": len(episodes),
            "median_episode_bars": (
                sorted(e.bars for e in episodes)[len(episodes) // 2] if episodes else 0
            ),
            "parameters": {
                "trend_period": self.parameters.trend_period,
                "slope_period": self.parameters.slope_period,
                "bull_breadth": self.parameters.bull_breadth,
                "bear_breadth": self.parameters.bear_breadth,
                "confirmation_bars": self.parameters.confirmation_bars,
                "breadth_key": self.parameters.breadth_key,
                "require_slope": self.parameters.require_slope,
            },
        }


class AssetDetector:
    """The same major-trend test applied to one series, minus breadth.

    Used by the router's `regime_scope="asset"` mode (H-014). It runs the market
    detector's two remaining tests -- price against its own long average, and
    that average against where it was `slope_period` bars ago -- on the served
    `sma_200` column, so the two scopes are comparable rather than two
    differently-tuned systems.

    This is not H-003's cross-sectional relative strength, which ranked assets
    against each other inside a falling cross-section and found every decile
    negative. Nothing here is relative: an asset qualifies on its own absolute
    structure or not at all.
    """

    def __init__(
        self,
        trend_key: str = "sma_200",
        slope_period: int = 20,
        confirmation_bars: int = 20,
    ):
        if slope_period < 1:
            raise ValueError("slope_period must be at least one bar")
        if confirmation_bars < 1:
            raise ValueError("confirmation_bars must be at least one bar")
        self.trend_key = trend_key
        self.slope_period = slope_period
        self.confirmation_bars = confirmation_bars
        self.reset()

    def reset(self) -> None:
        self.regime = MarketRegime.UNKNOWN
        # `slope_period + 1` entries: the current average and the one from
        # `slope_period` bars ago, with nothing in between retained.
        self._averages: deque[float] = deque(maxlen=self.slope_period + 1)
        self._pending: MarketRegime | None = None
        self._streak = 0

    def observe(self, close: float, indicators: dict[str, Any]) -> MarketRegime:
        average = indicators.get(self.trend_key)
        if average is None:
            # The column has not filled yet. Holding the previous label would
            # route on a reading the asset has not earned.
            return self.regime
        self._averages.append(float(average))
        if len(self._averages) <= self.slope_period:
            return self.regime
        prior = self._averages[0]
        if close > average and average > prior:
            raw = MarketRegime.BULL
        elif close < average and average < prior:
            raw = MarketRegime.BEAR
        else:
            raw = MarketRegime.SIDEWAYS
        if self.regime is MarketRegime.UNKNOWN:
            self.regime, self._pending, self._streak = raw, None, 0
        elif raw is self.regime:
            self._pending, self._streak = None, 0
        elif raw is self._pending:
            self._streak += 1
            if self._streak >= self.confirmation_bars:
                self.regime, self._pending, self._streak = raw, None, 0
        else:
            self._pending, self._streak = raw, 1
        return self.regime


def regime_shares(labels: Iterable[MarketRegime]) -> dict[str, float]:
    counts = Counter(label.value for label in labels)
    total = sum(counts.values()) or 1
    return {label: count / total for label, count in sorted(counts.items())}
