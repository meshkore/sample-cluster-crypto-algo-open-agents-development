"""The momentum brain: three entries, and an exit that must not cap the winner.

The load-bearing test here is `test_a_winner_is_never_closed_for_being_big`.
H-INTRA-002 exists because the previous hypothesis capped its upside, so a take
profit sneaking back in -- through a parameter, a default, or a helper reused
from the other brain -- would silently turn this into the idea that already
failed, and every other test in this file would still pass.

Each "it did not trade" assertion is paired with an open-gate control.
Sabotage-verified; each test names the mutation it was checked against.
"""

from datetime import datetime, timedelta, timezone
import unittest

from quantlab_intraday.momentum import DEFAULTS, IntradayMomentumBrain
from quantlab_trading.brains import build

UTC = timezone.utc
DAY = datetime(2024, 3, 5, tzinfo=UTC)

ROW = {
    "atr_14": 1.0,
    "natr_14": 1.0,
    "dollar_volume_20": 5_000_000.0,
    "high_200": 99.0,
    "range_vs_atr": 3.0,
    "internal_bar_strength": 0.95,
    "volume_ratio_20": 5.0,
    "ema_200": 90.0,
    "bb_upper": 99.0,
}


def _tick(
    hour=12,
    minute=0,
    close=101.0,
    equity=100_000.0,
    cash=None,
    positions=None,
    row=None,
    symbol="BTCUSDT",
    day=DAY,
):
    stamp = day + timedelta(hours=hour, minutes=minute)
    return {
        "timestamp": stamp.isoformat(),
        "sequence": hour * 12 + minute // 5,
        "candles": {
            symbol: {
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 5_000.0,
            }
        },
        "indicators": {symbol: dict(row or ROW)},
        "account": {
            "initial_capital": 100_000.0,
            "equity": equity,
            "cash": equity if cash is None else cash,
            "positions": positions or {},
        },
        "clock": {"processed": 1, "total": 10_000},
    }


def _position(move=0.0):
    return {
        "quantity": 10.0,
        "entry_price": 100.0,
        "entry_time": DAY.isoformat(),
        "invested": 1_000.0,
        "unrealised_pct": move,
    }


class EntryTest(unittest.TestCase):
    def test_intraday_momentum_buys_a_day_that_is_already_up(self):
        """THE open-gate control for the itsm rule."""
        brain = IntradayMomentumBrain(entry_rule="itsm", itsm_threshold=0.005)
        brain.decide(_tick(hour=0, close=100.0))  # sets the day's open
        decision = brain.decide(_tick(hour=12, close=101.0))  # +1% on the day
        self.assertEqual(len(decision.orders), 1, decision.note)
        self.assertEqual(decision.orders[0]["reason"], "MOMENTUM")

    def test_intraday_momentum_ignores_a_day_that_has_not_moved_enough(self):
        brain = IntradayMomentumBrain(entry_rule="itsm", itsm_threshold=0.005)
        brain.decide(_tick(hour=0, close=100.0))
        self.assertEqual(brain.decide(_tick(hour=12, close=100.2)).orders, [])

    def test_intraday_momentum_only_fires_at_its_hour(self):
        """Sabotage: dropping the hour check turns one trade a day into 288."""
        brain = IntradayMomentumBrain(entry_rule="itsm", itsm_hour=12)
        brain.decide(_tick(hour=0, close=100.0))
        self.assertEqual(brain.decide(_tick(hour=11, close=101.0)).orders, [])
        self.assertEqual(len(brain.decide(_tick(hour=12, close=101.0)).orders), 1)

    def test_breakout_needs_a_close_above_the_trailing_high(self):
        brain = IntradayMomentumBrain(entry_rule="donchian")
        self.assertEqual(len(brain.decide(_tick(close=101.0)).orders), 1)
        low = dict(ROW, high_200=200.0)
        self.assertEqual(brain.decide(_tick(close=101.0, row=low)).orders, [])

    def test_volatility_expansion_needs_all_three_conditions(self):
        brain = IntradayMomentumBrain(entry_rule="volexp")
        self.assertEqual(len(brain.decide(_tick()).orders), 1)
        for key, value in (
            ("range_vs_atr", 1.0),
            ("internal_bar_strength", 0.3),
            ("volume_ratio_20", 1.0),
        ):
            brain = IntradayMomentumBrain(entry_rule="volexp")
            self.assertEqual(
                brain.decide(_tick(row=dict(ROW, **{key: value}))).orders,
                [],
                f"{key} did not veto the entry",
            )

    def test_nothing_opens_on_the_last_hour_when_the_day_closes_positions(self):
        """A position opened at 23:00 is sold at 23:55 and pays a full round
        trip for eleven bars of exposure."""
        brain = IntradayMomentumBrain(entry_rule="donchian", exit_end_of_day=True)
        self.assertEqual(brain.decide(_tick(hour=23, close=101.0)).orders, [])
        # OPEN-GATE CONTROL: the same bar an hour earlier trades.
        brain = IntradayMomentumBrain(entry_rule="donchian", exit_end_of_day=True)
        self.assertEqual(len(brain.decide(_tick(hour=22, close=101.0)).orders), 1)

    def test_the_brain_is_reachable_through_the_registry(self):
        brain = build("intraday-momentum", entry_rule="donchian")
        self.assertEqual(len(brain.decide(_tick(close=101.0)).orders), 1)

    def test_an_unknown_entry_rule_is_refused(self):
        with self.assertRaises(ValueError):
            IntradayMomentumBrain(entry_rule="astrology")


