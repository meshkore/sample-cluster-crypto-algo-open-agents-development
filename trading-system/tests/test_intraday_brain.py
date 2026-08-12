"""The intraday brain: the mandate, the exits, the portfolio, and the controls.

The load-bearing test in this file is `test_a_qualifying_bar_is_bought`. Every
other assertion here is of the form "it did not trade", and a brain that never
trades at all passes all of them -- which is not a hypothetical failure mode in
this repository, it is a bug that has shipped twice.

All sabotage-verified. Each test names the mutation it was checked against.
"""

from datetime import datetime, timedelta, timezone
import unittest

from quantlab_intraday.reversion import IntradayReversionBrain
from quantlab_trading.brains import build

UTC = timezone.utc
START = datetime(2025, 6, 1, tzinfo=UTC)

# A bar 2 ATR below its anchor, closing on its low, on a liquid symbol: the
# shape the system exists to buy.
QUALIFYING_ROW = {
    "vwap_rolling": 100.0,
    "atr_14": 0.5,
    "natr_14": 0.5,
    "rsi_2": 4.0,
    "dollar_volume_20": 5_000_000.0,
    "internal_bar_strength": 0.05,
    "ema_200": 110.0,
}
QUALIFYING_CANDLE = {
    "open": 100.2,
    "high": 100.3,
    "low": 99.0,
    "close": 99.0,
    "volume": 900.0,
}


def _tick(
    sequence=0,
    equity=100_000.0,
    cash=None,
    positions=None,
    candles=None,
    indicators=None,
):
    positions = positions or {}
    return {
        "timestamp": (START + timedelta(minutes=15 * sequence)).isoformat(),
        "sequence": sequence,
        "candles": candles
        if candles is not None
        else {"BTCUSDT": dict(QUALIFYING_CANDLE)},
        "indicators": (
            indicators if indicators is not None else {"BTCUSDT": dict(QUALIFYING_ROW)}
        ),
        "account": {
            "initial_capital": 100_000.0,
            "equity": equity,
            "cash": equity if cash is None else cash,
            "positions": positions,
        },
        "clock": {"processed": sequence + 1, "total": 1_000},
    }


def _position(entry=99.2, move=0.0, quantity=100.0):
    return {
        "quantity": quantity,
        "entry_price": entry,
        "entry_time": START.isoformat(),
        "invested": entry * quantity,
        "unrealised_pct": move,
    }


