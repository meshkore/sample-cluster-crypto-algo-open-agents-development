from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import unittest

from quantlab.backtest import CostModel
from quantlab.models import Bar
from quantlab.portfolio import LongOnlyPortfolioBacktester, MoneyManagement


def _policy(**overrides) -> MoneyManagement:
    base = {
        "risk_per_trade": 0.02,
        "maximum_position_fraction": 0.90,
        "stop_loss_pct": 0.05,
        "take_profit_pct": 5.0,
        "minimum_confidence": 0.25,
        "long_only": True,
        "maximum_concurrent_assets": 5,
        "minimum_order_notional": 1.0,
        "minimum_position_fraction": 0.0,
        "maximum_drawdown": 0.25,
        "drawdown_safety_buffer": 0.0,
        "volatility_target": 1.0,
        "volatility_lookback": 20,
        "minimum_daily_quote_volume": 0.0,
        "volume_lookback": 20,
        "maximum_volume_participation": 1.0,
        "drawdown_deleverage_start": 0.25,
    }
    base.update(overrides)
    return MoneyManagement(**base)


def _rising_bars(count: int = 120) -> list[Bar]:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = []
    price = 100.0
    for index in range(count):
        close = price * 1.004
        bars.append(
            Bar(
                timestamp=start + timedelta(hours=index),
                open=price,
                high=max(price, close) * 1.0005,
                low=min(price, close) * 0.9995,
                close=close,
                volume=10_000.0,
            )
        )
        price = close
    return bars


class _AlwaysLong:
    """A control signal: constant full confidence, so anything the portfolio
    does is attributable to money management and never to the signal."""

    def reset(self) -> None:
        pass

    def on_bar(self, bars: list[Bar]) -> float:
        return 1.0


class _NeverLong:
    def reset(self) -> None:
        pass

    def on_bar(self, bars: list[Bar]) -> float:
        return 0.0


class SizingDistanceTest(unittest.TestCase):
    """`stop_loss_pct` used to be both the exit trigger and the denominator of
    the sizing formula, so the two could not be varied independently and
    "wide stop, full size" was inexpressible. `risk_distance_pct` separates
    them while defaulting to the old behaviour.
    """

    def test_absent_risk_distance_falls_back_to_the_stop(self):
        policy = _policy(stop_loss_pct=0.05)
        self.assertIsNone(policy.risk_distance_pct)
        self.assertEqual(policy.sizing_distance, 0.05)

    def test_an_explicit_risk_distance_overrides_the_stop(self):
        policy = _policy(stop_loss_pct=0.20, risk_distance_pct=0.05)
        self.assertEqual(policy.sizing_distance, 0.05)

    def test_a_wide_stop_alone_shrinks_position_size(self):
        # This is the coupling that made the old parameter ambiguous, pinned
        # here so it is visible rather than surprising.
        bars = {"BTCUSDT": _rising_bars()}
        costs = CostModel(0.0, 0.0)
        narrow = LongOnlyPortfolioBacktester(costs, _policy(stop_loss_pct=0.05)).run(
            bars, _AlwaysLong, 100_000.0
        )
        wide = LongOnlyPortfolioBacktester(costs, _policy(stop_loss_pct=0.20)).run(
            bars, _AlwaysLong, 100_000.0
        )
        self.assertGreater(narrow.average_exposure, wide.average_exposure)

    def test_a_wide_stop_can_now_keep_full_size(self):
        # The point of the split: same wide exit distance as above, but sizing
        # pinned to the narrow distance, so exposure matches the tight-stop run
        # instead of collapsing with it.
        bars = {"BTCUSDT": _rising_bars()}
        costs = CostModel(0.0, 0.0)
        narrow = LongOnlyPortfolioBacktester(costs, _policy(stop_loss_pct=0.05)).run(
            bars, _AlwaysLong, 100_000.0
        )
        wide_full_size = LongOnlyPortfolioBacktester(
            costs, _policy(stop_loss_pct=0.20, risk_distance_pct=0.05)
        ).run(bars, _AlwaysLong, 100_000.0)
        self.assertAlmostEqual(
            narrow.average_exposure, wide_full_size.average_exposure, places=6
        )

    def test_an_out_of_range_risk_distance_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            LongOnlyPortfolioBacktester(
                CostModel(0.0, 0.0), _policy(risk_distance_pct=0.0)
            )
        with self.assertRaises(ValueError):
            LongOnlyPortfolioBacktester(
                CostModel(0.0, 0.0), _policy(risk_distance_pct=1.5)
            )


