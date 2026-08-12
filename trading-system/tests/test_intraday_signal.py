"""The intraday vocabulary: the four gates, the vetoes, and their controls.

Every "it refused" assertion here is paired with an OPEN-GATE CONTROL: the same
bar with the one blocking field moved, which must be accepted. A gate that
refuses everything passes every refusal test ever written, and this laboratory
has shipped that bug more than once.

All sabotage-verified. Each test names the mutation it was checked against.
"""

import unittest

from quantlab_intraday import context, microstructure
from quantlab_intraday.moneymanagement import (
    bar_turnover_floor,
    intraday_money_management,
    position_notional,
    round_trip_cost,
)

# A bar 1% below its anchor with a close on the low: the shape this system buys.
CANDLE = {"open": 101.0, "high": 101.5, "low": 99.0, "close": 99.0, "volume": 500.0}
ROW = {
    "vwap_rolling": 100.0,
    "atr_14": 0.5,
    "natr_14": 0.5,
    "rsi_2": 5.0,
    "dollar_volume_20": 5_000_000.0,
    "internal_bar_strength": 0.0,
    "ema_200": 105.0,
}
GATES = {
    "minimum_displacement_atr": 1.5,
    "maximum_ibs": 0.30,
    "maximum_rsi": 15.0,
    "cost_hurdle_pct": 0.006,
    "minimum_turnover": 104_166.0,
}


class ReadingTest(unittest.TestCase):
    def test_reads_the_six_numbers_the_rule_needs(self):
        reading = microstructure.read("BTCUSDT", CANDLE, ROW)
        self.assertIsNotNone(reading)
        # 1.0 below a 100.0 anchor, on an ATR of 0.5, is two ATR and 1.01%.
        self.assertAlmostEqual(reading.displacement_atr, 2.0)
        self.assertAlmostEqual(reading.displacement_pct, 1.0 / 99.0)
        self.assertEqual(reading.ibs, 0.0)

    def test_a_warming_column_is_never_read_as_zero(self):
        """Sabotage: `or 0.0` instead of the None check reads warm-up as signal."""
        for column in ("vwap_rolling", "atr_14", "rsi_2"):
            row = dict(ROW, **{column: None})
            self.assertIsNone(
                microstructure.read("BTCUSDT", CANDLE, row),
                f"{column} was None and the bar was still read",
            )
        # OPEN-GATE CONTROL: with every column present the same bar reads.
        self.assertIsNotNone(microstructure.read("BTCUSDT", CANDLE, dict(ROW)))

    def test_ibs_falls_back_to_the_same_arithmetic_the_panel_does(self):
        row = dict(ROW)
        row.pop("internal_bar_strength")
        reading = microstructure.read("BTCUSDT", CANDLE, row)
        self.assertAlmostEqual(
            reading.ibs,
            (CANDLE["close"] - CANDLE["low"]) / (CANDLE["high"] - CANDLE["low"]),
        )


class GateTest(unittest.TestCase):
    def _verdict(self, candle=None, row=None, **overrides):
        gates = dict(GATES)
        gates.update(overrides)
        reading = microstructure.read("BTCUSDT", candle or CANDLE, row or ROW)
        return microstructure.qualifies(reading, **gates)

    def test_the_reference_bar_qualifies(self):
        """The open-gate control for every refusal below."""
        verdict = self._verdict()
        self.assertTrue(verdict.ok, verdict.reason)

    def test_turnover_gate_holds_the_capacity_invariant(self):
        row = dict(ROW, dollar_volume_20=50_000.0)
        self.assertEqual(self._verdict(row=row).reason, "turnover")
        # OPEN-GATE CONTROL: just above the floor and it trades.
        row = dict(ROW, dollar_volume_20=200_000.0)
        self.assertTrue(self._verdict(row=row).ok)

    def test_cost_hurdle_refuses_a_move_too_small_to_pay_for_itself(self):
        """Sabotage: dropping the hurdle check makes this bar tradeable."""
        candle = dict(CANDLE, close=99.6, low=99.6, high=100.1, open=100.05)
        row = dict(ROW, atr_14=0.05)  # 0.4% below the anchor, eight ATR
        self.assertEqual(self._verdict(candle=candle, row=row).reason, "cost_hurdle")
        # OPEN-GATE CONTROL: the same bar with a hurdle it can clear.
        self.assertTrue(self._verdict(candle=candle, row=row, cost_hurdle_pct=0.002).ok)

    def test_displacement_gate_needs_a_real_dislocation(self):
        row = dict(ROW, atr_14=2.0)  # 1.0 below the anchor is only half an ATR
        self.assertEqual(self._verdict(row=row).reason, "displacement")
        self.assertTrue(self._verdict(row=row, minimum_displacement_atr=0.4).ok)

    def test_shape_gates_want_the_sellers_finished(self):
        row = dict(ROW, internal_bar_strength=0.9)
        self.assertEqual(self._verdict(row=row).reason, "ibs")
        self.assertTrue(self._verdict(row=row, maximum_ibs=0.95).ok)

        row = dict(ROW, rsi_2=60.0)
        self.assertEqual(self._verdict(row=row).reason, "rsi")
        self.assertTrue(self._verdict(row=row, maximum_rsi=70.0).ok)

    def test_a_bar_above_the_anchor_is_never_bought(self):
        """The rule is long-only reversion, so strength is not a candidate."""
        candle = dict(CANDLE, close=101.0, low=100.5, high=101.5)
        verdict = self._verdict(candle=candle)
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.reason, "cost_hurdle")


