from __future__ import annotations

import unittest

from quantlab_trading.brains import available, build
from quantlab_trading.codex_regime_system import (
    BearAbsoluteStrengthBranch,
    BearReclaimBranch,
    BreadthRegimeDetector,
    BullParticipationBranch,
    BullVolumeRsiBranch,
    SidewaysBreakoutBranch,
    SidewaysVolumeRsiBranch,
)
from quantlab_trading.regime import MarketRegime
from quantlab_trading.regime_system import SymbolState


def _market(up: int, down: int, rsi: float):
    candles, indicators, symbols = {}, {}, []
    for index in range(up + down):
        symbol = f"S{index}"
        symbols.append(symbol)
        rising = index < up
        candles[symbol] = {"close": 110.0 if rising else 90.0, "volume": 150.0}
        indicators[symbol] = {
            "sma_50": 105.0 if rising else 95.0,
            "sma_200": 100.0,
            "rsi_14": rsi,
        }
    return candles, indicators, symbols


def _row(**overrides):
    row = {
        "sma_20": 108.0,
        "sma_50": 105.0,
        "sma_200": 100.0,
        "rsi_14": 55.0,
        "volume_ratio_20": 1.5,
    }
    row.update(overrides)
    return row


class TestBreadthDetector(unittest.TestCase):
    def test_requires_closed_bar_confirmation_before_a_label_changes(self):
        detector = BreadthRegimeDetector(confirmation_bars=3)
        bull = _market(4, 0, 60.0)
        self.assertIs(detector.observe(*bull), MarketRegime.UNKNOWN)
        self.assertIs(detector.observe(*bull), MarketRegime.UNKNOWN)
        self.assertIs(detector.observe(*bull), MarketRegime.BULL)

        bear = _market(0, 4, 40.0)
        self.assertIs(detector.observe(*bear), MarketRegime.BULL)
        self.assertIs(detector.observe(*bear), MarketRegime.BULL)
        self.assertIs(detector.observe(*bear), MarketRegime.BEAR)

    def test_mixed_breadth_is_sideways(self):
        detector = BreadthRegimeDetector(confirmation_bars=1)
        self.assertIs(detector.observe(*_market(2, 2, 50.0)), MarketRegime.SIDEWAYS)


class TestSimpleBranches(unittest.TestCase):
    def test_bull_needs_trend_rsi_and_volume(self):
        branch = BullVolumeRsiBranch({})
        self.assertTrue(
            branch.evaluate({"close": 110, "volume": 150}, _row(), SymbolState())
        )
        self.assertFalse(
            branch.evaluate(
                {"close": 110, "volume": 90},
                _row(volume_ratio_20=0.9),
                SymbolState(),
            )
        )

    def test_sideways_buys_oversold_and_exits_at_the_mean(self):
        branch = SidewaysVolumeRsiBranch({})
        state = SymbolState()
        self.assertTrue(
            branch.evaluate(
                {"close": 95, "volume": 150},
                _row(sma_20=100, rsi_14=30),
                state,
            )
        )
        self.assertFalse(
            branch.evaluate(
                {"close": 101, "volume": 150},
                _row(sma_20=100, rsi_14=50),
                state,
            )
        )

    def test_bear_refuses_a_dip_and_accepts_absolute_strength(self):
        branch = BearAbsoluteStrengthBranch({})
        self.assertFalse(
            branch.evaluate(
                {"close": 85, "volume": 300},
                _row(sma_20=95, sma_50=100, sma_200=105, rsi_14=25),
                SymbolState(),
            )
        )
        self.assertTrue(
            branch.evaluate({"close": 115, "volume": 200}, _row(), SymbolState())
        )

    def test_v2_sideways_requires_a_confirmed_cross_not_a_dip(self):
        branch = SidewaysBreakoutBranch({})
        state = SymbolState(previous={"sma_20": 100.0}, previous_candle={"close": 99.0})
        self.assertTrue(
            branch.evaluate(
                {"close": 103, "volume": 200},
                _row(sma_20=102, sma_50=101, rsi_14=60),
                state,
            )
        )
        self.assertFalse(
            branch.evaluate(
                {"close": 95, "volume": 300},
                _row(sma_20=100, sma_50=101, rsi_14=25, volume_ratio_20=3),
                SymbolState(),
            )
        )

    def test_v2_bear_requires_a_cross_above_the_cycle_average(self):
        branch = BearReclaimBranch({})
        state = SymbolState(
            previous={"sma_200": 100.0}, previous_candle={"close": 99.0}
        )
        self.assertTrue(
            branch.evaluate(
                {"close": 103, "volume": 250},
                _row(sma_50=102, sma_200=100, rsi_14=60, volume_ratio_20=2.5),
                state,
            )
        )

    def test_v2_bull_demands_above_average_volume(self):
        branch = BullParticipationBranch({})
        self.assertFalse(
            branch.evaluate(
                {"close": 110, "volume": 100},
                _row(rsi_14=60, volume_ratio_20=1.4),
                SymbolState(),
            )
        )


class TestRegistration(unittest.TestCase):
    def test_the_brain_is_available_from_a_fresh_registry_import(self):
        names = {entry["name"] for entry in available()}
        self.assertIn("codex-volume-rsi-regime", names)
        brain = build("codex-volume-rsi-regime")
        self.assertEqual(brain.parameters()["hypothesis"], "H-CODEX-VRMA-001")
        self.assertEqual(brain.policy.maximum_drawdown, 0.30)
        self.assertEqual(brain.policy.drawdown_deleverage_end, 0.25)

    def test_v2_has_a_distinct_identity_and_bounded_positions(self):
        brain = build("codex-volume-rsi-regime-v2")
        self.assertEqual(brain.parameters()["hypothesis"], "H-CODEX-VRMA-002")
        self.assertEqual(brain.parameters()["implementation_version"], 2)
        self.assertEqual(brain.policy.maximum_concurrent_assets, 6)
        self.assertEqual(brain.policy.maximum_position_fraction, 0.05)


if __name__ == "__main__":
    unittest.main()
