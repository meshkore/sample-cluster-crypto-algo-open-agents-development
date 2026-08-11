"""The three regime-conditional branches and the brain that composes them.

Pieces two, three and four of the operator's four-piece system. `regime.py`
answers *what market are we in*; this module answers *what do we do about it*,
and keeps the two separable on purpose: the detector can be scored on its own
labels, each branch can be swept on its own parameters, and the router can be
measured against a single-rule strategy to show whether switching earned
anything.

**Every branch reads indicators it did not compute.** The backtester serves
seventy-nine columns per symbol per tick, already computed and already causal,
so a branch here is a comparison between served numbers and nothing else. The
previous version of this file recomputed SMAs and RSIs from a growing list of
`Bar`s on every call, which was both the slowest thing in the laboratory and a
second implementation of arithmetic the instrument already owned -- two places
to be wrong about Wilder smoothing instead of one.

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
for, unlike everything above it, and it is why `DeviationBranch` exists and why
it is not in the bear branch.

Which rule occupies which regime is data, not doctrine: see `BRANCHES` for the
current assignment and `RULES` for the alternatives, each swappable per run so
the operator's four pieces stay independently tunable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from . import grammar
from .brains import register
from .policy import MoneyManagement, policy_keys
from .regime import (
    REFERENCE_BASKET,
    AssetDetector,
    MarketDetector,
    MarketRegime,
    RegimeParameters,
)
from .runner import Decision
from .space import Dimension, SearchSpace
from .universe import LiquidityGate


@dataclass
class SymbolState:
    """One symbol's memory. Owned by the brain, handed to whichever branch runs.

    Branches are shared across the whole universe and hold no per-symbol state
    of their own, so routing 386 assets costs six branch objects rather than
    2,316. `previous` is the last tick's indicator row and `previous_candle`
    the last tick's candle -- the two things a served column cannot express,
    because a rolling window that ends at the *previous* bar is not one of the
    seventy-nine.
    """

    active: bool = False
    remaining: int = 0
    previous: dict[str, Any] = field(default_factory=dict)
    previous_candle: dict[str, Any] = field(default_factory=dict)
    asset_detector: AssetDetector | None = None
    entered_at: datetime | None = None

    def clear(self) -> None:
        """Forget the position, keep the memory of the tape.

        `previous` deliberately survives: it is a fact about the market, not
        about the branch, and dropping it would make the bar after a regime
        handover unable to evaluate a breakout for one tick.
        """
        self.active = False
        self.remaining = 0


class _Branch:
    """Shared plumbing: prefixed parameters, so the same rule in two regimes is
    two independently tunable pieces rather than one shared configuration."""

    def __init__(self, params: dict[str, Any], prefix: str = ""):
        self.params, self.prefix = params, prefix

    def _get(self, name: str, default: Any) -> Any:
        return self.params.get(f"{self.prefix}{name}", default)

    def _number(self, name: str, default: float) -> float:
        return float(self._get(name, default))

    def _key(self, name: str, default: str) -> str:
        return str(self._get(name, default))

    def evaluate(
        self, candle: dict[str, Any], row: dict[str, Any], state: SymbolState
    ) -> bool:
        raise NotImplementedError


class TrendBranch(_Branch):
    """Ride the confirmed trend, enter on strength that is not yet exhausted.

    This is the H-SMARSI-001 mechanism, deliberately unchanged: it is the only
    rule in this laboratory with a positive walk-forward record (9 of 12 folds,
    consistency 0.75) and reusing it verbatim means any difference this router
    produces is attributable to the *switching*, not to a new bull rule
    smuggled in alongside it.
    """

    def evaluate(self, candle, row, state) -> bool:
        fast = row.get(self._key("fast_key", "sma_50"))
        slow = row.get(self._key("slow_key", "sma_200"))
        rsi = row.get(self._key("rsi_key", "rsi_14"))
        if fast is None or slow is None or rsi is None:
            return state.active
        floor = self._number("rsi_floor", 55.0)
        ceiling = self._number("rsi_ceiling", 90.0)
        trend_up = fast > slow
        if state.active:
            if not trend_up or rsi > ceiling:
                state.active = False
        elif trend_up and floor < rsi <= ceiling and candle["close"] > fast:
            state.active = True
        return state.active


class BreakoutBranch(_Branch):
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

    **The channel is read from the PREVIOUS tick.** The served `high_20`
    includes the current bar, and a bar's own high is by definition at or above
    its own close, so `close > high_20` can only be true on a doji -- the rule
    would silently never trade. The first version of this branch made exactly
    that mistake with a hand-rolled window and it took a control test to catch.
    """

    def evaluate(self, candle, row, state) -> bool:
        high_key = self._key("high_key", "high_20")
        low_key = self._key("low_key", "low_20")
        previous = state.previous
        highest, lowest = previous.get(high_key), previous.get(low_key)
        if highest is None or lowest is None:
            return state.active
        close = candle["close"]
        if state.active:
            if close < (highest + lowest) / 2:
                state.active = False
        elif close > highest:
            state.active = True
        return state.active


