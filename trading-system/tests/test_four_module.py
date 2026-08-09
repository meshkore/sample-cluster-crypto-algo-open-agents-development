"""The four-module brain: routing, the bear gate, the mandate, and sizing.

The branch tests each carry an OPEN-GATE CONTROL -- a case that must produce a
trade. A branch that silently never fires passes every "it did not trade"
assertion, and this laboratory has shipped exactly that bug: the first breakout
branch compared the close against a window containing its own bar, which can
only be true on a doji, and looked like a conservative rule for weeks.

All sabotage-verified; each test names the bug it was checked against.
"""

from datetime import datetime, timedelta, timezone
import unittest

from quantlab_trading.brains import build
from quantlab_trading.regime import MarketRegime
from quantlab_trading.regime_system import (
    BreakoutBranch,
    ClimaxBranch,
    DeviationBranch,
    FourModuleBrain,
    ParticipationBranch,
    SupertrendBranch,
    SymbolState,
    TrendBranch,
)

UTC = timezone.utc
START = datetime(2020, 1, 1, tzinfo=UTC)


def _candle(close, volume=1_000_000.0):
    return {
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": volume,
    }


def _account(equity=100_000.0, cash=None, positions=None):
    return {
        "initial_capital": 100_000.0,
        "equity": equity,
        "cash": equity if cash is None else cash,
        "invested": 0.0,
        "exposure": 0.0,
        "positions": positions or {},
    }


def _tick(day, candles, indicators, account=None):
    return {
        "timestamp": (START + timedelta(days=day)).isoformat(),
        "candles": candles,
        "indicators": indicators,
        "account": account or _account(),
        "clock": {"processed": day + 1, "total": 10_000},
    }


class TestBranches(unittest.TestCase):
    """Each branch is a comparison between served columns. Nothing more."""

    def test_breakout_reads_the_channel_from_the_previous_bar(self):
        """The bug that shipped: a channel containing its own bar never breaks.

        Sabotage: read `high_20` from `row` instead of `state.previous`. The
        open-gate control below then produces NO entry, because a bar's high is
        at or above its own close by definition.
        """
        branch = BreakoutBranch({})
        state = SymbolState()
        state.previous = {"high_20": 100.0, "low_20": 80.0}
        # OPEN-GATE CONTROL: a close above the previous channel top must trade.
        self.assertTrue(branch.evaluate(_candle(101.0), {"high_20": 101.0}, state))
        # And it exits at the midpoint, not at the opposing low.
        state.previous = {"high_20": 101.0, "low_20": 80.0}
        self.assertFalse(branch.evaluate(_candle(89.0), {}, state))

    def test_breakout_stands_aside_until_the_channel_has_filled(self):
        branch = BreakoutBranch({})
        state = SymbolState()
        self.assertFalse(branch.evaluate(_candle(500.0), {}, state))

    def test_trend_needs_the_trend_and_a_live_but_unexhausted_rsi(self):
        branch = TrendBranch({})
        state = SymbolState()
        rising = {"sma_50": 100.0, "sma_200": 90.0, "rsi_14": 60.0}
        # OPEN-GATE CONTROL.
        self.assertTrue(branch.evaluate(_candle(105.0), rising, state))
        # Exhausted momentum closes it.
        self.assertFalse(
            branch.evaluate(_candle(105.0), {**rising, "rsi_14": 95.0}, state)
        )
        # A dead trend never opens it.
        state = SymbolState()
        self.assertFalse(
            branch.evaluate(_candle(105.0), {**rising, "sma_50": 80.0}, state)
        )

    def test_participation_demands_both_averages_and_is_symmetric(self):
        branch = ParticipationBranch({})
        state = SymbolState()
        self.assertTrue(
            branch.evaluate(_candle(120.0), {"sma_200": 90.0, "sma_50": 100.0}, state)
        )
        # Losing either one ends it on the same bar. No asymmetry to earn here.
        self.assertFalse(
            branch.evaluate(_candle(95.0), {"sma_200": 90.0, "sma_50": 100.0}, state)
        )

    def test_deviation_buys_a_collapse_and_exits_on_reversion(self):
        branch = DeviationBranch({})
        state = SymbolState()
        self.assertFalse(branch.evaluate(_candle(90.0), {"sma_20": 100.0}, state))
        # OPEN-GATE CONTROL: 30% below the average is the Kotegawa band.
        self.assertTrue(branch.evaluate(_candle(70.0), {"sma_20": 100.0}, state))
        # Still held while the gap is open...
        self.assertTrue(branch.evaluate(_candle(90.0), {"sma_20": 100.0}, state))
        # ...and closed when the gap closes, not at a fixed profit target.
        self.assertFalse(branch.evaluate(_candle(96.0), {"sma_20": 100.0}, state))

    def test_climax_holds_for_a_fixed_number_of_bars(self):
        branch = ClimaxBranch({"holding": 2})
        state = SymbolState()
        quiet = {"volume_sma_20": 1_000.0, "return_1": 0.0}
        self.assertFalse(branch.evaluate(_candle(100.0, 1_000.0), quiet, state))
        shock = {"volume_sma_20": 1_000.0, "return_1": -0.08}
        self.assertTrue(branch.evaluate(_candle(92.0, 9_000.0), shock, state))
        self.assertTrue(branch.evaluate(_candle(93.0, 1_000.0), quiet, state))
        self.assertFalse(branch.evaluate(_candle(94.0, 1_000.0), quiet, state))

    def test_supertrend_enters_on_the_flip_not_on_the_state(self):
        """Sabotage: entering whenever direction > 0. The position is then
        re-opened on every bullish bar, including ones it deliberately exited."""
        branch = SupertrendBranch({})
        state = SymbolState()
        state.previous = {"supertrend_direction": -1.0}
        self.assertTrue(
            branch.evaluate(
                _candle(100.0), {"supertrend_direction": 1.0, "adx": 30.0}, state
            )
        )
        # A weak trend does not authorise the flip.
        state, state.previous = SymbolState(), {"supertrend_direction": -1.0}
        self.assertFalse(
            branch.evaluate(
                _candle(100.0), {"supertrend_direction": 1.0, "adx": 5.0}, state
            )
        )
        # Already bullish, no flip: nothing re-opens.
        state.previous = {"supertrend_direction": 1.0}
        self.assertFalse(
            branch.evaluate(
                _candle(100.0), {"supertrend_direction": 1.0, "adx": 30.0}, state
            )
        )


