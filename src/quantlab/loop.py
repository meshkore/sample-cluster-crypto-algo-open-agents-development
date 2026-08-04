from __future__ import annotations

import random
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .backtest import Backtester, CostModel
from .config import Settings
from .data import DataManager, SyntheticProvider
from .memory import ExperimentMemory
from .models import ExperimentSpec, ResearchState, STATE_ORDER
from .optimization import ExecutionOptimizer, SEED_POLICIES
from .reporting import Reporter
from .strategies import build_strategy, initial_hypotheses
from .validation import AdversarialCritic, StatisticalValidator


DEFAULT_PARAMS: dict[str, dict[str, float | int]] = {
    "volatility_expansion": {"lookback": 20, "exit_window": 10, "max_vol": 0.04},
    "volume_climax": {
        "volume_window": 20,
        "holding": 3,
        "return_threshold": -0.025,
        "volume_multiple": 1.5,
    },
    "trade_abstention": {
        "fast": 8,
        "slow": 30,
        "vol_window": 15,
        "min_vol": 0.004,
        "max_vol": 0.03,
    },
    "trend_persistence": {
        "lookback": 30,
        "entry_threshold": 1.0,
        "confidence_ceiling": 3.0,
    },
    "supertrend_adx": {
        "atr_period": 10,
        "multiplier": 3.0,
        "adx_period": 14,
        "adx_threshold": 20.0,
        "supertrend_window": 40,
        "adx_window": 30,
    },
    "donchian_breakout": {"entry_period": 20, "exit_period": 10},
    "multi_factor_trend": {
        "trend_period": 50,
        "rsi_period": 14,
        "flow_short_period": 5,
        "flow_long_period": 20,
        "rsi_floor": 50.0,
        "min_votes": 2,
    },
    "regime_switching": {
        "regime_period": 200,
        "trend_period": 20,
        "rsi_period": 14,
        "oversold_rsi": 30.0,
        "bull_confidence": 1.0,
        "bear_confidence": 0.5,
    },
    "sma_rsi_trend": {
        "fast_period": 20,
        "slow_period": 50,
        "rsi_period": 14,
        "rsi_floor": 50.0,
        "rsi_ceiling": 75.0,
    },
}