class ParticipationBranch(_Branch):
    """Hold only what is rising on its own terms. Absolute strength, not relative.

    Two measurements built this rule, and the second overturned the obvious
    reading of the first.

    **Never buy the dip.** RSI-30 bounces return -0.20% over the following 20
    bars inside a bear regime against +2.26% in a bull one, and Kotegawa's far
    more extreme deviation signal is -1.57%/120h in BEAR against +10.13% in
    BULL. A bear market is a sequence of failed bounces and a rule that buys
    them all is buying the failures. H-REGIME-001 did exactly that and returned
    -8.46%.

    **Relative strength does not work either.** 2026 looked like it should:
    the median asset fell 47% while 40 of 399 rose, several above +100%. But
    ranking the liquid universe by trailing 30-day return inside pre-2026 bear
    regimes shows *every decile negative* -- strongest -1.66%, weakest -1.52%,
    spread -0.13% over 7 days. The winners are visible in hindsight and not
    identifiable by momentum rank in advance. "Falling less than your peers" is
    not a reason to own something.

    **What does work is absolute trend confirmation.** Pre-2026, inside BEAR
    regimes, liquid assets, mean forward 30-day return:

    | condition                    | fwd 30d | n      |
    |------------------------------|---------|--------|
    | every liquid asset           | -5.41%  | 20,636 |
    | 90-day momentum positive     | -1.56%  |  6,080 |
    | above own 200-day average    | +2.50%  |  4,467 |
    | **above own 200d AND 50d**   | **+3.13%** | 3,988 |

    An 8.5-point swing against the bear baseline, from demanding that the asset
    be above both its long and short averages -- rising now *and* rising over
    the cycle. Being up over 90 days is not enough on its own and is in fact
    negative, which is why this tests the averages rather than a return.

    This branch needs BREADTH to do anything. In a bear market only a handful
    of names satisfy it, and on a five-asset basket of majors that all fell
    together the answer is correctly "hold nothing".
    """

    def evaluate(self, candle, row, state) -> bool:
        long_average = row.get(self._key("long_key", "sma_200"))
        short_average = row.get(self._key("short_key", "sma_50"))
        if long_average is None or short_average is None:
            return state.active
        # Symmetric entry and exit. There is no asymmetry to earn here: the base
        # rate inside a bear regime is that advances end, so the moment the
        # asset stops being above both averages the reason to hold it is gone.
        state.active = (
            candle["close"] > long_average and candle["close"] > short_average
        )
        return state.active


class DeviationBranch(_Branch):
    """Kotegawa's deviation rate: buy capitulation, sell the reversion.

    Takashi Kotegawa (BNF) traded the 25-day moving-average deviation rate --
    buying liquid names 20-35% BELOW their 25-day average and exiting as price
    reverted toward it. That is not the RSI-30 dip this laboratory already
    rejected; it is one to two orders of magnitude more extreme, a capitulation
    filter rather than a pullback filter.

    Measured, pooled across the basket 2017-2025, forward return from the
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

    The reference average is `sma_20` on daily bars, the closest served column
    to his 25 days. On an hourly family, point `average_key` at a column whose
    window is roughly 25 days of those bars -- running it on a 20-BAR hourly
    average would be a one-day mean reversion wearing his name.
    """

    def evaluate(self, candle, row, state) -> bool:
        average = row.get(self._key("average_key", "sma_20"))
        if not average:
            return state.active
        deviation = candle["close"] / average - 1
        if state.active:
            # Exit on reversion toward the average, not at a fixed profit
            # target: the trade's thesis is the gap closing, so the gap closing
            # IS the exit. A target unrelated to the signal would leave the
            # position open after its reason had expired.
            if deviation >= self._number("exit_deviation", -0.05):
                state.active = False
        elif deviation <= self._number("entry_deviation", -0.25):
            state.active = True
        return state.active


