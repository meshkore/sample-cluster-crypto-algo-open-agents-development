import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from quantlab.models import Bar
from quantlab.regime import (
    MarketContext,
    MarketRegime,
    RegimeParameters,
    RegimeTimeline,
)
from quantlab.regime_system import DEFAULT_WEIGHTS
from quantlab.strategies import build_strategy

START = datetime(2021, 1, 1, tzinfo=timezone.utc)
DAY = 86_400.0


def _bars(closes: list[float]) -> list[Bar]:
    bars, previous = [], closes[0]
    for i, close in enumerate(closes):
        bars.append(
            Bar(
                timestamp=START + timedelta(days=i),
                open=previous,
                high=max(previous, close) * 1.02,
                low=min(previous, close) * 0.98,
                close=close,
                volume=1_000.0,
            )
        )
        previous = close
    return bars


def _staircase(start: float, count: int, rise: float = 3.0, dip: float = 1.0):
    """A rising series that pulls back, because a straight line is untradeable.

    The bull branch reuses H-SMARSI-001, which enters only while RSI sits
    inside a band. A perfectly monotone advance has no down bars at all, so its
    RSI pins at 100 -- above the ceiling -- and the branch correctly refuses to
    buy something that vertical. Testing it on a straight line measures the
    test's series, not the rule.
    """
    closes, level = [], start
    for i in range(count):
        level += rise if i % 4 else -dip
        closes.append(level)
    return closes


def _forced(regimes: list[MarketRegime]) -> MarketContext:
    """A timeline that hands the router a chosen regime on each bar.

    The stamps are placed one full bar earlier than the bars they govern,
    because `RegimeTimeline.at()` only releases a label once its own bar has
    closed. Building the stub any other way would silently test the router
    against labels it could never legally see.
    """
    stamps = [START + timedelta(days=i - 1) for i in range(len(regimes))]
    return MarketContext(
        regimes=RegimeTimeline(
            stamps=stamps,
            labels=list(regimes),
            index=[100.0] * len(regimes),
            breadth=[1.0] * len(regimes),
            bar_seconds=DAY,
            parameters=RegimeParameters(),
        )
    )


SHORT_PERIODS = {
    "bull_fast_period": 5,
    "bull_slow_period": 12,
    "bull_rsi_period": 5,
    "sideways_entry_period": 6,
    "sideways_exit_period": 6,
    "bear_long_period": 12,
    "bear_short_period": 5,
}


def _router(regimes: list[MarketRegime], **params):
    return build_strategy(
        "regime_router", {**SHORT_PERIODS, **params}, _forced(regimes)
    )


def _drive(strategy, bars: list[Bar]) -> list[float]:
    return [strategy.on_bar(bars[: i + 1]) for i in range(len(bars))]


class RouterContractTest(unittest.TestCase):
    def test_a_router_without_a_market_context_refuses_to_exist(self):
        """The failure has to be loud.

        A router that quietly fell back to a single rule would publish a
        regime-switching result produced without a regime -- an unreadable
        number of exactly the kind this laboratory already has too many of.
        """
        with self.assertRaises(ValueError) as raised:
            build_strategy("regime_router", {})
        self.assertIn("MarketContext", str(raised.exception))

    def test_the_warmup_regime_stands_aside(self):
        """UNKNOWN means no position, not a default branch.

        The detector needs ~220 bars before it can label anything, and the
        operator accepted that the system does not trade during that window.
        """
        bars = _bars([100.0 + i for i in range(40)])
        signals = _drive(_router([MarketRegime.UNKNOWN] * 40), bars)
        self.assertEqual(set(signals), {0.0})

    def test_every_default_weight_clears_the_policy_confidence_floor(self):
        """A weight below `minimum_confidence` deletes its branch silently.

        The portfolio vetoes any signal under the floor before sizing it, so a
        bear weight of 0.2 against a floor of 0.25 does not trade at 20% size,
        it never trades at all -- and the only symptom is a branch with no
        trades, which reads as "the rule found nothing".
        """
        config = json.loads(
            (Path(__file__).resolve().parents[1] / "config/default.json").read_text()
        )
        floor = float(config["portfolio"]["minimum_confidence"])
        for regime, weight in DEFAULT_WEIGHTS.items():
            self.assertGreaterEqual(
                weight,
                floor,
                f"{regime.value} weight {weight} is below the {floor} confidence "
                "floor, so that branch would never open a position",
            )