class ExitTest(unittest.TestCase):
    def _opened(self, **params):
        brain = IntradayMomentumBrain(entry_rule="donchian", **params)
        brain.decide(_tick(hour=1, close=101.0))
        return brain

    def test_a_winner_is_never_closed_for_being_big(self):
        """The whole hypothesis. Sabotage: add any take profit and this fails.

        A trade up 12% with the trailing stop switched off must still be open:
        the only things allowed to end it are the stop, the trail, the clock
        and the end of the day.
        """
        brain = self._opened(trail_atr=0, exit_end_of_day=False)
        for hour in range(2, 12):
            decision = brain.decide(
                _tick(hour=hour, positions={"BTCUSDT": _position(move=0.12)})
            )
            self.assertEqual(decision.orders, [], f"closed a winner at hour {hour}")

    def test_the_trailing_stop_follows_the_move_and_then_takes_it(self):
        # ATR 1.0 on a close of 101 is 0.99%; a 3 ATR trail is ~2.97%.
        brain = self._opened(trail_atr=3.0, exit_end_of_day=False)
        brain.decide(_tick(hour=2, positions={"BTCUSDT": _position(move=0.10)}))
        held = brain.decide(_tick(hour=3, positions={"BTCUSDT": _position(move=0.08)}))
        self.assertEqual(held.orders, [], "closed inside the trail")
        taken = brain.decide(_tick(hour=4, positions={"BTCUSDT": _position(move=0.06)}))
        self.assertEqual(
            [(o["side"], o["reason"]) for o in taken.orders], [("SELL", "TRAIL")]
        )

    def test_the_stop_is_scaled_by_the_entry_bar(self):
        brain = self._opened(stop_atr=1.5, exit_end_of_day=False)
        plan = brain.pending["BTCUSDT"]
        self.assertAlmostEqual(plan["stop_pct"], 1.5 / 101.0, places=6)
        decision = brain.decide(
            _tick(hour=2, positions={"BTCUSDT": _position(move=-0.03)})
        )
        self.assertEqual(
            [(o["side"], o["reason"]) for o in decision.orders], [("SELL", "STOP_LOSS")]
        )

    def test_everything_closes_at_the_end_of_the_day(self):
        brain = self._opened(exit_end_of_day=True)
        held = brain.decide(
            _tick(hour=23, minute=50, positions={"BTCUSDT": _position(move=0.02)})
        )
        self.assertEqual(held.orders, [])
        closed = brain.decide(
            _tick(hour=23, minute=55, positions={"BTCUSDT": _position(move=0.02)})
        )
        self.assertEqual(
            [(o["side"], o["reason"]) for o in closed.orders], [("SELL", "END_OF_DAY")]
        )

    def test_the_time_stop_closes_a_trade_that_went_nowhere(self):
        brain = self._opened(maximum_holding_bars=3, exit_end_of_day=False)
        decision = None
        for index in range(3):
            decision = brain.decide(
                _tick(hour=2 + index, positions={"BTCUSDT": _position(move=0.001)})
            )
        self.assertEqual(
            [(o["side"], o["reason"]) for o in decision.orders], [("SELL", "TIME_STOP")]
        )