class ClimaxBranch(_Branch):
    """The incumbent champion's mechanism, made available per regime.

    `volume_climax` (H-REV-001's family) is the only strategy in this laboratory
    with a positive 2026 result: +3.46% on 41 trades at 2.03% drawdown, in a year
    whose median asset fell 47%. It buys a sharp one-bar drop that arrives on
    heavy volume and holds for a fixed number of bars.

    It is wired in as a selectable branch rule so it can be tested INSIDE a bear
    regime on pre-2026 evidence, rather than inferred to work there from a single
    forward number that is the maximum of 313 evaluations.
    """

    def evaluate(self, candle, row, state) -> bool:
        average_volume = row.get(self._key("volume_key", "volume_sma_20"))
        drop = row.get(self._key("return_key", "return_1"))
        if not average_volume or drop is None:
            return state.active
        relative = candle["volume"] / average_volume
        if drop <= self._number("return_threshold", -0.025) and relative > self._number(
            "volume_multiple", 3.5
        ):
            state.remaining = int(self._number("holding", 3))
        state.active = state.remaining > 0
        state.remaining = max(0, state.remaining - 1)
        return state.active


class SupertrendBranch(_Branch):
    """SuperTrend's bullish flip, authorised by ADX. H-STA-001.

    The entry trigger is the flip itself -- it fires exactly once, on the bar
    the band is crossed, not on every bar the trend happens to still be bullish,
    or this would re-enter a position it never exited. ADX authorises that flip
    rather than gating every bar, so a strong trend that started before ADX
    caught up is not retroactively vetoed once the position is already open.

    The flip is detected against the previous tick's `supertrend_direction`
    because a flip is a change and a served column is a level.
    """

    def evaluate(self, candle, row, state) -> bool:
        direction = row.get(self._key("direction_key", "supertrend_direction"))
        if direction is None:
            return state.active
        if direction <= 0:
            state.active = False
            return False
        previous = state.previous.get(
            self._key("direction_key", "supertrend_direction")
        )
        if previous is not None and previous <= 0:
            adx = row.get(self._key("adx_key", "adx"))
            state.active = adx is not None and adx >= self._number(
                "adx_threshold", 20.0
            )
        return state.active


class EvolvedBranch(_Branch):
    """A rule the laboratory invented, carried as data rather than as code.

    Reads `<prefix>entry_rule` and `<prefix>exit_rule` -- expression trees over
    the served columns (see `grammar.py`). Everything above this line is a
    mechanism a person wrote and the search may only tune; this is the one
    branch whose *shape* the loop can change, which is what lets an iteration
    discover a combination nobody proposed.

    An unknown answer holds the position. A rule whose columns have not filled
    yet has not said "sell", and reading it as a sell would liquidate the book
    every time a referenced window was warming.
    """

    def evaluate(self, candle, row, state) -> bool:
        entry = self._get("entry_rule", None)
        if not entry:
            return state.active
        previous_row = state.previous
        previous_candle = state.previous_candle or candle
        try:
            if state.active:
                exit_rule = self._get("exit_rule", None)
                if exit_rule:
                    verdict = grammar.evaluate(
                        exit_rule, candle, row, previous_row, previous_candle
                    )
                    if verdict is True:
                        state.active = False
                    return state.active
                # No exit rule: the entry condition failing IS the exit, which
                # is how every hand-written branch above behaves.
                verdict = grammar.evaluate(
                    entry, candle, row, previous_row, previous_candle
                )
                if verdict is False:
                    state.active = False
                return state.active
            verdict = grammar.evaluate(
                entry, candle, row, previous_row, previous_candle
            )
            state.active = verdict is True
        except grammar.GrammarError:
            # A malformed tree is a dead genome, not a dead run. It stands
            # aside for the whole backtest and the objective rejects it for
            # taking no trades, which is the correct verdict.
            state.active = False
        return state.active


RULES: dict[str, type] = {
    "trend": TrendBranch,
    "breakout": BreakoutBranch,
    "participation": ParticipationBranch,
    "deviation": DeviationBranch,
    "climax": ClimaxBranch,
    "supertrend": SupertrendBranch,
    "evolved": EvolvedBranch,
}

# Which rule runs in which regime. Every entry is a measurement, not a
# preference, and the mapping is overridable per run (`bull_rule`,
# `sideways_rule`, `bear_rule`) so each of the operator's four pieces can be
# swapped and scored on its own without touching the other three.
BRANCHES: dict[MarketRegime, str] = {
    MarketRegime.BULL: "trend",
    MarketRegime.SIDEWAYS: "deviation",
    MarketRegime.BEAR: "participation",
}

