from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from quantlab_manager.config import Settings
from quantlab_backtester.data import (
    FAMILY_DATA_OVERRIDES,
    BinanceProvider,
    ForwardDataManager,
    SyntheticProvider,
)
from quantlab_manager.forward import ForwardEvaluator
from quantlab_manager.loop import ResearchDirector
from quantlab_manager.memory import ExperimentMemory
from quantlab_backtester.models import Bar, ExperimentSpec, utc_now
from quantlab_trading.strategies import initial_hypotheses


class ForwardEvaluationTest(unittest.TestCase):
    def test_only_positive_best_phase1_strategy_is_evaluated_in_2026_store(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = json.loads(Path("config/default.json").read_text())
            raw.update(
                {
                    "database_path": str(root / "lab.db"),
                    "research_root": str(root / "research"),
                    "data_root": str(root / "data"),
                }
            )
            config = root / "config.json"
            config.write_text(json.dumps(raw))
            settings = Settings.load(config)
            director = ResearchDirector(settings)
            director.run(1)
            evaluator = ForwardEvaluator(settings, director.memory)
            self.assertIsNone(evaluator.evaluate())
            strategy_number = director.memory.experiments()[-1]["strategy_number"]
            with director.memory.transaction() as db:
                db.execute(
                    "UPDATE experiments SET status='PROMOTE' WHERE strategy_number=?",
                    (strategy_number,),
                )
                db.execute(
                    """INSERT INTO portfolio_backtest_runs(
                    strategy_number,status,period_start,period_end,current_date,initial_capital,
                    current_equity,final_equity,net_profit,return_pct,max_drawdown,total_days,
                    processed_days,assets_available,assets_traded,trades,wins,losses,win_rate,
                    open_positions,cash,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        strategy_number,
                        "COMPLETE",
                        "2020-01-01",
                        "2025-12-31",
                        "2025-12-31",
                        100000,
                        120000,
                        120000,
                        20000,
                        0.20,
                        0.05,
                        2192,
                        2192,
                        1,
                        1,
                        10,
                        6,
                        4,
                        0.6,
                        0,
                        120000,
                        utc_now(),
                    ),
                )
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            end = datetime(2026, 7, 1, tzinfo=timezone.utc)
            bars = SyntheticProvider(91).bars("BTCUSDT", "1d", start, end)
            manager = ForwardDataManager(
                root / "data" / "forward", settings.splits["future_lock_start"]
            )
            path = manager.save_csv(
                bars, "synthetic", "BTCUSDT", "1d", manager.audit(bars, "1d")
            )
            with director.memory.transaction() as db:
                db.execute(
                    "INSERT INTO asset_universe VALUES(?,?,?,?,?,?,?,?)",
                    (
                        "BTCUSDT",
                        "TRADING",
                        utc_now(),
                        utc_now(),
                        None,
                        str(path),
                        None,
                        utc_now(),
                    ),
                )
                db.execute(
                    "INSERT INTO asset_liquidity VALUES(?,?,?,?,?)",
                    ("BTCUSDT", 100_000_000, 10_000, 1, utc_now()),
                )
            run_id = evaluator.evaluate()
            self.assertIsNotNone(run_id)
            latest = evaluator.latest()
            self.assertEqual(latest["initial_capital"], 100000)
            self.assertEqual(latest["period_start"], "2026-01-01T00:00:00+00:00")
            self.assertEqual(latest["assets_available"], 1)
            self.assertEqual(latest["assets"][0]["symbol"], "BTCUSDT")
            self.assertAlmostEqual(
                latest["score"], latest["return_pct"] - latest["max_drawdown"]
            )


def _hourly_bars(start: datetime, count: int) -> list[Bar]:
    """A gently rising hourly series, enough bars to clear any warmup."""
    bars = []
    price = 100.0
    for index in range(count):
        close = price * (1.0 + (0.004 if index % 3 else -0.003))
        bars.append(
            Bar(
                timestamp=start + timedelta(hours=index),
                open=price,
                high=max(price, close) * 1.001,
                low=min(price, close) * 0.999,
                close=close,
                volume=5_000.0,
                taker_buy_volume=2_600.0,
            )
        )
        price = close
    return bars


class ForwardOverrideTimeframeTest(unittest.TestCase):
    """A family listed in FAMILY_DATA_OVERRIDES is swept on its own interval
    and symbol list; the forward phase has to use the same two. Before this
    was wired, `evaluate()` read `asset_universe` unconditionally, so an
    hourly three-major hypothesis was forward-tested on daily candles across
    386 unrelated assets -- an incomparable result presented as the same
    strategy's out-of-sample evidence.
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
        config = root / "config.json"
        config.write_text(json.dumps(raw))
        return Settings.load(config)

    def _seed(self, memory: ExperimentMemory) -> int:
        hypothesis = next(
            h for h in initial_hypotheses("test") if h.family == "sma_rsi_trend"
        )
        memory.store_hypothesis(hypothesis.canonical())
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
        strategy_number = memory.register_strategy("sma_rsi_trend", {}, {}, policy)
        memory.create_experiment(
            ExperimentSpec(
                "forward-override-wiring",
                hypothesis,
                "e" * 64,
                ["BTCUSDT"],
                {
                    "fast_period": 10,
                    "slow_period": 30,
                    "rsi_period": 14,
                    "rsi_floor": 45.0,
                    "rsi_ceiling": 95.0,
                },
                "train",
                "val",
                "test",
                {},
            ),
            strategy_number=strategy_number,
        )
        with memory.transaction() as db:
            # `latest()` -- unlike `evaluate()` -- ranks only promoted rows.
            db.execute(
                "UPDATE experiments SET status='PROMOTE' WHERE strategy_number=?",
                (strategy_number,),
            )
            db.execute(
                """INSERT INTO portfolio_backtest_runs(
                strategy_number,status,period_start,period_end,current_date,initial_capital,
                current_equity,final_equity,net_profit,return_pct,max_drawdown,total_days,
                processed_days,assets_available,assets_traded,trades,wins,losses,win_rate,
                open_positions,cash,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    strategy_number,
                    "COMPLETE",
                    "2020-01-01",
                    "2025-12-31",
                    "2025-12-31",
                    100000,
                    120000,
                    120000,
                    20000,
                    0.20,
                    0.05,
                    2192,
                    2192,
                    3,
                    3,
                    50,
                    30,
                    20,
                    0.6,
                    0,
                    120000,
                    utc_now(),
                ),
            )
        return strategy_number

    def test_the_forward_phase_uses_the_family_interval_and_symbols(self):
        override = FAMILY_DATA_OVERRIDES["sma_rsi_trend"]
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            self._seed(memory)
            # asset_universe and asset_liquidity are left empty on purpose:
            # the override path must not consult them at all, so a run that
            # still succeeds here proves the data came from somewhere else.

            def bars(symbol, interval, start, end):
                return _hourly_bars(start, 400)

            with patch.object(BinanceProvider, "bars", side_effect=bars) as mocked:
                run_id = ForwardEvaluator(settings, memory).evaluate()

            self.assertIsNotNone(run_id)
            self.assertEqual(
                {call.args[1] for call in mocked.call_args_list},
                {override["interval"]},
            )
            self.assertEqual(
                {call.args[0] for call in mocked.call_args_list},
                set(override["symbols"]),
            )

    def test_the_forward_window_starts_at_the_2026_lock(self):
        with TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            memory = ExperimentMemory(settings.database_path)
            self._seed(memory)

            def bars(symbol, interval, start, end):
                return _hourly_bars(start, 400)

            with patch.object(BinanceProvider, "bars", side_effect=bars):
                evaluator = ForwardEvaluator(settings, memory)
                self.assertIsNotNone(evaluator.evaluate())
                latest = evaluator.latest()
            # Pre-2026 history is loaded so indicator warmup is satisfied, but
            # only 2026 onward is ever scored as forward evidence.
            self.assertEqual(latest["period_start"], "2026-01-01T00:00:00+00:00")
            self.assertEqual(
                latest["assets_available"],
                len(FAMILY_DATA_OVERRIDES["sma_rsi_trend"]["symbols"]),
            )


if __name__ == "__main__":
    unittest.main()
