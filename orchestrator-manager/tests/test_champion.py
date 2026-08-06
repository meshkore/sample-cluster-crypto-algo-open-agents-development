import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from quantlab_manager.champion import FORWARD_2026, HISTORICAL_PHASE_1, ChampionRegistry
from quantlab_manager.memory import ExperimentMemory
from quantlab_backtester.models import ENGINE_VERSION, utc_now


def _definition(db, number: int) -> None:
    db.execute(
        """INSERT INTO strategy_definitions
           VALUES(?,?,?,?,?,?,1,?)""",
        (
            number,
            f"hash-{number}",
            "breakout",
            json.dumps({"parameters": {"lookback": number}}),
            json.dumps({"fill": "next_bar_open"}),
            json.dumps({"initial_capital": 100000.0}),
            utc_now(),
        ),
    )


def _backtest(
    db,
    number: int,
    return_pct: float,
    drawdown: float,
    benchmark: float = 0.0,
    engine: int = ENGINE_VERSION,
) -> None:
    _definition(db, number)
    db.execute(
        # Named columns, so adding one to the schema does not break the fixture.
        """INSERT INTO portfolio_backtest_runs(
           strategy_number,status,period_start,period_end,current_date,
           initial_capital,current_equity,final_equity,net_profit,return_pct,
           max_drawdown,total_days,processed_days,assets_available,assets_traded,
           trades,wins,losses,win_rate,open_positions,cash,updated_at,
           benchmark_reference,engine_version)
           VALUES(
           ?,'COMPLETE','2017-08-17T00:00:00+00:00','2025-12-31T00:00:00+00:00',
           '2025-12-31T00:00:00+00:00',100000.0,?,?,?,?,?,3059,3059,386,120,40,18,22,
           0.45,0,?,?,?,?)""",
        (
            number,
            100000.0 * (1 + return_pct),
            100000.0 * (1 + return_pct),
            100000.0 * return_pct,
            return_pct,
            drawdown,
            100000.0 * (1 + return_pct),
            utc_now(),
            benchmark,
            engine,
        ),
    )
    db.execute(
        "INSERT INTO portfolio_equity VALUES(?,?,?,?,0)",
        (number, "2017-08-17T00:00:00+00:00", 100000.0, 100000.0),
    )
    db.execute(
        "INSERT INTO portfolio_trades VALUES(?,'BTCUSDT',1,?,?,10.0,11.0,86400.0,100.0,10.0,0.1,'TAKE_PROFIT')",
        (number, "2024-01-01T00:00:00+00:00", "2024-01-02T00:00:00+00:00"),
    )


def _forward(
    db,
    number: int,
    run_id: str,
    return_pct: float,
    drawdown: float,
    benchmark: float = 0.0,
    engine: int = ENGINE_VERSION,
) -> None:
    db.execute(
        """INSERT INTO forward_portfolio_runs(run_id,strategy_number,period_start,
           period_end,as_of,initial_capital,final_equity,net_profit,return_pct,
           max_drawdown,score,trades,wins,losses,win_rate,assets_available,
           assets_traded,cash,status,current_date,target_end,processed_days,
           total_days,open_positions,benchmark_reference,engine_version)
           VALUES(?,?,'2026-01-01T00:00:00+00:00','2026-07-31T00:00:00+00:00',?,
           100000.0,?,?,?,?,?,40,18,22,0.45,468,120,?, 'FORWARD_2026',
           '2026-07-31T00:00:00+00:00','2026-07-31T00:00:00+00:00',212,212,0,?,?)""",
        (
            run_id,
            number,
            utc_now(),
            100000.0 * (1 + return_pct),
            100000.0 * return_pct,
            return_pct,
            drawdown,
            return_pct - drawdown,
            100000.0 * (1 + return_pct),
            benchmark,
            engine,
        ),
    )
    db.execute(
        "INSERT INTO forward_portfolio_equity VALUES(?,?,100000.0,100000.0,0)",
        (run_id, "2026-01-01T00:00:00+00:00"),
    )