class ExposureReportingTest(unittest.TestCase):
    """Exposure is a first-class output of every run. Eight months of this
    lab's published returns were generated at 5-9% average exposure and read
    as if fully invested, because nothing recorded it.
    """

    def test_a_strategy_that_never_trades_reports_zero_exposure(self):
        result = LongOnlyPortfolioBacktester(CostModel(0.0, 0.0), _policy()).run(
            {"BTCUSDT": _rising_bars()}, _NeverLong, 100_000.0
        )
        self.assertEqual(result.average_exposure, 0.0)
        self.assertEqual(result.peak_exposure, 0.0)
        self.assertEqual(result.time_in_market, 0.0)

    def test_an_always_long_strategy_reports_positive_exposure(self):
        result = LongOnlyPortfolioBacktester(CostModel(0.0, 0.0), _policy()).run(
            {"BTCUSDT": _rising_bars()}, _AlwaysLong, 100_000.0
        )
        self.assertGreater(result.average_exposure, 0.0)
        self.assertGreater(result.time_in_market, 0.0)
        self.assertLessEqual(result.average_exposure, result.peak_exposure)
        self.assertLessEqual(result.peak_exposure, 1.0 + 1e-9)

    def test_a_larger_risk_budget_produces_measurably_more_exposure(self):
        bars = {"BTCUSDT": _rising_bars()}
        costs = CostModel(0.0, 0.0)
        small = LongOnlyPortfolioBacktester(costs, _policy(risk_per_trade=0.002)).run(
            bars, _AlwaysLong, 100_000.0
        )
        large = LongOnlyPortfolioBacktester(costs, _policy(risk_per_trade=0.02)).run(
            bars, _AlwaysLong, 100_000.0
        )
        self.assertGreater(large.average_exposure, small.average_exposure)

    def test_time_in_market_is_a_fraction(self):
        result = LongOnlyPortfolioBacktester(CostModel(0.0, 0.0), _policy()).run(
            {"BTCUSDT": _rising_bars()}, _AlwaysLong, 100_000.0
        )
        self.assertGreaterEqual(result.time_in_market, 0.0)
        self.assertLessEqual(result.time_in_market, 1.0)


class PolicyCalibrationTest(unittest.TestCase):
    """A policy is only meaningful relative to how many assets it is applied
    to. `maximum_position_fraction=0.2` is a fully-invested portfolio across
    five assets and a 20%-invested one on a single asset -- the same number
    silently dividing every published return by five.
    """

    def test_it_reports_how_many_assets_reach_full_investment(self):
        self.assertEqual(
            _policy(maximum_position_fraction=0.2).exposure_calibration[
                "assets_for_full_investment"
            ],
            5,
        )
        self.assertEqual(
            _policy(maximum_position_fraction=0.5).exposure_calibration[
                "assets_for_full_investment"
            ],
            2,
        )

    def test_the_calibration_reports_the_sizing_distance_actually_in_use(self):
        calibration = _policy(
            stop_loss_pct=0.20, risk_distance_pct=0.05
        ).exposure_calibration
        self.assertEqual(calibration["sizing_distance"], 0.05)


if __name__ == "__main__":
    unittest.main()