class RouterSwitchingTest(unittest.TestCase):
    def test_the_live_branch_output_is_scaled_by_its_regime_weight(self):
        """Same bars, same branch rule, three different exposures."""
        bars = _bars(_staircase(100.0, 40))
        full = _drive(_router([MarketRegime.BULL] * 40), bars)
        weighted = _drive(_router([MarketRegime.BULL] * 40, bull_weight=0.4), bars)
        self.assertGreater(max(full), 0.0)
        self.assertAlmostEqual(max(weighted), max(full) * 0.4)

    def test_a_regime_change_forces_flat_for_exactly_one_bar(self):
        """The handover is a closed trade, not an inherited position.

        A bull trend position must not ride into a confirmed bear on the
        incoming branch's say-so, and the exit has to appear in the ledger as
        its own trade rather than being absorbed silently.
        """
        bars = _bars(_staircase(100.0, 40))
        regimes = [MarketRegime.BULL] * 25 + [MarketRegime.SIDEWAYS] * 15
        signals = _drive(_router(regimes), bars)
        self.assertGreater(signals[24], 0.0)
        self.assertEqual(signals[25], 0.0, "the switching bar must be flat")

    def test_a_branch_does_not_resume_a_position_when_its_regime_returns(self):
        """State is cleared at the switch, so re-entry is a fresh decision.

        Without the reset a branch left holding `active=True` would resume mid
        position on a regime it had been absent from for months, sizing into a
        setup its own entry rule never re-confirmed.
        """
        bars = _bars(_staircase(100.0, 20) + [140.0 - 3.0 * i for i in range(20)])
        regimes = (
            [MarketRegime.BULL] * 18
            + [MarketRegime.BEAR] * 4
            + [MarketRegime.BULL] * 18
        )
        router = _router(regimes)
        _drive(router, bars)
        self.assertFalse(router.branches[MarketRegime.BULL].active)