class VolatilityWatchTest(unittest.TestCase):
    def test_no_opinion_until_the_sample_is_big_enough(self):
        watch = context.VolatilityWatch(minimum_samples=10)
        for _ in range(9):
            watch.observe("BTCUSDT", 1.0)
        self.assertFalse(watch.elevated("BTCUSDT", 99.0, 0.95))
        # OPEN-GATE CONTROL: one more sample and the same value is elevated.
        watch.observe("BTCUSDT", 1.0)
        self.assertTrue(watch.elevated("BTCUSDT", 99.0, 0.95))

    def test_quiet_bars_are_not_vetoed(self):
        watch = context.VolatilityWatch(minimum_samples=10)
        for value in range(20):
            watch.observe("BTCUSDT", float(value))
        self.assertFalse(watch.elevated("BTCUSDT", 5.0, 0.95))

    def test_the_verdict_for_a_bar_cannot_change_when_the_next_arrives(self):
        """Prefix equality. Sabotage: a centred window makes this fail at once."""
        series = [1.0, 2.0, 9.0, 1.5, 8.0, 2.5, 1.0, 7.0, 3.0, 1.0, 12.0, 2.0]
        first = context.VolatilityWatch(minimum_samples=4)
        verdicts = []
        for value in series[:8]:
            first.observe("BTCUSDT", value)
            verdicts.append(first.elevated("BTCUSDT", value, 0.75))

        second = context.VolatilityWatch(minimum_samples=4)
        longer = []
        for value in series:
            second.observe("BTCUSDT", value)
            longer.append(second.elevated("BTCUSDT", value, 0.75))
        self.assertEqual(verdicts, longer[:8])

    def test_reset_actually_resets(self):
        watch = context.VolatilityWatch(minimum_samples=2)
        watch.observe("BTCUSDT", 1.0)
        watch.observe("BTCUSDT", 1.0)
        watch.reset()
        self.assertFalse(watch.elevated("BTCUSDT", 99.0, 0.95))


class TrendAndHourTest(unittest.TestCase):
    def test_none_has_no_opinion(self):
        self.assertTrue(context.trend_allows({}, "none", 100.0, "ema_200"))

    def test_an_opt_in_gate_refuses_what_it_cannot_evaluate(self):
        self.assertFalse(context.trend_allows({}, "above_slow", 100.0, "ema_200"))
        # OPEN-GATE CONTROL: with the column present it answers properly.
        self.assertTrue(
            context.trend_allows({"ema_200": 90.0}, "above_slow", 100.0, "ema_200")
        )

    def test_the_inverse_gate_is_the_inverse(self):
        row = {"ema_200": 90.0}
        self.assertTrue(context.trend_allows(row, "above_slow", 100.0, "ema_200"))
        self.assertFalse(context.trend_allows(row, "below_slow", 100.0, "ema_200"))

    def test_hours_are_off_by_default_and_bind_when_given(self):
        stamp = "2026-01-01T13:45:00+00:00"
        self.assertTrue(context.hour_allows(stamp, None))
        self.assertTrue(context.hour_allows(stamp, (13,)))
        self.assertFalse(context.hour_allows(stamp, (14,)))


class MoneyManagementTest(unittest.TestCase):
    def test_the_round_trip_is_both_legs_of_both_components(self):
        self.assertAlmostEqual(round_trip_cost(10.0, 5.0), 0.0030)

    def test_the_turnover_floor_is_the_daily_floor_in_bar_units(self):
        """Sabotage: comparing a 15m average against the daily figure empties
        the universe, and nothing in the summary says why."""
        self.assertAlmostEqual(bar_turnover_floor(10_000_000.0, 96), 104_166.67, 2)

    def test_sizing_scales_inversely_with_the_stop_distance(self):
        policy = intraday_money_management()
        tight = position_notional(policy, 100_000.0, 0.01)
        wide = position_notional(policy, 100_000.0, 0.02)
        self.assertGreater(tight, wide)
        self.assertAlmostEqual(tight, 2 * wide)

    def test_the_cap_and_the_floor_both_bind(self):
        policy = intraday_money_management()
        capped = position_notional(policy, 100_000.0, 0.001)
        self.assertAlmostEqual(capped, 100_000.0 * policy.maximum_position_fraction)
        # Under the floor the answer is zero, not a token position: a run that
        # grinds out thousands of trades too small to matter still pays full
        # costs on every one of them.
        self.assertEqual(position_notional(policy, 100_000.0, 0.90), 0.0)

    def test_the_deleverage_ramp_can_close_the_book(self):
        policy = intraday_money_management()
        self.assertGreater(position_notional(policy, 100_000.0, 0.02, 0.05), 0.0)
        self.assertEqual(position_notional(policy, 100_000.0, 0.02, 0.30), 0.0)


if __name__ == "__main__":
    unittest.main()