class ResearchDirector:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.memory = ExperimentMemory(settings.database_path)
        self.data = DataManager(
            settings.data_root, settings.splits["future_lock_start"]
        )
        self.reporter = Reporter(settings.research_root)
        self.costs = CostModel(
            settings.commission_bps, settings.slippage_bps, settings.funding_bps_per_bar
        )
        self.execution_optimizer = ExecutionOptimizer(
            self.memory, settings.portfolio, settings.seed
        )

    def _choose_mode(self, cycle: int) -> str:
        rng = random.Random(self.settings.seed + cycle)
        modes, weights = zip(*self.settings.scheduler_weights.items())
        return rng.choices(modes, weights=weights, k=1)[0]

    def _bars(self):
        return SyntheticProvider(self.settings.seed).bars(
            "BTCUSDT",
            "1d",
            datetime(2021, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    @staticmethod
    def _parameters(family: str, cycle: int) -> dict[str, float | int]:
        """Produce a deterministic lineage: three baselines, then bounded mutations."""
        params = dict(DEFAULT_PARAMS[family])
        # Hold the signal fixed while a full population of execution policies is tested.
        generation = (cycle - 1) // (len(DEFAULT_PARAMS) * len(SEED_POLICIES))
        if generation == 0:
            return params
        if family == "volatility_expansion":
            params["lookback"] = int(params["lookback"]) + 2 * generation
        elif family == "volume_climax":
            params["volume_multiple"] = round(
                float(params["volume_multiple"]) + 0.1 * generation, 2
            )
        elif family == "trend_persistence":
            params["lookback"] = int(params["lookback"]) + 3 * generation
        elif family == "supertrend_adx":
            params["adx_threshold"] = round(
                float(params["adx_threshold"]) + 2 * generation, 2
            )
        elif family == "donchian_breakout":
            params["entry_period"] = int(params["entry_period"]) + 5 * generation
            params["exit_period"] = max(2, int(params["entry_period"]) // 2)
        elif family == "multi_factor_trend":
            params["trend_period"] = int(params["trend_period"]) + 5 * generation
        elif family == "regime_switching":
            params["regime_period"] = int(params["regime_period"]) + 10 * generation
        elif family == "sma_rsi_trend":
            # Widen the pair together so the fast/slow ratio stays intact --
            # mutating only one end walks the schedule into fast >= slow,
            # where the entry condition can never be true.
            params["fast_period"] = int(params["fast_period"]) + 4 * generation
            params["slow_period"] = int(params["slow_period"]) + 10 * generation
        else:
            params["slow"] = int(params["slow"]) + 3 * generation
        params["lineage_generation"] = generation
        return params

    @staticmethod
    def _git_commit() -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            return "uncommitted"

    def _handle(
        self, state: ResearchState, cycle: int, ctx: dict[str, Any]
    ) -> dict[str, Any]:
        if state == ResearchState.OBSERVE:
            ctx.update(
                {
                    "iteration_id": f"{cycle:06d}",
                    "previous_experiments": len(self.memory.experiments()),
                }
            )
        elif state == ResearchState.RESEARCH:
            ctx.update(
                {
                    "research_mode": self._choose_mode(cycle),
                    "sources": [],
                    "offline_cycle": True,
                }
            )
        elif state == ResearchState.IDEATE:
            hypotheses = initial_hypotheses(ctx["research_mode"])
            ctx["candidate_ids"] = [h.id for h in hypotheses]
        elif state == ResearchState.SELECT:
            hypotheses = initial_hypotheses(ctx["research_mode"])
            hypothesis = hypotheses[(cycle - 1) % len(hypotheses)]
            similar = self.memory.similar_hypotheses(hypothesis.canonical())
            ctx.update(
                {
                    "hypothesis": hypothesis.canonical(),
                    "similar": similar,
                    "difference_justification": "Cycle rotation covers a distinct mechanism family.",
                }
            )
        elif state == ResearchState.DESIGN:
            hypothesis = next(
                h
                for h in initial_hypotheses(ctx["research_mode"])
                if h.id == ctx["hypothesis"]["id"]
            )
            bars = self._bars()
            self.data.validate(bars)
            dataset_version = self.data.version(bars, "synthetic", "BTCUSDT", "1d")
            experiment_id = f"EXP-{cycle:06d}-{hypothesis.id}"
            parameters = self._parameters(hypothesis.family, cycle)
            money_management = self.execution_optimizer.propose(
                hypothesis.family, cycle
            )
            experiment_parameters = {
                **parameters,
                "_execution_variant": money_management["optimizer_variant"],
            }
            strategy_number = self.memory.register_strategy(
                hypothesis.family,
                {"hypothesis": hypothesis.canonical(), "parameters": parameters},
                {
                    "fill": "next_bar_open",
                    "commission_bps": self.costs.commission_bps,
                    "slippage_bps": self.costs.slippage_bps,
                    "long_only": True,
                },
                money_management,
            )
            spec = ExperimentSpec(
                experiment_id,
                hypothesis,
                dataset_version,
                ["BTCUSDT"],
                experiment_parameters,
                "2021-01-01/2023-12-31",
                "LOCKED:2024",
                "LOCKED:2025",
                asdict(self.costs),
            )
            ctx.update(
                {
                    "dataset_version": dataset_version,
                    "experiment_id": experiment_id,
                    "strategy_number": strategy_number,
                    "signal_parameters": parameters,
                    "execution_policy": {
                        "side": "LONG_ONLY",
                        "fill": "next_bar_open",
                        "commission_bps": self.costs.commission_bps,
                        "slippage_bps": self.costs.slippage_bps,
                    },
                    "money_management": money_management,
                    "spec": spec.canonical(),
                    "spec_hash": spec.digest(),
                }
            )
        elif state == ResearchState.IMPLEMENT:
            ctx["implementation"] = "builtin-deterministic-strategy-v1"
        elif state == ResearchState.TEST:
            hypothesis = next(
                h
                for h in initial_hypotheses(ctx["research_mode"])
                if h.id == ctx["hypothesis"]["id"]
            )
            spec = ExperimentSpec(
                ctx["experiment_id"],
                hypothesis,
                ctx["dataset_version"],
                ["BTCUSDT"],
                {
                    **self._parameters(hypothesis.family, cycle),
                    "_execution_variant": ctx["money_management"]["optimizer_variant"],
                },
                "2021-01-01/2023-12-31",
                "LOCKED:2024",
                "LOCKED:2025",
                asdict(self.costs),
            )
            self.memory.store_hypothesis(hypothesis.canonical())
            existing = self.memory.experiment_by_hash(spec.digest())
            if existing and existing["status"] != "RUNNING":
                raise RuntimeError(
                    f"exact experiment already completed as {existing['experiment_id']}"
                )
            if not existing:
                self.memory.create_experiment(
                    spec, self._git_commit(), ctx["strategy_number"]
                )
            bars = self._bars()
            strategy = build_strategy(hypothesis.family, spec.parameters)
            ctx["result"] = (
                Backtester(
                    self.settings.initial_equity,
                    self.costs,
                    self.settings.max_position_fraction,
                )
                .run(bars, strategy)
                .summary()
            )
        elif state == ResearchState.VALIDATE:
            hypothesis = next(
                h
                for h in initial_hypotheses(ctx["research_mode"])
                if h.id == ctx["hypothesis"]["id"]
            )
            bars = self._bars()
            strategy = build_strategy(
                hypothesis.family, self._parameters(hypothesis.family, cycle)
            )
            full_result = Backtester(self.settings.initial_equity, self.costs).run(
                bars, strategy
            )
            ctx["robustness"] = StatisticalValidator(
                self.settings.minimum_trades
            ).validate(
                full_result, bars, strategy, self.settings.initial_equity, self.costs
            )
        elif state == ResearchState.CRITIQUE:
            hypothesis = next(
                h
                for h in initial_hypotheses(ctx["research_mode"])
                if h.id == ctx["hypothesis"]["id"]
            )
            bars, strategy = (
                self._bars(),
                build_strategy(
                    hypothesis.family, self._parameters(hypothesis.family, cycle)
                ),
            )
            result = Backtester(self.settings.initial_equity, self.costs).run(
                bars, strategy
            )
            ctx["critic"] = AdversarialCritic().critique(
                hypothesis, result, ctx["robustness"], True
            )
        elif state == ResearchState.COMPARE:
            completed = [
                e for e in self.memory.experiments() if e["status"] != "RUNNING"
            ]
            ctx["comparison"] = {"completed_peers": len(completed), "champion": None}
        elif state == ResearchState.EVOLVE:
            critic_verdict = ctx["critic"]["verdict"]
            ctx["decision"] = "REJECT" if critic_verdict == "REJECT" else "MUTATE"
            ctx["decision_reason"] = (
                "Synthetic evidence is rejected for promotion; retain the mechanism for real-data tests."
                if ctx["decision"] == "REJECT"
                else "Evidence is provisional; mutate only after stronger validation."
            )
        elif state == ResearchState.DOCUMENT:
            status = ctx["decision"]
            failure = ctx["decision_reason"] if status == "REJECT" else None
            self.memory.finish_experiment(
                ctx["experiment_id"],
                ctx["result"],
                ctx["robustness"],
                ctx["critic"],
                status,
                failure,
            )
            path = self.reporter.write_iteration(ctx["iteration_id"], ctx)
            ctx["report_path"] = str(path)
        return ctx

    def run(self, max_cycles: int = 1, max_seconds: float | None = None) -> list[str]:
        if max_cycles <= 0:
            raise ValueError("max_cycles must be positive")
        started, completed, reports = time.monotonic(), 0, []
        while completed < max_cycles:
            if max_seconds is not None and time.monotonic() - started >= max_seconds:
                break
            state, cycle, ctx = self.memory.load_state()
            ctx = self._handle(state, cycle, ctx)
            if state == ResearchState.DOCUMENT:
                reports.append(ctx["report_path"])
                self.memory.start_next_cycle(cycle)
                completed += 1
            else:
                next_state = STATE_ORDER[STATE_ORDER.index(state) + 1]
                self.memory.save_transition(state, next_state, cycle, ctx)
        return reports

    def status(self) -> dict[str, Any]:
        state, cycle, context = self.memory.load_state()
        return {
            "state": state.value,
            "cycle": cycle,
            "context": context,
            "experiments": len(self.memory.experiments()),
        }