class PolicyReconstructionTest(unittest.TestCase):
    """Every MoneyManagement field must survive a round trip through storage.

    Both evaluators rebuild a stored policy by copying a list of keys out of
    `money_management_json`. Those lists used to be hand-maintained literals,
    one per module, and they drifted: `drawdown_deleverage_end` was added to the
    dataclass and to neither list, so both phases silently dropped it and it
    fell back to `maximum_drawdown` -- which had just been raised to 0.30. The
    de-leverage ramp widened without anyone asking, average exposure went from
    8.1% to 18.7%, and a configuration measured legal at 24.72% drawdown
    aborted at 31.35%. `forward.py`'s copy was also missing
    `minimum_position_fraction` outright.

    A field absent from that list is not a missing feature, it is a silently
    different policy producing a number nobody can reproduce.
    """

    def test_policy_keys_covers_every_field(self):
        from dataclasses import fields as dataclass_fields

        from quantlab.portfolio import policy_keys

        self.assertEqual(
            set(policy_keys()),
            {field.name for field in dataclass_fields(MoneyManagement)},
        )

    def test_a_stored_policy_round_trips_without_losing_a_field(self):
        from quantlab.portfolio import policy_keys

        original = MoneyManagement(
            risk_per_trade=0.02,
            stop_loss_pct=0.35,
            risk_distance_pct=0.10,
            maximum_position_fraction=0.10,
            maximum_drawdown=0.30,
            drawdown_deleverage_end=0.25,
            minimum_position_fraction=0.03,
        )
        stored = json.loads(json.dumps(asdict(original)))
        rebuilt = MoneyManagement(**{key: stored[key] for key in policy_keys()})
        self.assertEqual(rebuilt, original)
        # The specific value that went missing, and the behaviour it controls.
        self.assertEqual(rebuilt.deleverage_end, 0.25)
        self.assertNotEqual(rebuilt.deleverage_end, rebuilt.maximum_drawdown)


class DrawdownBasisTest(unittest.TestCase):
    """The mandate question: 25% of what?

    Measuring drawdown from the running PEAK makes the de-leverage ramp a
    one-way ratchet. Once equity sits near the ramp's far end the risk budget
    collapses, every candidate position falls under the minimum size, nothing
    opens -- and because equity cannot grow without trading, the peak never
    updates and the drawdown never shrinks. The strategy is permanently bricked
    while reporting itself legal. S00852 earned +1480% by 2021-05-19 and then
    held zero positions for four and a half years.

    Measuring against the STARTING capital is the operator's mandate: never lose
    more than 25% of what was deposited. It binds hard early, when there are no
    profits to risk, and stops throttling an account that has compounded.
    """

    def test_the_two_bases_disagree_once_an_account_has_compounded(self):
        policy = MoneyManagement(drawdown_basis="peak")
        initial_basis = MoneyManagement(drawdown_basis="initial")
        # Grew 100k -> 400k, now sitting at 250k: a 37.5% peak drawdown, but the
        # deposit is still up 150%. The operator's stated position is that this
        # is not a problem.
        self.assertAlmostEqual(
            policy.drawdown_against(250_000, 400_000, 100_000), 0.375
        )
        self.assertEqual(initial_basis.drawdown_against(250_000, 400_000, 100_000), 0.0)

    def test_the_initial_basis_still_binds_on_real_capital_loss(self):
        """Relaxing the peak rule must not remove the floor that matters."""
        policy = MoneyManagement(drawdown_basis="initial")
        self.assertAlmostEqual(policy.drawdown_against(70_000, 120_000, 100_000), 0.30)
        self.assertGreater(policy.drawdown_against(70_000, 120_000, 100_000), 0.25)

    def test_an_invalid_basis_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            MoneyManagement(drawdown_basis="highwater")

    def test_the_run_records_where_it_stopped_deploying_capital(self):
        """`last_active_timestamp` is what lets the chart stop drawing.

        Without it the engine emits a point every bar forever and the equity
        curve draws a flat line across years of inactivity, which reads as a
        deliberate cash position rather than a dead strategy.
        """
        bars = _rising_bars(120)
        result = LongOnlyPortfolioBacktester(
            CostModel(commission_bps=0.0, slippage_bps=0.0),
            _policy(drawdown_basis="initial"),
        ).run({"AAAUSDT": bars}, lambda: _AlwaysLong(), 100_000.0)
        self.assertIsNotNone(result.last_active_timestamp)
        self.assertGreaterEqual(result.capital_drawdown, 0.0)
        # An always-long run on a rising series is active on its final bar, so
        # there is nothing for the chart to truncate.
        self.assertEqual(
            result.last_active_timestamp, result.equity_curve[-1]["timestamp"]
        )
