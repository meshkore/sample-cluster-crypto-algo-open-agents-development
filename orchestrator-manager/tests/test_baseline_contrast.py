from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from quantlab_manager.config import Settings
from quantlab_backtester.data import FAMILY_DATA_OVERRIDES, BinanceProvider
from quantlab_manager.historical import HistoricalUniverseEvaluator
from quantlab_manager.memory import ExperimentMemory
from quantlab_backtester.models import Bar, ExperimentSpec
from quantlab_trading.strategies import (
    BASELINE_FAMILY,
    BASELINE_PARAMS,
    initial_hypotheses,
)

UTC = timezone.utc


def _policy(**overrides) -> dict:
    policy = {
        "risk_per_trade": 0.02,
        "maximum_position_fraction": 0.5,
        "stop_loss_pct": 0.2,
        "take_profit_pct": 0.1,
        "minimum_confidence": 0.25,
        "long_only": True,
        "maximum_concurrent_assets": 5,
        "minimum_order_notional": 1.0,
        "minimum_position_fraction": 0.0,
        "maximum_drawdown": 0.25,
        "drawdown_safety_buffer": 0.0,
        "volatility_target": 0.5,
        "volatility_lookback": 20,
        "minimum_daily_quote_volume": 0.0,
        "volume_lookback": 20,
        "maximum_volume_participation": 1.0,
        "drawdown_deleverage_start": 0.25,
    }
    policy.update(overrides)
    return policy


def _hourly(count: int = 700) -> list[Bar]:
    from datetime import timedelta

    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars, price = [], 100.0
    for index in range(count):
        close = price * (1.006 if index % 4 else 0.994)
        bars.append(
            Bar(
                timestamp=start + timedelta(hours=index),
                open=price,
                high=max(price, close) * 1.001,
                low=min(price, close) * 0.999,
                close=close,
                volume=8_000.0,
                taker_buy_volume=4_200.0,
            )
        )
        price = close
    return bars