# Regime exposure, expressed as the confidence the money-management layer sizes
# by. Read the warning in `notional_for`: a weight below the policy's
# `minimum_confidence` does not reduce the branch's exposure, it deletes the
# branch, silently and with no trades to show for it.
DEFAULT_WEIGHTS: dict[MarketRegime, float] = {
    MarketRegime.BULL: 1.0,
    MarketRegime.SIDEWAYS: 0.6,
    MarketRegime.BEAR: 0.3,
}


def _as_datetime(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@register(
    "four-module",
    "A market-wide trend detector routing three regime-conditional branches, "
    "sized by the trading system's own money management.",
)
class FourModuleBrain:
    """H-ROUTER-002: one detector, three branches, one live at a time.

    The operator's four pieces, assembled: a major-trend detector (`regime.py`),
    a bull branch, a sideways branch and a bear branch, with the mandate and the
    sizing owned here because they are decisions.

    Four behaviours are not obvious and all are load-bearing.

    **Only the live branch is evaluated.** Each branch is a comparison between
    served columns, so a branch dormant for two years is not cold when it takes
    over -- its first call reads a 200-day average the backtester has been
    maintaining all along. Evaluating all three every bar would change nothing
    except the bill.

    **A regime change forces flat for one bar.** When the label moves, every
    open position is closed and no new one is opened, whatever the incoming
    branch wants. A bull trend position does not ride into a confirmed bear on
    the incoming branch's say-so, and the handover appears in the trade ledger
    as its own closed trade rather than being silently inherited.

    **The detector needs a run-up and refuses to fake one.** It reports UNKNOWN
    until it has seen `trend_period + slope_period` bars of the reference
    basket, and this brain does not trade an UNKNOWN market. Launch a forward
    evaluation with a `start` well before the window you care about and a
    `trade_from` at its boundary: equity stays flat while the detector warms, so
    the recorded return is the return of the period you asked about.

    **The mandate is enforced here, not by the instrument.** The backtester has
    no view on whether a 30% loss should end a run. `Decision.stop` is this
    brain's request, and different contributors will legitimately disagree
    about when to make it.
    """

    def __init__(self, **params: Any):
        self.params = dict(params)
        self.regime_scope = str(params.get("regime_scope", "market"))
        if self.regime_scope not in ("market", "asset"):
            raise ValueError("regime_scope must be 'market' or 'asset'")

        self.reference_symbols = tuple(
            params.get("reference_symbols") or REFERENCE_BASKET
        )
        self.detector = MarketDetector(
            RegimeParameters(
                trend_period=int(params.get("trend_period", 100)),
                slope_period=int(params.get("slope_period", 20)),
                bull_breadth=float(params.get("bull_breadth", 0.50)),
                bear_breadth=float(params.get("bear_breadth", 0.35)),
                confirmation_bars=int(params.get("confirmation_bars", 5)),
                breadth_key=str(params.get("breadth_key", "sma_50")),
                require_slope=bool(params.get("require_slope", False)),
            ),
            self.reference_symbols,
        )
        # Whether the reference basket may also be traded. Off by default: a
        # universe is usually chosen for liquidity and the basket for history,
        # and silently trading six majors nobody asked for would make two runs
        # on the same universe incomparable.
        self.trade_reference = bool(params.get("trade_reference", False))

        # Where in a bear market participation is allowed at all.
        #
        # `bear_min_age` counts bars into the CURRENT bear episode, so its scale
        # is set by how long the detector's episodes are -- it is not a free
        # number. The old 240 was read off a detector that produced six BEAR
        # episodes in eight years with a 324-bar maximum. The detector measured
        # in H-L081D produces 24 episodes with a 127-bar maximum, and under it
        # NOT ONE BAR of the tape would have passed 240. Left alone, the faster
        # label would have arrived to find the gate it feeds welded shut, and
        # the whole repair would have measured as no change at all.
        #
        # 30 is the same idea rescaled: roughly the first quartile of the new
        # episode lengths, so the gate opens after the first month of a fall and
        # stays open for 588 of the 1192 BEAR bars. It is a first cut on a
        # searchable dimension, not an optimum.
        self.min_bear_depth = float(params.get("bear_min_depth", 0.70))
        self.min_bear_age = int(params.get("bear_min_age", 30))

        # Asset scope (H-014). "market" is the original design: one detector,
        # one label, every asset routed the same way. Its structural limit
        # showed up in the forward window -- 2026 is labelled BEAR for 100% of
        # the year, so every asset is forced onto the bear branch, including
        # the 40 of 399 that finished positive and three above +140%. A single
        # global switch cannot reach an asset in its own clean uptrend while
        # the market falls. "asset" keeps the market detector but demotes it to
        # a risk governor: the bear-phase gate still decides whether the
        # environment is fit to trade at all, and the asset's own trend decides
        # WHICH mechanism runs.
        self.asset_trend_key = str(params.get("asset_trend_key", "sma_200"))
        self.asset_slope_period = int(params.get("asset_slope_period", 20))
        self.asset_confirmation_bars = int(params.get("asset_confirmation_bars", 20))

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
            regime: RULES[name](self.params, f"{regime.value.lower()}_")
            for regime, name in self.rule_names.items()
        }

        # The mandate. 30% abort with the de-leverage ramp ending at 25% is the
        # operator's standing instruction, and the two are separate numbers
        # precisely so raising one does not silently move the other.
        defaults = {
            "risk_per_trade": 0.02,
            "maximum_position_fraction": 0.05,
            "maximum_concurrent_assets": 15,
            "stop_loss_pct": 0.35,
            "take_profit_pct": 0.10,
            "risk_distance_pct": 0.20,
            "maximum_drawdown": 0.30,
            "drawdown_deleverage_start": 0.10,
            "drawdown_deleverage_end": 0.25,
            # Peak basis, because the operator's standing rule is literal:
            # abort when maximum drawdown reaches 30%, and "maximum drawdown"
            # means distance below the running high. The first run of this
            # brain defaulted to `ratchet` and finished at +43.6% having gone
            # 42.0% below its peak -- inside the ratchet floor, and a plain
            # breach of the mandate the laboratory publishes.
            #
            # The pathology that made `peak` dangerous is bounded now. S00852
            # bricked because the de-leverage ramp ended at the SAME number as
            # the abort: at the ramp's end the risk budget is zero, nothing
            # opens, equity cannot grow, the peak never updates and the
            # drawdown never shrinks -- four and a half years flat. Here the
            # ramp ends at 25% and the abort fires at 30%, so a run can only
            # sit in that five-point band until it either recovers or ends.
            "drawdown_basis": "peak",
        }
        overrides = {key: params[key] for key in policy_keys() if key in params}
        self.policy = MoneyManagement(**{**defaults, **overrides})

        # Which assets exist to be bought, decided per bar rather than by the
        # list someone passed in. `minimum_daily_quote_volume` has been a field
        # on the policy since the beginning and was read by nothing on this
        # path: every run this laboratory has published could size a position
        # in a coin trading fifty thousand dollars a day. `tradeable_assets` is
        # the width of the book we are willing to run on top of that floor.
        #
        # Neither is in MODULE_KEYS["POLICY"], so no search moves them. The
        # universe is a statement about where the system is deployed, not a
        # parameter to be tuned until the past looks better.
        self.universe = LiquidityGate(
            minimum_turnover=float(self.policy.minimum_daily_quote_volume),
            maximum_assets=int(params.get("tradeable_assets", 0) or 0),
        )

        trade_from = params.get("trade_from")
        self.trade_from = _as_datetime(trade_from) if trade_from else None
        self.reset()

    def reset(self) -> None:
        self.detector.reset()
        self.states: dict[str, SymbolState] = {}
        self.last_regime: dict[str, MarketRegime] = {}
        self.peak_equity = 0.0
        self.bars_seen = 0
        self.bars_traded = 0

    # -- the one method a brain owes the laboratory -------------------------- #

    def decide(self, tick: dict[str, Any]) -> Decision:
        decision = Decision()
        candles = tick.get("candles") or {}
        indicators = tick.get("indicators") or {}
        account = tick["account"]
        equity = account["equity"]
        initial = account["initial_capital"]
        moment = _as_datetime(tick["timestamp"])
        self.bars_seen += 1

        market = self._observe_market(moment, candles, indicators)

        self.peak_equity = max(self.peak_equity, equity, initial)
        floor = self.policy.equity_floor(initial, self.peak_equity)
        if equity <= floor:
            decision.stop = (
                f"drawdown mandate breached: equity {equity:,.0f} at or below "
                f"the {self.policy.drawdown_basis} floor of {floor:,.0f} "
                f"(deposit {initial:,.0f}, peak {self.peak_equity:,.0f})"
            )
            return decision
        drawdown = self.policy.drawdown_against(equity, self.peak_equity, initial)

        positions = account["positions"]
        warming = self.trade_from is not None and moment < self.trade_from
        held = set(positions)
        # Recomputed every bar from this bar's own trailing turnover, so a coin
        # enters the day it becomes liquid and leaves the day it stops being
        # liquid, with no list to maintain and no rebalance date to remember.
        # Buys only: a holding whose liquidity has collapsed is exactly the one
        # that must stay closeable.
        tradeable = (
            self.universe.tradeable(indicators) if self.universe.enabled else None
        )
        # Every symbol with a position must be evaluated even if it has no bar
        # this tick, or a delisted holding would be held for ever.
        for symbol in sorted(set(candles) | held):
            state = self._state(symbol)
            row = indicators.get(symbol) or {}
            candle = candles.get(symbol)
            regime = self._route(symbol, market, candle, row)
            changed = (
                symbol in self.last_regime and self.last_regime[symbol] is not regime
            )
            self.last_regime[symbol] = regime

            if candle is None:
                continue
            live = regime is not MarketRegime.UNKNOWN and self._permitted(market)
            signal = False
            if changed:
                # Flat through the handover, and the branch's state is cleared
                # so it does not resume mid-position if its regime returns.
                state.clear()
            elif live:
                signal = self.branches[regime].evaluate(candle, row, state)

            if symbol in positions:
                reason = self._exit_reason(
                    positions[symbol], state, signal, changed, live, moment
                )
                if reason:
                    decision.sell(symbol, reason[0], reason[1])
                    state.clear()
            elif signal and not warming and (tradeable is None or symbol in tradeable):
                self._maybe_buy(
                    decision, symbol, regime, equity, drawdown, account, positions
                )
            state.previous = row
            state.previous_candle = candle

        if warming:
            decision.note = (
                f"warming the detector: {self.bars_seen} bars observed, market "
                f"{market.value}, trading opens {self.trade_from:%Y-%m-%d}"
            )
        elif not decision.orders:
            self.bars_traded += 1
            decision.note = (
                f"{market.value} · depth {self.detector.depth:.0%} · age "
                f"{self.detector.episode_age} · held {len(positions)}"
            )
        else:
            self.bars_traded += 1
        return decision

    # -- routing ------------------------------------------------------------- #

    def _observe_market(self, moment, candles, indicators) -> MarketRegime:
        breadth_key = self.detector.parameters.breadth_key
        closes, above = {}, {}
        for symbol in self.reference_symbols:
            candle = candles.get(symbol)
            if candle is None:
                continue
            closes[symbol] = candle["close"]
            average = (indicators.get(symbol) or {}).get(breadth_key)
            if average is not None:
                above[symbol] = candle["close"] > average
        return self.detector.observe(moment, closes, above)

    def _state(self, symbol: str) -> SymbolState:
        state = self.states.get(symbol)
        if state is None:
            state = SymbolState()
            if self.regime_scope == "asset":
                state.asset_detector = AssetDetector(
                    self.asset_trend_key,
                    self.asset_slope_period,
                    self.asset_confirmation_bars,
                )
            self.states[symbol] = state
        return state

    def _route(self, symbol, market, candle, row) -> MarketRegime:
        """Which branch owns this symbol on this bar."""
        if not self.trade_reference and symbol in self.reference_symbols:
            return MarketRegime.UNKNOWN
        if self.regime_scope == "market":
            return market
        state = self._state(symbol)
        if candle is None or state.asset_detector is None:
            return state.asset_detector.regime if state.asset_detector else market
        return state.asset_detector.observe(candle["close"], row)

    def _permitted(self, market: MarketRegime) -> bool:
        """Stand aside in the shallow, early part of a market-wide bear.

        The regime label says "bear"; it does not say WHERE in the bear. Pre-2026
        those are opposite environments -- 30-50% below the composite high
        returns -32.30% over the next 30 days at a 9% hit rate, while 70-100%
        below returns +6.86% at 52%. Participating on the label alone means
        taking the worst measured cell in this laboratory in order to reach the
        good one.

        Either condition qualifies: deep enough, or old enough. They are two
        views of the same exhaustion and neither dominates -- the 2018 bear got
        deep quickly, the 2022 one took longer. The thresholds sit on the
        boundaries of the measured bands and have NOT been bracketed, so they
        are a first cut rather than an optimum; both are parameters precisely so
        a sweep can move them one at a time.

        In asset scope this is the market detector's only remaining job: it
        governs whether the environment is fit to trade, not which rule runs.
        """
        if market is not MarketRegime.BEAR:
            return market is not MarketRegime.UNKNOWN
        return (
            self.detector.depth >= self.min_bear_depth
            or self.detector.episode_age >= self.min_bear_age
        )

    # -- what to do about it -------------------------------------------------- #

    def _exit_reason(self, holding, state, signal, changed, live, moment):
        move = holding["unrealised_pct"]
        if changed:
            return "REGIME_HANDOVER", "regime changed; flat through the switch"
        if not live:
            return "REGIME_GATE", "the environment is no longer fit to trade"
        if move >= self.policy.take_profit_pct:
            return "TAKE_PROFIT", f"+{move:.1%} reached target"
        if move <= -self.policy.stop_loss_pct:
            return "STOP_LOSS", f"{move:.1%} breached stop"
        days = self.policy.maximum_holding_days
        if days is not None:
            entered = _as_datetime(holding["entry_time"])
            if (moment - entered).days >= days:
                return "TIME_STOP", f"held {(moment - entered).days} days"
        if not signal:
            return "SIGNAL_EXIT", "the branch no longer wants it"
        return None

    def _maybe_buy(
        self, decision, symbol, regime, equity, drawdown, account, positions
    ):
        room = self.policy.maximum_concurrent_assets - len(positions)
        if room - len([o for o in decision.orders if o["side"] == "BUY"]) <= 0:
            return
        notional = self.policy.notional_for(equity, self.weights[regime], drawdown)
        if notional <= 0:
            return
        committed = sum(o["notional"] for o in decision.orders if o["side"] == "BUY")
        # The session caps a fill at whatever cash is left, so an over-committed
        # batch would silently fill the alphabetically-first orders at full size
        # and the rest at whatever remained -- position sizes decided by symbol
        # name. Refusing here keeps every fill the size that was decided.
        if committed + notional > account["cash"]:
            return
        decision.buy(
            symbol,
            notional,
            f"{regime.value}_{self.rule_names[regime].upper()}",
            f"{self.rule_names[regime]} branch, {regime.value.lower()} regime "
            f"at {self.weights[regime]:.0%} confidence",
        )

    # -- what a search is allowed to move ------------------------------------- #

    @staticmethod
    def search_space() -> Any:
        """The knobs, and how far each may travel. Declared by the hypothesis.

        A brain publishes this so the optimiser never has to know what a
        parameter means. Everything absent is fixed by construction and a search
        must not touch it -- the reference basket, `trade_from`, the universe.

        Ranges are wide on purpose. Narrow ranges centred on today's defaults
        are not a search, they are a confirmation: the optimum is inside the box
        before it starts. Where a bound is a measurement rather than a guess it
        says so.
        """
        return SearchSpace(
            (
                # --- the detector -------------------------------------------
                Dimension("trend_period", 50, 300, integer=True),
                Dimension("slope_period", 5, 60, integer=True),
                Dimension("confirmation_bars", 3, 45, integer=True),
                Dimension("bull_breadth", 0.35, 0.75),
                Dimension("bear_breadth", 0.15, 0.50),
                # Which trailing average breadth is counted against. It was
                # pinned to `sma_200` and never searchable, and H-L081D measured
                # that moving it to `sma_50` is worth 3.2 points of BEAR-minus-
                # BULL separation in the fold that falls. Only windows the
                # backtester actually serves appear here; naming one it does not
                # would make every reference asset silently absent from breadth.
                Dimension("breadth_key", choices=("sma_50", "sma_100", "sma_200")),
                # Whether the trend average's SLOPE must also have turned. This
                # was a hardcoded AND, and it is the term that made the detector
                # arrive after the bottom -- see `RegimeParameters`. It is a
                # dimension rather than a deletion because the search, not this
                # comment, should decide whether it earns its place per fold.
                Dimension("require_slope", choices=(False, True)),
                # --- the bear gate ------------------------------------------
                # The floor tracks the detector: `bear_min_age` counts bars into
                # a BEAR episode, and the measured detector's longest episode is
                # 127 bars, so the old 30-400 range was mostly unreachable.
                Dimension("bear_min_depth", 0.30, 0.90),
                Dimension("bear_min_age", 5, 200, integer=True),
                # --- which mechanism runs where -----------------------------
                Dimension("bull_rule", choices=tuple(sorted(RULES))),
                Dimension("sideways_rule", choices=tuple(sorted(RULES))),
                Dimension("bear_rule", choices=tuple(sorted(RULES))),
                Dimension("regime_scope", choices=("market", "asset")),
                # A weight below the policy's `minimum_confidence` does not
                # reduce a branch's exposure, it deletes the branch. The floor
                # here is that threshold, so the search cannot silently buy a
                # do-nothing genome.
                Dimension("bull_weight", 0.25, 1.0),
                Dimension("sideways_weight", 0.25, 1.0),
                Dimension("bear_weight", 0.25, 1.0),
                # --- the branches -------------------------------------------
                Dimension("bull_rsi_floor", 40.0, 70.0),
                Dimension("bull_rsi_ceiling", 70.0, 95.0),
                Dimension("sideways_entry_deviation", -0.45, -0.10),
                Dimension("sideways_exit_deviation", -0.15, 0.05),
                Dimension("bear_return_threshold", -0.10, -0.01),
                Dimension("bear_volume_multiple", 1.5, 8.0),
                Dimension("bear_holding", 1, 20, integer=True),
                # --- money management ---------------------------------------
                # The operator's rule is not searchable: the abort stays at 30%
                # and the ramp ends at 25%, so neither appears here.
                Dimension("risk_per_trade", 0.005, 0.05),
                Dimension("maximum_position_fraction", 0.02, 0.15),
                Dimension("maximum_concurrent_assets", 5, 40, integer=True),
                Dimension("risk_distance_pct", 0.05, 0.40),
                Dimension("take_profit_pct", 0.04, 0.60),
                Dimension("stop_loss_pct", 0.05, 0.50),
                Dimension("maximum_holding_days", 3, 120, integer=True),
            )
        )

    # -- observability -------------------------------------------------------- #

    def parameters(self) -> dict[str, Any]:
        """Everything that makes this run this run, flat and scalar.

        The orchestrator derives `backtest_id` from this, so a knob missing here
        is a knob two runs can differ on while sharing an id. Scalar attributes
        alone were not enough: the rule names and weights live in dictionaries
        and the scope, gates and branch prefixes are what the whole hypothesis
        is about.
        """
        described: dict[str, Any] = {
            "regime_scope": self.regime_scope,
            "trade_reference": self.trade_reference,
            "reference_symbols": ",".join(self.reference_symbols),
            "trend_period": self.detector.parameters.trend_period,
            "slope_period": self.detector.parameters.slope_period,
            "bull_breadth": self.detector.parameters.bull_breadth,
            "bear_breadth": self.detector.parameters.bear_breadth,
            "confirmation_bars": self.detector.parameters.confirmation_bars,
            "breadth_key": self.detector.parameters.breadth_key,
            "require_slope": self.detector.parameters.require_slope,
            "bear_min_depth": self.min_bear_depth,
            "bear_min_age": self.min_bear_age,
            "asset_trend_key": self.asset_trend_key,
            "asset_slope_period": self.asset_slope_period,
            "asset_confirmation_bars": self.asset_confirmation_bars,
            "trade_from": self.trade_from.isoformat() if self.trade_from else None,
        }
        for regime, name in self.rule_names.items():
            described[f"{regime.value.lower()}_rule"] = name
            described[f"{regime.value.lower()}_weight"] = self.weights[regime]
        # Branch-level overrides the caller supplied, so a swept parameter is
        # part of the identity rather than an invisible difference.
        for key, value in sorted(self.params.items()):
            if key not in described and isinstance(value, (int, float, str, bool)):
                described[key] = value
        # An evolved rule is a tree, not a scalar, so it would vanish from the
        # identity and two different invented mechanisms would share a
        # `backtest_id`. Carry a stable digest of it instead.
        for regime in self.rule_names:
            for slot in ("entry_rule", "exit_rule"):
                tree = self.params.get(f"{regime.value.lower()}_{slot}")
                if tree:
                    described[f"{regime.value.lower()}_{slot}_digest"] = hashlib.sha256(
                        json.dumps(tree, sort_keys=True).encode()
                    ).hexdigest()[:16]
        return described

    def diagnostics(self) -> dict[str, Any]:
        return {
            "regime_scope": self.regime_scope,
            "rules": {r.value: name for r, name in self.rule_names.items()},
            "weights": {r.value: w for r, w in self.weights.items()},
            "bear_phase_gate": {
                "min_depth": self.min_bear_depth,
                "min_age": self.min_bear_age,
            },
            "trade_from": self.trade_from.isoformat() if self.trade_from else None,
            "bars_seen": self.bars_seen,
            "bars_traded": self.bars_traded,
            "policy": {key: getattr(self.policy, key) for key in policy_keys()},
            "detector": self.detector.summary(),
            "separation": self.detector.separation(),
        }


# Brains that subclass `FourModuleBrain` register from here, after the name they
# need is defined, rather than from `brains._register_builtins`. Registering
# them there worked only when something else had already imported this module
# first; entering through `quantlab_trading.regime_system` -- which is what the
# loop's own entry point does -- raised ImportError on a partially initialised
# module. Test collection happened to import in the lucky order, so the suite
# stayed green while the loop could not start.
from . import codex_regime_system  # noqa: E402,F401