class _Tape:
    """Drives a brain through a synthetic market so the whole path is exercised."""

    def __init__(self, brain, reference=("BTCUSDT",), tradable=("ALTUSDT",)):
        self.brain = brain
        self.reference, self.tradable = reference, tradable
        self.day = 0
        # The price level carries ACROSS calls. Restarting it per call injected
        # a -60% single-bar gap between phases, which crashed the composite and
        # made a 20-bar 3%/day decline read as a 79% drawdown.
        self.level = 100.0
        self.decisions = []

    def run(self, bars, growth, breadth_above=True, asset_above=None, account=None):
        """`asset_above` is deliberately separable from `breadth_above`.

        A falling market containing an asset that is still above its own
        averages is precisely the case the bear branch exists for, and a tape
        that cannot express it can only ever test the branch not firing.
        """
        asset_above = breadth_above if asset_above is None else asset_above
        for _ in range(bars):
            self.level *= growth
            candles, indicators = {}, {}
            for symbol in (*self.reference, *self.tradable):
                above = breadth_above if symbol in self.reference else asset_above
                candles[symbol] = _candle(self.level)
                indicators[symbol] = {
                    "sma_200": self.level * (0.9 if above else 1.1),
                    "sma_50": self.level * (0.95 if above else 1.05),
                    "rsi_14": 60.0,
                    "sma_20": self.level * 0.99,
                    "high_20": self.level * 1.5,
                    "low_20": self.level * 0.5,
                    "volume_sma_20": 1_000_000.0,
                    "return_1": growth - 1,
                    "supertrend_direction": 1.0,
                    "adx": 30.0,
                }
            decision = self.brain.decide(_tick(self.day, candles, indicators, account))
            self.decisions.append(decision)
            self.day += 1
        return self.decisions[-1]


