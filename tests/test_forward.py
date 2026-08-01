from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from quantlab.config import Settings
from quantlab.data import ForwardDataManager, SyntheticProvider
from quantlab.forward import ForwardEvaluator
from quantlab.loop import ResearchDirector
from quantlab.models import utc_now


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


if __name__ == "__main__":
    unittest.main()