class BaselineContrastTest(unittest.TestCase):
    """Every Phase-1 run reports its difference against the control strategy
    under identical bars, costs and money management. Nine families were
    evaluated here with no control, producing absolute numbers that could not
    be compared with each other or with anything else.
    """

    def _settings(self, tmp: str) -> Settings:
        root = Path(tmp)
        raw = json.loads(Path("orchestrator-manager/config/default.json").read_text())
        raw.update(
            {
                "database_path": str(root / "lab.db"),
                "research_root": str(root / "research"),
                "data_root": str(root / "data"),
            }
        )
        raw["autonomous"]["backtest_pace_seconds"] = 0
        config = root / "config.json"
        config.write_text(json.dumps(raw))
        return Settings.load(config)

    def _seed(self, memory: ExperimentMemory, family: str, params: dict) -> int:
        hypothesis = next(h for h in initial_hypotheses("test") if h.family == family)
        memory.store_hypothesis(hypothesis.canonical())
        number = memory.register_strategy(family, {}, {}, _policy())
        memory.create_experiment(
            ExperimentSpec(
                f"contrast-{family}-{params.get('fast_period')}-{params.get('slow_period')}",
                hypothesis,
                "a" * 64,
                ["BTCUSDT"],
                params,
                "train",
                "val",
                "test",
                {},
            ),
            strategy_number=number,
        )
        return number

    def _run(self, settings, memory):
        bars = _hourly()
        with patch.object(BinanceProvider, "bars", return_value=bars):
            return HistoricalUniverseEvaluator(settings, memory).evaluate_latest()

    def test_the_report_carries_a_contrast_against_the_baseline(self):
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            self._seed(memory, BASELINE_FAMILY, dict(BASELINE_PARAMS))
            report = self._run(settings, memory)

            self.assertIsNotNone(report)
            contrast = report["contrast"]
            self.assertEqual(contrast["baseline_family"], BASELINE_FAMILY)
            self.assertIn("excess_over_baseline", contrast)
            self.assertIn("drawdown_vs_baseline", contrast)

    def test_the_baseline_family_is_flagged_as_being_its_own_control(self):
        # A candidate that IS the control ties with itself; the report says so
        # rather than publishing a meaningless zero as evidence of merit.
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            self._seed(memory, BASELINE_FAMILY, dict(BASELINE_PARAMS))
            report = self._run(settings, memory)

            self.assertTrue(report["contrast"]["is_the_baseline"])
            self.assertAlmostEqual(report["contrast"]["excess_over_baseline"], 0.0)

    def test_a_different_family_is_not_flagged_as_the_control(self):
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            self._seed(
                memory,
                BASELINE_FAMILY,
                {**BASELINE_PARAMS, "fast_period": 10, "slow_period": 50},
            )
            report = self._run(settings, memory)

            self.assertFalse(report["contrast"]["is_the_baseline"])
            self.assertAlmostEqual(
                report["contrast"]["excess_over_baseline"],
                report["return_pct"] - report["contrast"]["baseline_return"],
            )

    def test_the_control_is_computed_once_and_then_cached(self):
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            self._seed(
                memory,
                BASELINE_FAMILY,
                {**BASELINE_PARAMS, "fast_period": 10, "slow_period": 50},
            )
            first = self._run(settings, memory)

            cached = memory.baseline(
                memory.scope_key(
                    BASELINE_FAMILY,
                    BASELINE_PARAMS,
                    None,
                    ["BTCUSDT"],
                    700,
                    _policy(),
                    {
                        "commission_bps": settings.commission_bps,
                        "slippage_bps": settings.slippage_bps,
                        "funding_bps_per_bar": 0.0,
                    },
                )
            )
            # The exact key depends on the cost model's fields, so rather than
            # reconstruct it, assert that exactly one control row exists and
            # that a second candidate on the same condition reuses it.
            with memory.session() as db:
                rows = db.execute("SELECT COUNT(*) c FROM baseline_runs").fetchone()[
                    "c"
                ]
            self.assertEqual(rows, 1, "the control should be stored once")
            del cached, first

            self._seed(
                memory,
                BASELINE_FAMILY,
                {**BASELINE_PARAMS, "fast_period": 20, "slow_period": 80},
            )
            self._run(settings, memory)
            with memory.session() as db:
                rows = db.execute("SELECT COUNT(*) c FROM baseline_runs").fetchone()[
                    "c"
                ]
            self.assertEqual(
                rows,
                1,
                "a second candidate on the same condition must reuse the control",
            )

    def test_a_different_policy_gets_its_own_control(self):
        # The contrast only isolates the signal if everything else is identical,
        # so a changed policy must invalidate the cached control rather than
        # silently compare against one fitted to different money management.
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            key_a = memory.scope_key(
                BASELINE_FAMILY,
                BASELINE_PARAMS,
                "1h",
                ["BTCUSDT"],
                700,
                _policy(),
                {"commission_bps": 5.0},
            )
            key_b = memory.scope_key(
                BASELINE_FAMILY,
                BASELINE_PARAMS,
                "1h",
                ["BTCUSDT"],
                700,
                _policy(stop_loss_pct=0.05),
                {"commission_bps": 5.0},
            )
            self.assertNotEqual(key_a, key_b)

    def test_more_history_invalidates_the_cached_control(self):
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            short = memory.scope_key(
                BASELINE_FAMILY,
                BASELINE_PARAMS,
                "1h",
                ["BTCUSDT"],
                700,
                _policy(),
                {"commission_bps": 5.0},
            )
            longer = memory.scope_key(
                BASELINE_FAMILY,
                BASELINE_PARAMS,
                "1h",
                ["BTCUSDT"],
                9000,
                _policy(),
                {"commission_bps": 5.0},
            )
            self.assertNotEqual(short, longer)

    def test_the_override_interval_is_part_of_the_control_identity(self):
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            hourly = memory.scope_key(
                BASELINE_FAMILY,
                BASELINE_PARAMS,
                "1h",
                FAMILY_DATA_OVERRIDES[BASELINE_FAMILY]["symbols"],
                700,
                _policy(),
                {"commission_bps": 5.0},
            )
            daily = memory.scope_key(
                BASELINE_FAMILY,
                BASELINE_PARAMS,
                "1d",
                FAMILY_DATA_OVERRIDES[BASELINE_FAMILY]["symbols"],
                700,
                _policy(),
                {"commission_bps": 5.0},
            )
            self.assertNotEqual(hourly, daily)


if __name__ == "__main__":
    unittest.main()
