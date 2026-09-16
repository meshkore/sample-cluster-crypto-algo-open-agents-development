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
    # WHAT "THE MARKET" IS. `universe` means every asset the tape served on the
    # bar; `basket` means the six-name reference list.
    #
    # The operator's argument is that the trend being named is a property of the
    # whole market -- a bull run ends at peak total capitalisation, a bear at the
    # trough -- and six survivors are not that. Measured
    # (`orchestrator-manager/scripts/market_shootout.py`, H-L086M, 385 assets,
    # 3059 bars, every variant scored against the SAME broad benchmark so none
    # could win by being easy to predict):
    #
    #     market            BEAR   SIDEWAYS    BULL  ordered   BEAR in 24-26
    #     basket-6-equal   -2.15%    -4.16%  +3.70%       no           34.0%
    #     universe-equal   -2.43%    +1.01%  +4.01%      YES           57.1%
    #     universe-sqrt    -2.38%    -0.45%  +4.57%      YES           57.0%
    #     universe-turnover -1.34%   -5.33%  +5.60%       no           48.1%
    #
    # The six-name basket is NOT correctly ordered against the market it claims
    # to describe: its SIDEWAYS bucket falls harder than its BEAR bucket. The
    # broad equal-weighted universe is, and it nearly doubles the bear branch's
    # training signal in the fold that falls.
    #
    # Breadth is the sharper reason. On six names breadth can only report 0,
    # 1/6, 2/6 ... and the thresholds sit at 0.35 and 0.50 -- so the difference
    # between a bull market and a bear one was one asset changing its mind.
    market_scope: str = "universe"
    # How assets are weighted into the composite. Equal weight is a statement
    # about the median coin; turnover weight is a statement about where the
    # money is and is the closest PROXY for capitalisation this laboratory can
    # build, since it holds no circulating-supply data at all. `sqrt` is the
    # standard damping between them.
    #
    # Equal is the default because it is the only variant that came out
    # correctly ordered with a positive SIDEWAYS bucket. Turnover is kept and
    # searchable because it was the only variant right in ALL FOUR folds
    # (-1.20%, -2.35%, -0.78%, -4.46% BEAR-minus-BULL) -- a real disagreement
    # with the pooled test that the full objective, not this scorecard, should
    # settle.
    weighting: str = "equal"
    # THE MIDDLE LEVEL'S FLOOR: bars a label must survive before another may
    # replace it. `confirmation_bars` asks a NEW reading to persist; this asks
    # the CURRENT one to have lasted. They are different questions and only the
    # second one bounds how short a phase can be.
    #
    # Without it the mechanism produced 74 phases in 8.4 years, median 28 days,
    # 89% under three months -- so the trading module could be switched six
    # times in a quarter by moves nobody would call a change of trend. At 60 it
    # produces 39 phases with a median of 60 days and the label still orders the
    # next twenty bars (BEAR -1.05% against BULL +6.36%). At 90 the phase count
    # falls further but BEAR turns positive, so the floor is not free: past a
    # point it stops removing noise and starts removing the signal.
    minimum_phase: int = 60
    # THE GLOBAL LEVEL. Measured in H-L087C; see `CycleDetector` for the grid
    # and for why everything smoothed at 30 bars came out inverted.
    cycle_smoothing: int = 90
    cycle_bear_swing: float = 0.35
    cycle_bull_swing: float = 0.50
    cycle_minimum_phase: int = 150
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
        if self.market_scope not in ("universe", "basket"):
            raise ValueError("market_scope must be 'universe' or 'basket'")
        if self.weighting not in ("equal", "turnover", "sqrt"):
            raise ValueError("weighting must be 'equal', 'turnover' or 'sqrt'")
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