class EntryTest(unittest.TestCase):
    def test_a_qualifying_bar_is_bought(self):
        """THE open-gate control. Without this every test below is vacuous."""
        brain = IntradayReversionBrain()
        decision = brain.decide(_tick())
        self.assertEqual(len(decision.orders), 1, decision.note)
        order = decision.orders[0]
        self.assertEqual(order["side"], "BUY")
        self.assertEqual(order["reason"], "LIQUIDITY_EVENT")
        self.assertGreater(order["notional"], 0.0)

    def test_the_brain_is_reachable_through_the_registry(self):
        """Registering is the only wiring step, so it has to actually work."""
        brain = build("intraday-reversion", stop_atr=2.5)
        self.assertEqual(brain.params["stop_atr"], 2.5)
        self.assertEqual(len(brain.decide(_tick()).orders), 1)

    def test_an_ordinary_bar_is_not_bought(self):
        row = dict(QUALIFYING_ROW, internal_bar_strength=0.9, rsi_2=70.0)
        candle = dict(QUALIFYING_CANDLE, close=100.1, low=99.9, high=100.4)
        brain = IntradayReversionBrain()
        decision = brain.decide(
            _tick(candles={"BTCUSDT": candle}, indicators={"BTCUSDT": row})
        )
        self.assertEqual(decision.orders, [])

    def test_the_position_cap_binds(self):
        """Sabotage: dropping the cap opens a fourth position on the fourth symbol."""
        candles = {f"SYM{i}": dict(QUALIFYING_CANDLE) for i in range(6)}
        indicators = {f"SYM{i}": dict(QUALIFYING_ROW) for i in range(6)}
        brain = IntradayReversionBrain(maximum_positions=3)
        decision = brain.decide(_tick(candles=candles, indicators=indicators))
        self.assertEqual(len(decision.orders), 3)
        # OPEN-GATE CONTROL: raise the cap and more of the same bars are bought.
        wider = IntradayReversionBrain(maximum_positions=5, maximum_concurrent_assets=5)
        self.assertEqual(
            len(wider.decide(_tick(candles=candles, indicators=indicators)).orders), 5
        )

    def test_the_most_dislocated_candidate_is_preferred(self):
        candles = {
            "MILD": dict(QUALIFYING_CANDLE, close=99.4, low=99.4),
            "DEEP": dict(QUALIFYING_CANDLE, close=98.0, low=98.0),
        }
        indicators = {"MILD": dict(QUALIFYING_ROW), "DEEP": dict(QUALIFYING_ROW)}
        brain = IntradayReversionBrain(maximum_positions=1)
        decision = brain.decide(_tick(candles=candles, indicators=indicators))
        self.assertEqual([order["symbol"] for order in decision.orders], ["DEEP"])

    def test_a_held_symbol_is_not_bought_again(self):
        brain = IntradayReversionBrain()
        decision = brain.decide(_tick(positions={"BTCUSDT": _position()}))
        self.assertEqual([o["side"] for o in decision.orders], [])

    def test_cash_is_not_double_committed_in_one_tick(self):
        """Sabotage: not decrementing `cash` queues three buys the account
        cannot pay for, and the session silently truncates the last two."""
        candles = {f"SYM{i}": dict(QUALIFYING_CANDLE) for i in range(3)}
        indicators = {f"SYM{i}": dict(QUALIFYING_ROW) for i in range(3)}
        brain = IntradayReversionBrain()
        decision = brain.decide(
            _tick(
                equity=100_000.0, cash=26_000.0, candles=candles, indicators=indicators
            )
        )
        self.assertEqual(len(decision.orders), 1)
        self.assertLessEqual(sum(o["notional"] for o in decision.orders), 26_000.0)

    def test_trade_from_holds_fire_without_going_blind(self):
        opens = START + timedelta(days=1)
        brain = IntradayReversionBrain(trade_from=opens.isoformat())
        early = brain.decide(_tick(sequence=0))
        self.assertEqual(early.orders, [])
        self.assertIn("warming", early.note)
        # The bars before the boundary are still observed -- that is the whole
        # point of `trade_from` rather than a shorter window.
        self.assertEqual(brain.bars_seen, 1)
        # OPEN-GATE CONTROL: the same bar after the boundary trades.
        later = brain.decide(_tick(sequence=97))
        self.assertEqual(len(later.orders), 1, later.note)


class ExitTest(unittest.TestCase):
    def _hold(self, brain, ticks, move=0.0, positions=None):
        """Run `ticks` bars with a position open and return the last decision."""
        decision = None
        for index in range(ticks):
            decision = brain.decide(
                _tick(
                    sequence=index + 1,
                    positions=positions or {"BTCUSDT": _position(move=move)},
                )
            )
        return decision

    def test_the_time_stop_closes_a_trade_that_never_reverted(self):
        """Sabotage: counting days instead of bars never fires inside a session."""
        brain = IntradayReversionBrain(maximum_holding_bars=8, exit_on_anchor=False)
        brain.decide(_tick())  # queue the buy
        held = dict(QUALIFYING_ROW)
        candle = dict(QUALIFYING_CANDLE)
        decision = None
        for index in range(8):
            decision = brain.decide(
                _tick(
                    sequence=index + 1,
                    positions={"BTCUSDT": _position(move=-0.001)},
                    candles={"BTCUSDT": candle},
                    indicators={"BTCUSDT": held},
                )
            )
            if index < 7:
                self.assertEqual(decision.orders, [], f"sold early at bar {index}")
        self.assertEqual(
            [(o["side"], o["reason"]) for o in decision.orders], [("SELL", "TIME_STOP")]
        )

    def test_reaching_the_anchor_closes_the_trade(self):
        brain = IntradayReversionBrain()
        brain.decide(_tick())
        recovered = dict(QUALIFYING_CANDLE, close=100.5, low=99.5, high=100.6)
        decision = brain.decide(
            _tick(
                sequence=1,
                positions={"BTCUSDT": _position(move=0.013)},
                candles={"BTCUSDT": recovered},
            )
        )
        self.assertEqual(
            [(o["side"], o["reason"]) for o in decision.orders], [("SELL", "ANCHOR")]
        )

    def test_the_stop_and_the_target_are_scaled_by_the_entry_bar(self):
        brain = IntradayReversionBrain(
            exit_on_anchor=False, target_atr=1.0, stop_atr=2.0
        )
        brain.decide(_tick())
        # ATR 0.5 on a close of 99.0 is 0.505%; the target is one of those.
        plan = brain.pending["BTCUSDT"]
        self.assertAlmostEqual(plan["target_pct"], 0.5 / 99.0, places=6)
        self.assertAlmostEqual(plan["stop_pct"], 1.0 / 99.0, places=6)

        decision = brain.decide(
            _tick(sequence=1, positions={"BTCUSDT": _position(move=0.006)})
        )
        self.assertEqual(
            [(o["side"], o["reason"]) for o in decision.orders],
            [("SELL", "TAKE_PROFIT")],
        )

    def test_a_position_whose_symbol_stops_printing_is_still_aged_out(self):
        """Sabotage: ageing only symbols present in `candles` holds a delisted
        position for ever, because its time stop never advances."""
        brain = IntradayReversionBrain(maximum_holding_bars=3, exit_on_anchor=False)
        brain.decide(_tick())
        decision = None
        for index in range(3):
            decision = brain.decide(
                _tick(
                    sequence=index + 1,
                    positions={"BTCUSDT": _position()},
                    candles={},
                    indicators={},
                )
            )
        self.assertEqual(
            [(o["side"], o["reason"]) for o in decision.orders], [("SELL", "TIME_STOP")]
        )


