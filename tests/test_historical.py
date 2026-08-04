"""Coverage for the gap `master` flagged in ed1700c: nothing called
`WalkForwardEvaluator` from the research loop, so `walkforward_scores` stayed
empty and every mutation kept falling back to the in-sample selector the
module was built to replace. `HistoricalUniverseEvaluator.evaluate_latest`
now runs the fold evaluation itself for a Phase-1 candidate that already
cleared criterion 10, reusing the bars and policy it already built rather
than reloading anything.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from quantlab import walkforward
from quantlab.config import Settings
from quantlab.data import BinanceProvider, DataManager, FAMILY_DATA_OVERRIDES
from quantlab.historical import HistoricalUniverseEvaluator
from quantlab.memory import ExperimentMemory
from quantlab.models import Bar, ExperimentSpec, utc_now
from quantlab.strategies import initial_hypotheses


UTC = timezone.utc

# 730-day train + 21-day embargo + 182-day test is one fold's span; three
# steps of the 182-day test length past that gives three folds, the minimum
# `evaluate_folds` treats as a measurement rather than noise.
FOLD_SPAN_DAYS = 730 + 21 + 182
HISTORY_DAYS = FOLD_SPAN_DAYS + 2 * 182 + 10


def _rising_bars(start: datetime, days: int) -> list[Bar]:
    """A monotonic, low-volatility climb.

    `_Momentum` (family `volatility_expansion`) goes long once price clears
    its lookback high under the volatility cap, and only exits below the
    trailing mean. On a series that only ever rises, both conditions hold at
    every bar after warm-up, so the position opens once and every fold sees a
    profitable, single-direction market — enough to prove the wiring calls
    through, without needing to model a real strategy's edge.
    """
    bars = []
    price = 100.0
    for day in range(days):
        price *= 1.0015
        bars.append(
            Bar(
                start + timedelta(days=day),
                price / 1.0015,
                price * 1.001,
                price / 1.0015 * 0.999,
                price,
                1_000_000.0,
            )
        )
    return bars


def _full_policy(**overrides) -> dict:
    policy = {
        "risk_per_trade": 0.02,
        "maximum_position_fraction": 0.5,
        "stop_loss_pct": 0.5,
        "take_profit_pct": 5.0,
        "minimum_confidence": 0.5,
        "long_only": True,
        "maximum_concurrent_assets": 5,
        "minimum_order_notional": 1.0,
        "minimum_position_fraction": 0.0,
        "maximum_drawdown": 0.25,
        "drawdown_safety_buffer": 0.0,
        "volatility_target": 0.05,
        "volatility_lookback": 20,
        "minimum_daily_quote_volume": 0.0,
        "volume_lookback": 20,
        "maximum_volume_participation": 1.0,
        "drawdown_deleverage_start": 0.10,
    }
    policy.update(overrides)
    return policy


class HistoricalWalkForwardWiringTest(unittest.TestCase):
    def _settings(self, tmp: str) -> Settings:
        root = Path(tmp)
        raw = json.loads(Path("config/default.json").read_text())
        raw.update(
            {
                "database_path": str(root / "lab.db"),
                "research_root": str(root / "research"),
                "data_root": str(root / "data"),
            }
        )
        # Production stretches Phase 1 over `backtest_pace_seconds` so the
        # public monitor can show it advancing; that pacing is real
        # `time.sleep`, so a test inheriting it verifies nothing extra and
        # only pays the wall-clock cost.
        raw["autonomous"]["backtest_pace_seconds"] = 0
        config = root / "config.json"
        config.write_text(json.dumps(raw))
        return Settings.load(config)

    def _seed_strategy(
        self, settings: Settings, memory: ExperimentMemory, money_management: dict
    ) -> int:
        hypothesis = initial_hypotheses("test")[0]
        self.assertEqual(hypothesis.family, "volatility_expansion")
        memory.store_hypothesis(hypothesis.canonical())
        strategy_number = memory.register_strategy(
            hypothesis.family, {}, {}, money_management
        )
        spec = ExperimentSpec(
            "wiring-test-1",
            hypothesis,
            "d" * 64,
            ["BTCUSDT"],
            {"lookback": 20, "exit_window": 10, "max_vol": 0.04},
            "train",
            "val",
            "test",
            {},
        )
        memory.create_experiment(spec, strategy_number=strategy_number)

        manager = DataManager(settings.data_root, settings.splits["future_lock_start"])
        bars = _rising_bars(datetime(2021, 1, 1, tzinfo=UTC), HISTORY_DAYS)
        path = manager.save_csv(
            bars, "synthetic", "BTCUSDT", "1d", manager.audit(bars, "1d")
        )
        with memory.transaction() as db:
            db.execute(
                "INSERT INTO asset_universe VALUES(?,?,?,?,?,?,?,?)",
                (
                    "BTCUSDT",
                    "TRADING",
                    utc_now(),
                    utc_now(),
                    str(path),
                    None,
                    None,
                    utc_now(),
                ),
            )
        return strategy_number

    def test_a_profitable_candidate_is_scored_and_recorded_on_folds(self):
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            strategy_number = self._seed_strategy(settings, memory, _full_policy())

            phases: list[str] = []
            report = HistoricalUniverseEvaluator(
                settings, memory, lambda phase, payload: phases.append(phase)
            ).evaluate_latest()

            self.assertEqual(report["status"], "COMPLETE")
            self.assertGreater(report["return_pct"], 0)
            self.assertIn("walkforward", report)
            self.assertGreaterEqual(report["walkforward"]["folds_evaluated"], 3)
            self.assertTrue(report["walkforward"]["eligible"])
            self.assertIn("PHASE1_WALKFORWARD", phases)

            stored = walkforward.stored_score(memory, strategy_number)
            self.assertIsNotNone(stored)
            self.assertTrue(stored.eligible)
            with memory.session() as db:
                folds = db.execute(
                    "SELECT COUNT(*) FROM walkforward_folds WHERE strategy_number=?",
                    (strategy_number,),
                ).fetchone()[0]
            self.assertEqual(folds, stored.folds_evaluated)

    def test_a_candidate_that_never_opens_a_position_is_never_folded(self):
        """`return_pct == 0.0` fails the strictly-positive gate.

        Folding costs a full re-simulation per fold, so a candidate that
        never traded — and therefore taught nothing either way — should not
        pay for or produce fold evidence.
        """
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            # A confidence floor above the strategy's maximum possible signal
            # (1.0) means no bar ever authorizes an entry.
            strategy_number = self._seed_strategy(
                settings, memory, _full_policy(minimum_confidence=1.5)
            )

            report = HistoricalUniverseEvaluator(settings, memory).evaluate_latest()

            self.assertEqual(report["status"], "COMPLETE")
            self.assertEqual(report["trades"], 0)
            self.assertNotIn("walkforward", report)
            self.assertIsNone(walkforward.stored_score(memory, strategy_number))

    def test_a_short_history_is_reported_as_zero_folds_not_an_error(self):
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            hypothesis = initial_hypotheses("test")[0]
            memory.store_hypothesis(hypothesis.canonical())
            strategy_number = memory.register_strategy(
                hypothesis.family, {}, {}, _full_policy()
            )
            memory.create_experiment(
                ExperimentSpec(
                    "wiring-test-short",
                    hypothesis,
                    "d" * 64,
                    ["BTCUSDT"],
                    {"lookback": 5, "exit_window": 3, "max_vol": 0.04},
                    "train",
                    "val",
                    "test",
                    {},
                ),
                strategy_number=strategy_number,
            )
            manager = DataManager(
                settings.data_root, settings.splits["future_lock_start"]
            )
            bars = _rising_bars(datetime(2025, 1, 1, tzinfo=UTC), 90)
            path = manager.save_csv(
                bars, "synthetic", "BTCUSDT", "1d", manager.audit(bars, "1d")
            )
            with memory.transaction() as db:
                db.execute(
                    "INSERT INTO asset_universe VALUES(?,?,?,?,?,?,?,?)",
                    (
                        "BTCUSDT",
                        "TRADING",
                        utc_now(),
                        utc_now(),
                        str(path),
                        None,
                        None,
                        utc_now(),
                    ),
                )

            report = HistoricalUniverseEvaluator(settings, memory).evaluate_latest()

            self.assertEqual(report["status"], "COMPLETE")
            self.assertGreater(report["return_pct"], 0)
            self.assertEqual(report["walkforward"]["folds_evaluated"], 0)
            self.assertFalse(report["walkforward"]["eligible"])


def _minute_bars(start: datetime, count: int, interval_minutes: int = 15) -> list[Bar]:
    """A gently rising series on the override's own bar size.

    Real high/low range matters here: `supertrend_adx`'s ATR would be zero on
    the degenerate open==high==low==close bars other tests use.
    """
    bars = []
    price = 100.0
    for i in range(count):
        price *= 1.0003
        bars.append(
            Bar(
                start + timedelta(minutes=interval_minutes * i),
                price / 1.0003,
                price * 1.001,
                price / 1.0003 * 0.999,
                price,
                1_000.0,
            )
        )
    return bars


class FocusedAssetOverrideTest(unittest.TestCase):
    """QUANT9: a family whose source targets a short intraday horizon on a
    handful of liquid majors is tested on its own scope, not the shared
    daily/386-asset universe built for this lab's other families.
    """

    def _settings(self, tmp: str) -> Settings:
        root = Path(tmp)
        raw = json.loads(Path("config/default.json").read_text())
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

    def _seed_supertrend_adx(self, settings: Settings, memory: ExperimentMemory) -> int:
        hypothesis = next(
            h for h in initial_hypotheses("test") if h.family == "supertrend_adx"
        )
        memory.store_hypothesis(hypothesis.canonical())
        strategy_number = memory.register_strategy(
            hypothesis.family, {}, {}, _full_policy()
        )
        params = {
            "atr_period": 10,
            "adx_period": 14,
            "multiplier": 3.0,
            "adx_threshold": 0.0,
            "supertrend_window": 40,
            "adx_window": 30,
        }
        memory.create_experiment(
            ExperimentSpec(
                "override-wiring-test",
                hypothesis,
                "d" * 64,
                ["BTCUSDT"],
                params,
                "train",
                "val",
                "test",
                {},
            ),
            strategy_number=strategy_number,
        )
        return strategy_number

    def test_a_family_with_an_override_never_touches_asset_universe(self):
        override = FAMILY_DATA_OVERRIDES["supertrend_adx"]
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            self._seed_supertrend_adx(settings, memory)
            # asset_universe is deliberately left empty: unlike every other
            # family, the override path must not depend on it at all.

            bars = _minute_bars(datetime(2024, 1, 1, tzinfo=UTC), 200, 15)
            with patch.object(BinanceProvider, "bars", return_value=bars) as mocked:
                report = HistoricalUniverseEvaluator(settings, memory).evaluate_latest()

            self.assertIsNotNone(report)
            self.assertEqual(report["status"], "COMPLETE")
            self.assertEqual(report["assets_evaluated"], len(override["symbols"]))
            called_symbols = {call.args[0] for call in mocked.call_args_list}
            called_intervals = {call.args[1] for call in mocked.call_args_list}
            self.assertEqual(called_symbols, set(override["symbols"]))
            self.assertEqual(called_intervals, {override["interval"]})

    def test_the_focused_download_is_cached_after_the_first_call(self):
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            self._seed_supertrend_adx(settings, memory)

            bars = _minute_bars(datetime(2024, 1, 1, tzinfo=UTC), 200, 15)
            with patch.object(BinanceProvider, "bars", return_value=bars) as mocked:
                HistoricalUniverseEvaluator(settings, memory).evaluate_latest()
                first_call_count = mocked.call_count
                self.assertGreater(first_call_count, 0)
                HistoricalUniverseEvaluator(settings, memory).evaluate_latest()

            self.assertEqual(mocked.call_count, first_call_count)


if __name__ == "__main__":
    unittest.main()