class MandateAndHygieneTest(unittest.TestCase):
    def test_the_run_stops_at_the_drawdown_limit(self):
        brain = IntradayMomentumBrain(entry_rule="donchian")
        brain.decide(_tick(equity=200_000.0, close=101.0))
        breached = brain.decide(_tick(hour=13, equity=149_000.0, close=101.0))
        self.assertIsNotNone(breached.stop)

    def test_a_run_inside_the_limit_keeps_trading(self):
        brain = IntradayMomentumBrain(entry_rule="donchian")
        brain.decide(_tick(equity=200_000.0, close=101.0))
        alive = brain.decide(_tick(hour=13, equity=160_000.0, close=101.0))
        self.assertIsNone(alive.stop)

    def test_the_ramp_and_the_mandate_can_be_made_to_agree(self):
        """The published run's two definitions, and the coherent alternative.

        Peak mandate with an initial-basis ramp is what shipped: at 149,000
        against a 200,000 peak the mandate is breached while the ramp's drawdown
        is still ZERO, because equity is above the opening capital. That gap is
        why sizing never throttled through the 2021-2022 decline.

        Sabotage-verified: making `mandate_basis="policy"` read the peak anyway
        fails the second half; hard-coding the peak for the ramp fails the first.
        """
        published = IntradayMomentumBrain(
            entry_rule="donchian", drawdown_basis="initial"
        )
        published.decide(_tick(equity=200_000.0, close=101.0))
        self.assertIsNotNone(
            published.decide(_tick(hour=13, equity=149_000.0, close=101.0)).stop
        )
        self.assertEqual(
            published.policy.drawdown_against(149_000.0, 200_000.0, 100_000.0), 0.0
        )

        coherent = IntradayMomentumBrain(
            entry_rule="donchian", drawdown_basis="initial", mandate_basis="policy"
        )
        coherent.decide(_tick(equity=200_000.0, close=101.0))
        # Same equity, same peak, and the mandate is not breached: 149,000 is
        # +49% on the deposit, which is what "initial" means.
        self.assertIsNone(
            coherent.decide(_tick(hour=13, equity=149_000.0, close=101.0)).stop
        )
        # And it still stops, on its own basis, below 75,000.
        self.assertIsNotNone(
            coherent.decide(_tick(hour=14, equity=70_000.0, close=101.0)).stop
        )

    def test_a_stronger_signal_takes_a_bigger_position(self):
        """The dose-response, expressed as size. Sabotage-verified: returning a
        flat 1.0 from `_signal_scale`, or scaling the notional after the cap
        instead of the budget before it, both fail here."""
        weak = IntradayMomentumBrain(
            entry_rule="itsm", itsm_threshold=0.01, signal_scale_cap=3.0
        )
        weak.decide(_tick(hour=0, close=100.0))
        small = weak.decide(_tick(hour=12, close=101.0)).orders  # +1%, at threshold

        strong = IntradayMomentumBrain(
            entry_rule="itsm", itsm_threshold=0.01, signal_scale_cap=3.0
        )
        strong.decide(_tick(hour=0, close=100.0))
        big = strong.decide(_tick(hour=12, close=103.0)).orders  # +3%, three times

        self.assertEqual(len(small), 1, "the weak signal did not trade")
        self.assertEqual(len(big), 1, "the strong signal did not trade")
        self.assertGreater(big[0]["notional"], small[0]["notional"] * 2)

    def test_the_position_cap_still_bounds_a_scaled_position(self):
        """Or `maximum_position_fraction` stops being the number a reader can
        use to derive how much of the book is ever at risk."""
        brain = IntradayMomentumBrain(
            entry_rule="itsm",
            itsm_threshold=0.01,
            signal_scale_cap=50.0,
            maximum_position_fraction=0.20,
        )
        brain.decide(_tick(hour=0, close=100.0))
        orders = brain.decide(_tick(hour=12, close=140.0)).orders
        self.assertEqual(len(orders), 1)
        self.assertLessEqual(orders[0]["notional"], 100_000.0 * 0.20 + 1e-6)

    def test_scaling_is_off_by_default_and_off_for_rules_with_no_dose(self):
        """A Donchian break is over the high or it is not; there is nothing to
        scale, and computing a scale from an unrelated number would be worse
        than not scaling at all."""
        flat = IntradayMomentumBrain(entry_rule="itsm", itsm_threshold=0.01)
        flat.decide(_tick(hour=0, close=100.0))
        self.assertEqual(flat._signal_scale("BTCUSDT", 105.0), 1.0)

        breakout = IntradayMomentumBrain(entry_rule="donchian", signal_scale_cap=3.0)
        breakout.decide(_tick(hour=0, close=100.0))
        self.assertEqual(breakout._signal_scale("BTCUSDT", 105.0), 1.0)

    def test_an_unknown_mandate_basis_is_refused(self):
        with self.assertRaises(ValueError):
            IntradayMomentumBrain(entry_rule="donchian", mandate_basis="pekk")

    def test_reset_actually_resets(self):
        brain = IntradayMomentumBrain(entry_rule="donchian")
        brain.decide(_tick(close=101.0))
        brain.decide(_tick(hour=13, positions={"BTCUSDT": _position()}))
        brain.reset()
        for attribute in ("plans", "pending", "held_bars", "day_open", "day_of"):
            self.assertEqual(getattr(brain, attribute), {}, attribute)
        self.assertEqual(brain.bars_seen, 0)
        self.assertEqual(brain.volatility.history, {})

    def test_every_knob_reaches_the_fingerprint(self):
        self.assertEqual(set(IntradayMomentumBrain().parameters()), set(DEFAULTS))

    def test_no_take_profit_knob_exists_at_all(self):
        """Belt and braces for the hypothesis: it cannot be re-introduced by
        passing a parameter, because there is no parameter to pass."""
        self.assertNotIn("take_profit_atr", DEFAULTS)
        self.assertNotIn("target_atr", DEFAULTS)
        with self.assertRaises(ValueError):
            IntradayMomentumBrain(target_atr=1.0)


if __name__ == "__main__":
    unittest.main()
