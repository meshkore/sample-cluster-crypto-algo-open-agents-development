from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .backtest import Backtester, CostModel
from .models import BacktestResult, Bar, Hypothesis


@dataclass
class StatisticalValidator:
    minimum_trades: int

    def validate(
        self,
        result: BacktestResult,
        bars: list[Bar],
        strategy: Any,
        initial_equity: float,
        costs: CostModel,
    ) -> dict[str, Any]:
        stressed = Backtester(
            initial_equity,
            CostModel(
                costs.commission_bps * 2,
                costs.slippage_bps * 2,
                costs.funding_bps_per_bar,
            ),
            1.0,
        ).run(bars, strategy)
        midpoint = len(bars) // 2
        halves = []
        for segment in (bars[:midpoint], bars[midpoint:]):
            halves.append(
                Backtester(initial_equity, costs).run(segment, strategy).net_return
                if len(segment) >= 3
                else 0.0
            )
        finite_metrics = all(
            math.isfinite(x)
            for x in (
                result.net_return,
                result.max_drawdown,
                result.sharpe,
                result.sortino,
            )
        )
        checks = {
            "finite_metrics": finite_metrics,
            "minimum_trades": len(result.trades) >= self.minimum_trades,
            "positive_after_costs": result.net_return > 0,
            "survives_double_costs": stressed.net_return > 0,
            "both_halves_positive": all(value > 0 for value in halves),
        }
        return {
            "checks": checks,
            "passed": all(checks.values()),
            "double_cost_net_return": stressed.net_return,
            "half_returns": halves,
            "novelty_score": 1.0,
            "limitations": [
                "Infrastructure-grade checks only; purged CV and DSR are not yet implemented.",
                "Synthetic data results cannot support a profitability claim.",
            ],
        }


class AdversarialCritic:
    def critique(
        self,
        hypothesis: Hypothesis,
        result: BacktestResult,
        robustness: dict[str, Any],
        synthetic: bool,
    ) -> dict[str, Any]:
        failures: list[str] = []
        biases: list[str] = []
        if synthetic:
            failures.append(
                "Result uses synthetic data and has no market-evidence value."
            )
        if len(result.trades) < 20:
            biases.append("Small trade sample may make metrics unstable.")
        if result.turnover > 100:
            biases.append("High turnover increases execution-model sensitivity.")
        if not robustness["checks"]["survives_double_costs"]:
            failures.append("Edge disappears when stated costs are doubled.")
        if not robustness["checks"]["both_halves_positive"]:
            biases.append(
                "Performance is not temporally stable across two coarse subperiods."
            )
        if result.max_drawdown > 0.30:
            failures.append("Maximum drawdown exceeds the MVP research tolerance.")
        verdict = (
            "REJECT"
            if failures
            else ("REQUIRE_MORE_TESTS" if biases else "PROVISIONAL_PASS")
        )
        return {
            "verdict": verdict,
            "confidence": 0.95 if synthetic else 0.65,
            "critical_failures": failures,
            "suspected_biases": biases,
            "required_tests": [
                "point-in-time multi-asset validation",
                "purged walk-forward validation",
                "parameter perturbation",
                "remove best trades",
                "execution delay stress",
            ],
            "possible_repairs": [
                "collect exchange data",
                "simplify rules",
                "expand independent regimes",
            ],
        }