class BranchBehaviourTest(unittest.TestCase):
    """The branch contents the measurement dictated, pinned as behaviour.

    Pooled over 2017-2025 across the six reference assets, an RSI-30 bounce
    returned -0.20% over the following 20 bars inside a BEAR regime and +2.26%
    inside a BULL one. The bear branch therefore buys confirmed strength, never
    weakness -- which is also why H-REGIME-001's bear bounce failed.
    """

    def test_the_bear_branch_needs_both_averages_not_just_the_short_one(self):
        """A bounce above the 50-day inside a downtrend is not participation.

        This is the property that separates this rule from the one it replaced.
        Pre-2026, inside bear regimes, "above the short average" alone returns
        -3.55% over the next 30 days while "above both" returns +3.13%. A rule
        satisfied by the short average alone is buying exactly the failed
        rallies the bear measurements warn about.
        """
        # A long decline, then a rally big enough to clear the short average
        # but nowhere near the long one.
        closes = [200.0 - 1.2 * i for i in range(150)] + [
            20.0 + 1.5 * i for i in range(25)
        ]
        bars = _bars(closes)
        router = _router(
            [MarketRegime.BEAR] * len(closes),
            bear_long_period=140,
            bear_short_period=10,
        )
        signals = _drive(router, bars)
        i = len(closes) - 1
        short_average = sum(closes[i - 9 : i + 1]) / 10
        long_average = sum(closes[i - 139 : i + 1]) / 140
        self.assertGreater(
            closes[i], short_average, "fixture must clear the short average"
        )
        self.assertLess(
            closes[i], long_average, "fixture must stay under the long average"
        )
        self.assertEqual(signals[-1], 0.0)

    def test_the_bear_branch_refuses_to_buy_a_crash(self):
        crash = [100.0 - 3.0 * i for i in range(40)]
        bars = _bars(crash)
        signals = _drive(_router([MarketRegime.BEAR] * 40), bars)
        self.assertEqual(set(signals), {0.0})

    def test_the_bear_branch_participates_in_a_confirmed_advance(self):
        closes = [100.0 - 2.0 * i for i in range(20)] + [
            62.0 + 3.0 * i for i in range(30)
        ]
        bars = _bars(closes)
        signals = _drive(_router([MarketRegime.BEAR] * 50), bars)
        self.assertGreater(max(signals), 0.0)
        self.assertAlmostEqual(
            max(signals), DEFAULT_WEIGHTS[MarketRegime.BEAR], places=6
        )

    def test_the_breakout_rule_waits_for_the_range_to_break(self):
        oscillation = [100.0 + (4.0 if i % 2 else -4.0) for i in range(30)]
        bars = _bars(oscillation)
        signals = _drive(
            _router([MarketRegime.SIDEWAYS] * 30, sideways_rule="breakout"), bars
        )
        self.assertEqual(
            set(signals[:20]),
            {0.0},
            "an oscillation inside its own range is not a breakout",
        )

    def test_the_breakout_rule_follows_a_confirmed_breakout(self):
        closes = [100.0 + (2.0 if i % 2 else -2.0) for i in range(20)] + [
            110.0 + 4.0 * i for i in range(20)
        ]
        bars = _bars(closes)
        signals = _drive(
            _router([MarketRegime.SIDEWAYS] * 40, sideways_rule="breakout"), bars
        )
        self.assertAlmostEqual(
            max(signals), DEFAULT_WEIGHTS[MarketRegime.SIDEWAYS], places=6
        )


class DeviationBranchTest(unittest.TestCase):
    """Kotegawa's deviation rate, pinned as behaviour.

    Buy 25%+ below the trailing average, exit as price reverts toward it. The
    thesis is the gap closing, so the gap closing is the exit -- there is no
    separate target.
    """

    DEVIATION = {
        "sideways_rule": "deviation",
        "sideways_deviation_period": 20,
        "sideways_entry_deviation": -0.25,
        "sideways_exit_deviation": -0.05,
    }

    def test_a_shallow_dip_is_not_a_capitulation(self):
        """The whole point is that this is not the RSI-30 dip already rejected.

        A 10% sag below the average must leave the branch flat; if it fired
        here it would be the same pullback trade wearing a different name, and
        the measurement that justified it would not apply.
        """
        closes = [100.0] * 25 + [92.0] * 10
        signals = _drive(
            _router([MarketRegime.SIDEWAYS] * 35, **self.DEVIATION), _bars(closes)
        )
        self.assertEqual(set(signals), {0.0})

    def test_a_capitulation_is_bought_and_released_on_reversion(self):
        closes = [100.0] * 25 + [60.0] * 6 + [104.0] * 10
        signals = _drive(
            _router([MarketRegime.SIDEWAYS] * 41, **self.DEVIATION), _bars(closes)
        )
        self.assertAlmostEqual(
            max(signals), DEFAULT_WEIGHTS[MarketRegime.SIDEWAYS], places=6
        )
        self.assertEqual(
            signals[-1], 0.0, "the position must close once the gap has closed"
        )

    def test_an_unknown_rule_name_is_refused_rather_than_ignored(self):
        """A typo must not silently fall back to a default branch and publish
        a result attributed to a rule that never ran."""
        with self.assertRaises(ValueError) as raised:
            _router([MarketRegime.BULL] * 5, bull_rule="kotegowa")
        self.assertIn("kotegowa", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