class TestFourModuleBrain(unittest.TestCase):
    def _brain(self, **params):
        base = dict(
            trend_period=5,
            slope_period=2,
            confirmation_bars=1,
            reference_symbols=["BTCUSDT"],
        )
        base.update(params)
        return FourModuleBrain(**base)

    def test_it_is_launchable_by_name(self):
        """Registration is the only wiring step, so it has to actually work."""
        brain = build("four-module")
        self.assertTrue(hasattr(brain, "decide"))

    def test_it_does_not_trade_an_unknown_market(self):
        brain = self._brain()
        tape = _Tape(brain)
        decision = tape.run(3, 1.05)
        self.assertIs(brain.detector.regime, MarketRegime.UNKNOWN)
        self.assertEqual(decision.orders, [])

    def test_a_confirmed_bull_routes_to_the_bull_branch_and_buys(self):
        """OPEN-GATE CONTROL for the whole brain. If this stops trading, every
        'it did not trade' assertion in this file becomes vacuous."""
        brain = self._brain()
        tape = _Tape(brain)
        tape.run(20, 1.05)
        self.assertIs(brain.detector.regime, MarketRegime.BULL)
        buys = [o for d in tape.decisions for o in d.orders if o["side"] == "BUY"]
        self.assertTrue(buys)
        self.assertEqual(buys[0]["symbol"], "ALTUSDT")
        self.assertIn("TREND", buys[0]["reason"])

    def test_the_reference_basket_is_observed_but_not_traded(self):
        """Sabotage: drop the `trade_reference` guard. BTCUSDT then appears in
        the orders and two runs on the same universe stop being comparable."""
        brain = self._brain()
        tape = _Tape(brain)
        tape.run(20, 1.05)
        traded = {o["symbol"] for d in tape.decisions for o in d.orders}
        self.assertNotIn("BTCUSDT", traded)
        self.assertIn("BTCUSDT", brain.detector.seen_symbols)

    def test_trade_from_holds_fire_while_the_detector_warms(self):
        brain = self._brain(trade_from=(START + timedelta(days=30)).isoformat())
        tape = _Tape(brain)
        tape.run(20, 1.05)
        self.assertIs(brain.detector.regime, MarketRegime.BULL)
        self.assertEqual([o for d in tape.decisions for o in d.orders], [])
        # OPEN-GATE CONTROL: past the boundary it trades the same tape.
        tape.day = 40
        decision = tape.run(2, 1.05)
        self.assertTrue(decision.orders)

    def test_a_shallow_young_bear_is_not_traded(self):
        """The worst measured cell in this laboratory: -32.30% over 30 days at a
        9% hit rate. The gate refuses it; `bear_min_depth=0` opens it."""

        def tape_for(brain):
            tape = _Tape(brain)
            tape.run(20, 1.05)  # establish a high
            # The market falls and its breadth collapses, but the tradable asset
            # is still above both its own averages -- the one case the bear
            # branch is built for.
            tape.run(20, 0.97, breadth_above=False, asset_above=True)
            return tape

        gated = self._brain(bear_rule="participation")
        tape = tape_for(gated)
        self.assertIs(gated.detector.regime, MarketRegime.BEAR)
        self.assertLess(gated.detector.depth, 0.70)
        self.assertLess(gated.detector.episode_age, 240)
        # No BEAR-branch entry anywhere. The BULL entries that survive the
        # confirmation lag at the start of the decline are the detector's
        # hysteresis working, not the gate leaking.
        self.assertEqual(
            [
                o
                for d in tape.decisions
                for o in d.orders
                if o["side"] == "BUY" and o["reason"].startswith("BEAR")
            ],
            [],
        )

        # OPEN-GATE CONTROL: same tape, gate disabled, and the branch fires.
        opened = self._brain(bear_rule="participation", bear_min_depth=0.0)
        control = tape_for(opened)
        self.assertIs(opened.detector.regime, MarketRegime.BEAR)
        buys = [
            o
            for d in control.decisions[20:]
            for o in d.orders
            if o["side"] == "BUY" and o["reason"].startswith("BEAR")
        ]
        self.assertTrue(buys, "the bear branch never fired; the gate test is vacuous")

    def test_a_regime_change_closes_the_position_rather_than_handing_it_over(self):
        brain = self._brain()
        tape = _Tape(brain)
        tape.run(20, 1.05)
        held = {
            "ALTUSDT": {
                "quantity": 1.0,
                "entry_price": 100.0,
                "entry_time": START.isoformat(),
                "invested": 5_000.0,
                "unrealised_pct": 0.01,
            }
        }
        tape.run(12, 0.97, breadth_above=False, account=_account(positions=held))
        sells = [
            o
            for d in tape.decisions
            for o in d.orders
            if o["side"] == "SELL" and o["reason"] == "REGIME_HANDOVER"
        ]
        self.assertTrue(sells)

    def test_the_mandate_stops_the_run(self):
        brain = self._brain()
        tape = _Tape(brain)
        tape.run(20, 1.05)
        decision = tape.run(1, 1.05, account=_account(equity=60_000.0))
        self.assertIsNotNone(decision.stop)
        self.assertIn("mandate", decision.stop)

    def test_the_mandate_is_measured_against_the_running_peak(self):
        """The operator's rule is literal: abort at 30% below the high.

        The first real run of this brain defaulted to the `ratchet` basis and
        finished +43.6% having gone 42.0% below its peak -- inside the ratchet
        floor and a plain breach of the mandate the laboratory publishes.
        Sabotage: `drawdown_basis="ratchet"`. A 200,000 peak then tolerates
        135,000 and the assertion below fails.
        """
        brain = self._brain()
        self.assertEqual(brain.policy.drawdown_basis, "peak")
        tape = _Tape(brain)
        tape.run(20, 1.05)
        tape.run(1, 1.05, account=_account(equity=200_000.0))  # a new peak
        surviving = tape.run(1, 1.05, account=_account(equity=145_000.0))
        self.assertIsNone(surviving.stop)  # 27.5% below the peak: still alive
        breached = tape.run(1, 1.05, account=_account(equity=139_000.0))
        self.assertIsNotNone(breached.stop)  # 30.5%: over the line

    def test_a_batch_never_commits_more_cash_than_the_account_holds(self):
        """Sabotage: drop the `committed + notional > cash` check. The session
        caps each fill at the remaining cash, so the alphabetically-first orders
        fill at full size and the rest at whatever is left -- position sizes
        decided by symbol name."""
        brain = self._brain()
        tape = _Tape(brain, tradable=tuple(f"A{i}USDT" for i in range(12)))
        tape.run(20, 1.05, account=_account(equity=100_000.0, cash=8_000.0))
        buys = [o for d in tape.decisions for o in d.orders if o["side"] == "BUY"]
        for decision in tape.decisions:
            committed = sum(
                o["notional"] for o in decision.orders if o["side"] == "BUY"
            )
            self.assertLessEqual(committed, 8_000.0 + 1e-9)
        self.assertTrue(buys, "no buys at all; the cap test is vacuous")

    def test_diagnostics_report_the_detector_and_the_policy(self):
        brain = self._brain()
        _Tape(brain).run(20, 1.05)
        report = brain.diagnostics()
        self.assertEqual(report["detector"]["current_regime"], "BULL")
        self.assertEqual(report["rules"]["BULL"], "trend")
        self.assertEqual(report["policy"]["maximum_drawdown"], 0.30)
        self.assertEqual(report["policy"]["drawdown_deleverage_end"], 0.25)

    def test_an_unknown_rule_name_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            self._brain(bull_rule="does-not-exist")

    def test_an_unknown_scope_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            self._brain(regime_scope="sideways")


class TestAssetScope(unittest.TestCase):
    def test_asset_scope_routes_on_the_asset_and_gates_on_the_market(self):
        """H-014. The market detector keeps exactly one job: refusing to trade
        at all in the shallow part of a market-wide bear."""
        brain = FourModuleBrain(
            trend_period=5,
            slope_period=2,
            confirmation_bars=1,
            asset_slope_period=2,
            asset_confirmation_bars=1,
            regime_scope="asset",
            reference_symbols=["BTCUSDT"],
            bear_min_depth=0.0,
        )
        tape = _Tape(brain)
        tape.run(25, 1.05)
        state = brain.states["ALTUSDT"]
        self.assertIsNotNone(state.asset_detector)
        self.assertIs(state.asset_detector.regime, MarketRegime.BULL)
        buys = [o for d in tape.decisions for o in d.orders if o["side"] == "BUY"]
        self.assertTrue(buys)


if __name__ == "__main__":
    unittest.main()