class CycleDetector:
    """The GLOBAL trend: the multi-year cycle, dated causally.

    This is the coarsest of the three levels and the one the operator means by
    "la tendencia global". It exists because the regime detector, which reads
    price against a trailing average, produced 74 phases in 8.4 years -- a
    median of 28 days, 89% of them under three months. A twenty-day bounce
    inside a fall is not a bull market, and every published dating of the same
    period finds six to ten phases, not seventy-four.

    THE MECHANISM is a turning-point dating rule, which is what the literature
    uses for this (Bry-Boschan 1971; Pagan & Sossounov 2003) and what every
    consensus chart is drawn with. Two terms, and the regime detector has
    neither:

      * A SWING THRESHOLD. A bear is a fall of `bear_swing` from the running
        peak; a bull is a rise of `bull_swing` from the running trough. Not a
        close below an average.
      * A MINIMUM PHASE. A state may not be left before `minimum_phase` bars.
        This is the censoring rule and it is what kills the churn.

    CAUSAL, and that is the whole difficulty. The textbook algorithm is
    RETROSPECTIVE: it finds a peak by looking at the bars after it, which is
    precisely the lookahead this laboratory refuses, and it is how every chart
    in the literature is drawn. This version reads only closed bars -- a running
    peak, a running trough, and a smoothed level -- so it is always LATER than
    the retrospective dating. That lateness is the honest price of not
    cheating, and it is why the thresholds are large: they have to survive being
    measured from a high that is still moving.

    Measured over 385 assets and 3,059 bars
    (`orchestrator-manager/scripts/cycle_shootout.py`, H-L087C):

        smoothing  swing    floor  phases  median   120-day forward
        30 bars    20/20     120      18    120d   BEAR +14.6% INVERTED
        60 bars    35/50     150      10    224d   BEAR  -1.8% vs +12.9%
        90 bars    35/50     150       6    429d   BEAR  -9.0% vs +31.3%

    Everything smoothed at 30 bars comes out INVERTED, whatever the threshold,
    because a 20-30% bounce off the low of a crypto bear happens inside every
    one of them and the rise-from-trough test fires on it. That is the finding
    that set the defaults: this market's cycle needs a long filter and a wide
    band, and anything less dates the noise.

    What it dated at those defaults, against the operator's reference charts:

        BEAR  2018-07-27 -> 2020-08-15   24.7 months
        BULL  2020-08-16 -> 2022-03-03   18.6 months
        BEAR  2022-03-04 -> 2024-02-16   23.5 months

    Which is the shape the halving-cycle and COIN50 datings show.
    """

    def __init__(
        self,
        smoothing: int = 90,
        bear_swing: float = 0.35,
        bull_swing: float = 0.50,
        minimum_phase: int = 150,
    ):
        if smoothing < 1:
            raise ValueError("smoothing must span at least one bar")
        if minimum_phase < 1:
            raise ValueError("minimum_phase must be at least one bar")
        if not (0.0 < bear_swing < 1.0) or bull_swing <= 0.0:
            raise ValueError("swings must be positive fractions")
        self.smoothing = smoothing
        self.bear_swing = bear_swing
        self.bull_swing = bull_swing
        self.minimum_phase = minimum_phase
        self.reset()

    def reset(self) -> None:
        self.regime = MarketRegime.UNKNOWN
        self.phase_age = 0
        self.level: float | None = None
        self._window: deque[float] = deque(maxlen=self.smoothing)
        self._peak: float | None = None
        self._trough: float | None = None
        self._held = 0

    def observe(self, level: float) -> MarketRegime:
        """Advance the cycle by one bar of the composite.

        The smoothing is a trailing mean, so it is available from the first bar
        rather than after `smoothing` of them -- a cycle detector that says
        UNKNOWN for the first quarter of the sample would be useless on any
        window shorter than a cycle, and the mean of what has been seen is an
        honest estimate of the level even when it is short.
        """
        self._window.append(float(level))
        value = sum(self._window) / len(self._window)
        self.level = value
        self._peak = value if self._peak is None else max(self._peak, value)
        self._trough = value if self._trough is None else min(self._trough, value)
        self._held += 1

        fell = 1 - value / self._peak if self._peak else 0.0
        rose = value / self._trough - 1 if self._trough else 0.0
        wanted = self.regime
        if self.regime is not MarketRegime.BEAR and fell >= self.bear_swing:
            wanted = MarketRegime.BEAR
        elif self.regime is not MarketRegime.BULL and rose >= self.bull_swing:
            wanted = MarketRegime.BULL

        opening = self.regime is MarketRegime.UNKNOWN
        if wanted is not self.regime and (opening or self._held >= self.minimum_phase):
            self.regime = wanted
            self._held = 0
            self.phase_age = 0
            # The extremes reset with the phase. A bear that ends must forget
            # the old high, or the next bull is measured against a peak two
            # years stale and can never start -- which is the exact failure a
            # drawdown-from-all-time-high rule has, and the reason this is not
            # that rule wearing a new name.
            self._peak = self._trough = value
        else:
            self.phase_age += 1
        return self.regime

    def summary(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "phase_age": self.phase_age,
            "smoothing": self.smoothing,
            "bear_swing": self.bear_swing,
            "bull_swing": self.bull_swing,
            "minimum_phase": self.minimum_phase,
        }


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
        self._phase_held = 0
        # The global level, fed the same composite. It is owned here rather than
        # built beside the detector so there is exactly one place that knows how
        # "the market" is measured, and both levels are guaranteed to be reading
        # the same market.
        self.cycle = CycleDetector(
            self.parameters.cycle_smoothing,
            self.parameters.cycle_bear_swing,
            self.parameters.cycle_bull_swing,
            self.parameters.cycle_minimum_phase,
        )

    # -- the tape ------------------------------------------------------------ #

    def observe(
        self,
        timestamp: datetime,
        closes: dict[str, float],
        above_trend: dict[str, bool],
        weights: dict[str, float] | None = None,
    ) -> MarketRegime:
        """Advance the detector by one bar of the market.

        WHICH assets count is `market_scope`. Under `universe` it is everything
        the tape served on this bar -- the whole listed market, which is what a
        market-wide trend is a property of. Under `basket` it is the six-name
        reference list, which is what this class did for its first year and is
        kept so the two can be compared on the same run.

        `above_trend` says, per asset, whether it closed above its own long
        average -- read straight off the backtester's `breadth_key` column. An
        asset missing from either map is absent from that side of the
        calculation rather than counted as a zero or a `False`: counting an
        unlisted or short-history asset as "not above its average" would
        manufacture a bearish breadth reading out of missing data, most severely
        in 2017-2018 where the market is still filling in.

        `weights` is trailing dollar turnover per asset, used only when
        `weighting` asks for it. It is a PROXY for size and it is the only one
        available: this laboratory holds no circulating supply, so it cannot
        build a capitalisation index and does not pretend to.
        """
        wide = self.parameters.market_scope == "universe"
        usable = {
            symbol: float(close)
            for symbol, close in closes.items()
            if (wide or symbol in self.reference) and close and float(close) > 0
        }
        self.seen_symbols.update(usable)

        # Chaining the WEIGHTED MEAN RETURN rather than averaging levels is what
        # makes the composite survive listings: an asset joins the average on
        # the first bar where it has both a close and a previous close, and its
        # absent history neither dilutes nor rebases the index. A price-average
        # or a sum-of-values index would jump the day a new asset appears -- a
        # level change with no market event behind it, which on a 386-asset
        # universe happens most weeks.
        #
        # That is also why this is not called a capitalisation index even under
        # turnover weighting. A real one is a SUM and moves when a coin is
        # created; this moves only when prices move.
        scheme = self.parameters.weighting
        pairs: list[tuple[float, float]] = []
        for symbol, close in usable.items():
            previous = self._previous_closes.get(symbol)
            if not previous:
                continue
            if scheme == "equal":
                weight = 1.0
            else:
                size = float((weights or {}).get(symbol) or 0.0)
                weight = math.sqrt(size) if scheme == "sqrt" else size
            if weight > 0:
                pairs.append((math.log(close / previous), weight))
        if pairs:
            total = sum(weight for _, weight in pairs)
            self._level *= math.exp(
                sum(step * weight for step, weight in pairs) / total
            )
        self._previous_closes.update(usable)

        # Breadth over the same set. This is the statistic the wider scope was
        # really worth having: on six names breadth can only report 0, 1/6, 2/6
        # ... and the thresholds sit at 0.35 and 0.50, so the difference between
        # a bull market and a bear one was one asset changing its mind.
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

        # The global level sees the same composite. Advanced before the middle
        # level so `cycle_regime` is this bar's answer and not the previous
        # one -- a gate reading a stale global trend is a gate off by a bar.
        self.cycle.observe(self._level)

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
            self._phase_held = 0
            return
        self._phase_held += 1
        if raw is self.regime:
            self._pending, self._streak = None, 0
        elif raw is self._pending:
            self._streak += 1
            # Two separate bars to clear. `confirmation_bars` asks the NEW
            # reading to persist; `minimum_phase` asks the CURRENT phase to have
            # lasted long enough to be a phase at all. Only the second bounds
            # how short an episode can be, and without it a fortnight's bounce
            # could rename the market.
            long_enough = self._phase_held >= self.parameters.minimum_phase
            if self._streak >= self.parameters.confirmation_bars and long_enough:
                self.regime, self._pending, self._streak = raw, None, 0
                self._phase_held = 0
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
            "cycle": self.cycle.summary(),
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
                "market_scope": self.parameters.market_scope,
                "minimum_phase": self.parameters.minimum_phase,
                "weighting": self.parameters.weighting,
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