class MandateTest(unittest.TestCase):
    def test_the_run_stops_at_the_drawdown_limit_measured_from_the_peak(self):
        brain = IntradayReversionBrain()
        brain.decide(_tick(equity=200_000.0))  # the peak this is measured against
        breached = brain.decide(_tick(sequence=1, equity=149_000.0))
        self.assertIsNotNone(breached.stop)
        self.assertIn("drawdown mandate", breached.stop)

    def test_a_run_still_inside_the_limit_keeps_trading(self):
        """OPEN-GATE CONTROL: without this, an always-stop bug passes above."""
        brain = IntradayReversionBrain()
        brain.decide(_tick(equity=200_000.0))
        alive = brain.decide(_tick(sequence=1, equity=160_000.0))
        self.assertIsNone(alive.stop)
        self.assertEqual(len(alive.orders), 1)


class HygieneTest(unittest.TestCase):
    def test_reset_actually_resets(self):
        """Instances are reused. Rule 2 of the contribution rules."""
        brain = IntradayReversionBrain()
        brain.decide(_tick())
        brain.decide(_tick(sequence=1, positions={"BTCUSDT": _position()}))
        self.assertTrue(brain.plans or brain.pending)
        brain.reset()
        self.assertEqual(brain.plans, {})
        self.assertEqual(brain.pending, {})
        self.assertEqual(brain.held_bars, {})
        self.assertEqual(brain.bars_seen, 0)
        self.assertEqual(brain.entries, 0)
        self.assertEqual(brain.volatility.history, {})

    def test_every_knob_reaches_the_fingerprint(self):
        """A knob missing from `parameters()` is a knob two runs can disagree
        about while sharing a `backtest_id`, and the second overwrites the
        first. That is a recorded incident, not a hypothetical."""
        from quantlab_intraday.reversion import DEFAULTS

        published = IntradayReversionBrain().parameters()
        self.assertEqual(set(published), set(DEFAULTS))

    def test_a_misspelled_parameter_is_refused(self):
        with self.assertRaises(ValueError):
            IntradayReversionBrain(stop_ATR=2.0)

    def test_policy_fields_are_accepted_and_reach_the_policy(self):
        brain = IntradayReversionBrain(risk_per_trade=0.004)
        self.assertAlmostEqual(brain.policy.risk_per_trade, 0.004)

    def test_diagnostics_say_which_gate_refused(self):
        row = dict(QUALIFYING_ROW, dollar_volume_20=1.0)
        brain = IntradayReversionBrain()
        brain.decide(_tick(indicators={"BTCUSDT": row}))
        self.assertEqual(brain.diagnostics()["refusals"], {"turnover": 1})


if __name__ == "__main__":
    unittest.main()