class ChampionTest(unittest.TestCase):
    def registry(self, root: Path) -> ChampionRegistry:
        return ChampionRegistry(ExperimentMemory(root / "lab.db"))

    def build(self, db, evidence, number, run_id):
        return {
            "strategy_number": number,
            "label": f"S{number:05d}",
            "validated": True,
            "phase": evidence,
            "definition": {"family": "breakout"},
            "experiment": None,
            "backtest": {"status": "COMPLETE"},
            "assets": [],
            "trades": [
                {"symbol": "BTCUSDT", "sequence": index} for index in range(900)
            ],
            "equity_curve": [
                {"timestamp": str(index), "equity": 1.0} for index in range(4000)
            ],
        }

    def test_first_eligible_backtest_is_crowned_and_bounded(self):
        with TemporaryDirectory() as tmp:
            registry = self.registry(Path(tmp))
            with registry.memory.transaction() as db:
                _backtest(db, 1, 0.40, 0.10)
            record = registry.refresh(self.build)
            self.assertEqual(record["strategy_number"], 1)
            self.assertEqual(record["evidence"], HISTORICAL_PHASE_1)
            self.assertIsNone(record["replaced_strategy_number"])
            view = registry.current()
            self.assertEqual(view["label"], "S00001")
            self.assertEqual(len(view["trades"]), 500)
            self.assertEqual(len(view["equity_curve"]), 1200)
            self.assertEqual(view["phase1"]["status"], "COMPLETE")
            self.assertEqual(view["champion"]["evidence"], HISTORICAL_PHASE_1)

    def test_worse_and_ineligible_candidates_never_replace_the_champion(self):
        with TemporaryDirectory() as tmp:
            registry = self.registry(Path(tmp))
            with registry.memory.transaction() as db:
                _backtest(db, 1, 0.40, 0.10)
            registry.refresh(self.build)
            with registry.memory.transaction() as db:
                _backtest(db, 2, 0.20, 0.05)  # worse score
                _backtest(db, 3, 5.00, 0.40)  # breaches the drawdown limit
                _backtest(db, 4, -0.10, 0.02)  # lost capital
            record = registry.refresh(self.build)
            self.assertEqual(record["strategy_number"], 1)
            self.assertEqual(registry.current()["label"], "S00001")
            self.assertFalse(registry.decisions(1)[0]["replaced"])

    def test_strictly_better_candidate_replaces_and_is_audited(self):
        with TemporaryDirectory() as tmp:
            registry = self.registry(Path(tmp))
            with registry.memory.transaction() as db:
                _backtest(db, 1, 0.40, 0.10)
            registry.refresh(self.build)
            with registry.memory.transaction() as db:
                _backtest(db, 2, 0.60, 0.12)
            record = registry.refresh(self.build)
            self.assertEqual(record["strategy_number"], 2)
            self.assertEqual(record["replaced_strategy_number"], 1)
            decision = registry.decisions(1)[0]
            self.assertTrue(decision["replaced"])
            self.assertEqual(decision["previous_strategy_number"], 1)
            # Calmar, not return minus drawdown: 0.40 / 0.10.
            self.assertAlmostEqual(decision["previous_score"], 4.0, places=6)
            self.assertIn("beats", decision["reason"])

    def test_a_loss_never_replaces_a_profit_however_smooth_it_is(self):
        """The 2026-08-02 regression: -0.13% displaced +0.21% on a smaller dip."""
        with TemporaryDirectory() as tmp:
            registry = self.registry(Path(tmp))
            with registry.memory.transaction() as db:
                _definition(db, 391)
                _forward(db, 391, "FWD2-S00391", 0.0021, 0.0211)
            self.assertEqual(registry.refresh(self.build)["strategy_number"], 391)
            with registry.memory.transaction() as db:
                _definition(db, 658)
                _forward(db, 658, "FWD2-S00658", -0.0013, 0.0120)
            record = registry.refresh(self.build)
            self.assertEqual(record["strategy_number"], 391)
            self.assertTrue(record["profitable"])
            self.assertFalse(registry.decisions(1)[0]["replaced"])
            self.assertEqual(registry.current()["label"], "S00391")

    def test_the_comparison_itself_refuses_to_swap_a_profit_for_a_loss(self):
        """Belt and braces: the guard holds even if a loss reaches _compare."""
        stored = {
            "evidence": FORWARD_2026,
            "evidence_rank": 2,
            "strategy_number": 391,
            "score": 0.0995,
            "profitable": 1,
            "return_pct": 0.0021,
        }
        loss = {
            "evidence": FORWARD_2026,
            "strategy_number": 658,
            "score": -0.0013,
            "profitable": False,
            "return_pct": -0.0013,
        }
        better, reason = ChampionRegistry._compare(loss, stored)
        self.assertFalse(better)
        self.assertIn("is a loss", reason)
        better, reason = ChampionRegistry._compare(
            {**loss, "profitable": True, "return_pct": 0.0001, "score": 0.001},
            {**stored, "profitable": 0, "return_pct": -0.0013},
        )
        self.assertTrue(better)
        self.assertIn("is profitable", reason)

    def test_a_profit_always_takes_the_crown_from_a_loss(self):
        with TemporaryDirectory() as tmp:
            registry = self.registry(Path(tmp))
            with registry.memory.transaction() as db:
                _definition(db, 1)
                _forward(db, 1, "FWD2-S00001", -0.0013, 0.0120)
            self.assertFalse(registry.refresh(self.build)["profitable"])
            # Barely profitable, and four times the drawdown: still wins.
            with registry.memory.transaction() as db:
                _definition(db, 2)
                _forward(db, 2, "FWD2-S00002", 0.0004, 0.0480)
            record = registry.refresh(self.build)
            self.assertEqual(record["strategy_number"], 2)
            self.assertTrue(record["profitable"])
            self.assertIn("is profitable", registry.decisions(1)[0]["reason"])

    def test_ranking_does_not_reward_trading_less(self):
        """The old score peaked at inactivity; Calmar rewards earning more."""
        with TemporaryDirectory() as tmp:
            registry = self.registry(Path(tmp))
            with registry.memory.transaction() as db:
                _definition(db, 1)
                _forward(db, 1, "FWD2-S00001", 0.40, 0.10)  # earns, dips
                _definition(db, 2)
                _forward(db, 2, "FWD2-S00002", 0.001, 0.002)  # nearly idle
            self.assertEqual(registry.refresh(self.build)["strategy_number"], 1)

    def test_a_flawless_run_is_not_penalised_for_zero_drawdown(self):
        with TemporaryDirectory() as tmp:
            registry = self.registry(Path(tmp))
            with registry.memory.transaction() as db:
                _definition(db, 1)
                _forward(db, 1, "FWD2-S00001", 0.30, 0.0)
            record = registry.refresh(self.build)
            self.assertEqual(record["strategy_number"], 1)
            self.assertGreater(record["score"], 0.0)

    def test_evidence_from_a_superseded_engine_is_never_crowned(self):
        """Pre-QUANT8 runs are inflated by the sizing lookahead."""
        with TemporaryDirectory() as tmp:
            registry = self.registry(Path(tmp))
            with registry.memory.transaction() as db:
                _definition(db, 1)
                _forward(db, 1, "FWD2-S00001", 5.00, 0.02, engine=ENGINE_VERSION - 1)
            self.assertIsNone(registry.refresh(self.build))
            with registry.memory.transaction() as db:
                _definition(db, 2)
                _forward(db, 2, "FWD2-S00002", 0.01, 0.02)
            # A modest current-engine result beats a spectacular stale one.
            self.assertEqual(registry.refresh(self.build)["strategy_number"], 2)

    def test_the_benchmark_decides_between_two_profitable_strategies(self):
        with TemporaryDirectory() as tmp:
            registry = self.registry(Path(tmp))
            with registry.memory.transaction() as db:
                _definition(db, 1)
                # Bigger return, but it lagged a market that ran 30%.
                _forward(db, 1, "FWD2-S00001", 0.20, 0.05, benchmark=0.30)
            self.assertEqual(registry.refresh(self.build)["strategy_number"], 1)
            with registry.memory.transaction() as db:
                _definition(db, 2)
                # Smaller return, but it beat a flat market.
                _forward(db, 2, "FWD2-S00002", 0.05, 0.05, benchmark=-0.01)
            record = registry.refresh(self.build)
            self.assertEqual(record["strategy_number"], 2)
            self.assertAlmostEqual(record["excess_return"], 0.06, places=6)
            self.assertAlmostEqual(record["benchmark"], -0.01, places=6)

    def test_beating_nothing_is_not_an_edge(self):
        """Underperforming the benchmark scores below zero however green it is."""
        with TemporaryDirectory() as tmp:
            registry = self.registry(Path(tmp))
            with registry.memory.transaction() as db:
                _definition(db, 1)
                _forward(db, 1, "FWD2-S00001", 0.40, 0.05, benchmark=0.90)
            record = registry.refresh(self.build)
            self.assertTrue(record["profitable"])
            self.assertLess(record["score"], 0)
            self.assertAlmostEqual(record["excess_return"], -0.50, places=6)

    def test_forward_evidence_outranks_historical_and_survives_a_restart(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = self.registry(root)
            with registry.memory.transaction() as db:
                _backtest(db, 1, 5.00, 0.10)
                _backtest(db, 2, 0.30, 0.10)
            registry.refresh(self.build)
            self.assertEqual(registry.current()["champion"]["strategy_number"], 1)
            with registry.memory.transaction() as db:
                _forward(db, 2, "FWD2-S00002", -0.05, 0.09)
            record = registry.refresh(self.build)
            self.assertEqual(record["evidence"], FORWARD_2026)
            self.assertEqual(record["strategy_number"], 2)
            self.assertEqual(record["source_run_id"], "FWD2-S00002")
            # A far better historical backtest never demotes forward evidence.
            with registry.memory.transaction() as db:
                _backtest(db, 3, 9.00, 0.05)
            registry.refresh(self.build)
            restarted = self.registry(root)
            champion = restarted.current()["champion"]
            self.assertEqual(champion["strategy_number"], 2)
            self.assertEqual(champion["evidence"], FORWARD_2026)


class QualifiedStrategyTest(unittest.TestCase):
    """Phase 2 must be gated on the real portfolio result, not the synthetic one."""

    def settings(self, root: Path):
        import json
        from quantlab_manager.config import Settings

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

    def _experiment(self, db, number: int, status: str) -> None:
        db.execute(
            """INSERT INTO experiments(experiment_id,parent_ids_json,hypothesis_id,
               hypothesis_hash,code_commit,dataset_version,features_json,parameters_json,
               training_period,validation_period,test_period,assets_json,trades,
               net_return,drawdown,sharpe,sortino,profit_factor,turnover,exposure,
               slippage_model,robustness_results_json,critic_report_json,failure_reason,
               status,spec_hash,created_at,strategy_number)
               VALUES(?,'[]','H1','hh','commit','v1','[]','{}','2021/2023','LOCKED:2024',
                      'LOCKED:2025','[]',10,0.1,0.05,1.0,1.0,1.2,10.0,0.2,'bps','{}','{}',
                      NULL,?,?,?,?)""",
            (
                f"EXP-{number:06d}",
                status,
                f"spec-{number}",
                utc_now(),
                number,
            ),
        )

    def test_a_rejected_synthetic_experiment_no_longer_blocks_phase_2(self):
        from quantlab_manager.forward import ForwardEvaluator
        from quantlab_manager.memory import ExperimentMemory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self.settings(root)
            memory = ExperimentMemory(root / "lab.db")
            with memory.transaction() as db:
                db.execute(
                    "INSERT INTO hypotheses VALUES('H1','hh','fp','{}',?)",
                    (utc_now(),),
                )
                _backtest(db, 1, 0.40, 0.10)
                # The synthetic critic rejects every experiment; that verdict
                # must not veto a profitable real Phase-1 portfolio result.
                self._experiment(db, 1, "REJECT")
            selected = ForwardEvaluator(settings, memory).qualified_strategy()
            self.assertIsNotNone(selected)
            self.assertEqual(selected["strategy_number"], 1)

    def test_a_losing_or_over_drawdown_backtest_is_still_refused(self):
        from quantlab_manager.forward import ForwardEvaluator
        from quantlab_manager.memory import ExperimentMemory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self.settings(root)
            memory = ExperimentMemory(root / "lab.db")
            with memory.transaction() as db:
                db.execute(
                    "INSERT INTO hypotheses VALUES('H1','hh','fp','{}',?)",
                    (utc_now(),),
                )
                _backtest(db, 1, -0.10, 0.02)
                _backtest(db, 2, 3.00, 0.40)
                self._experiment(db, 1, "PROMOTE")
                self._experiment(db, 2, "PROMOTE")
            self.assertIsNone(ForwardEvaluator(settings, memory).qualified_strategy())


if __name__ == "__main__":
    unittest.main()


class WithdrawalTest(ChampionTest):
    def test_a_champion_crowned_by_a_superseded_engine_is_withdrawn(self):
        """Refusing to crown stale evidence does not retire what already was."""
        with TemporaryDirectory() as tmp:
            registry = self.registry(Path(tmp))
            with registry.memory.transaction() as db:
                _definition(db, 361)
                _forward(db, 361, "FWD2-S00361", 0.0024, 0.0223)
            self.assertEqual(registry.refresh(self.build)["strategy_number"], 361)
            # The engine is found to have been reading ahead all along.
            with registry.memory.transaction() as db:
                db.execute("UPDATE champion_records SET engine_version=1")
                db.execute("UPDATE forward_portfolio_runs SET engine_version=1")
            self.assertIsNone(registry.refresh(self.build))
            self.assertIsNone(registry.current())
            decision = registry.decisions(1)[0]
            self.assertFalse(decision["replaced"])
            self.assertIn("Withdrawn", decision["reason"])

    def test_an_honest_evaluation_repopulates_the_withdrawn_view(self):
        with TemporaryDirectory() as tmp:
            registry = self.registry(Path(tmp))
            with registry.memory.transaction() as db:
                _definition(db, 1)
                _forward(db, 1, "FWD2-S00001", 0.05, 0.02, engine=ENGINE_VERSION - 1)
            self.assertIsNone(registry.refresh(self.build))
            with registry.memory.transaction() as db:
                _definition(db, 2)
                _forward(db, 2, "FWD2-S00002", 0.03, 0.02)
            self.assertEqual(registry.refresh(self.build)["strategy_number"], 2)
