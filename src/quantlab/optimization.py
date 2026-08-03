from __future__ import annotations

import json
import random
from typing import Any

from .memory import ExperimentMemory


SEED_POLICIES = (
    (0.0010, 0.03, 0.020, 1.5, 0.015, 5, 0.50),
    (0.0015, 0.05, 0.025, 2.0, 0.020, 8, 0.50),
    (0.0020, 0.05, 0.035, 2.0, 0.020, 10, 0.50),
    (0.0025, 0.08, 0.050, 2.0, 0.025, 12, 0.50),
    (0.0030, 0.08, 0.035, 2.5, 0.025, 15, 0.60),
    (0.0035, 0.10, 0.050, 2.5, 0.030, 20, 0.60),
    (0.0040, 0.10, 0.065, 2.0, 0.030, 20, 0.70),
    (0.0050, 0.12, 0.080, 2.0, 0.035, 25, 0.70),
    (0.0020, 0.06, 0.025, 3.0, 0.020, 10, 0.75),
    (0.0030, 0.08, 0.040, 3.0, 0.025, 15, 0.75),
    (0.0040, 0.10, 0.060, 3.0, 0.030, 20, 0.75),
    (0.0050, 0.12, 0.080, 3.0, 0.035, 25, 0.75),
)


# Ranked on test folds the candidate was never fitted to. Ties break on
# consistency so that, between two equal medians, the one that won more often
# rather than once by more becomes the parent.
WALKFORWARD_PARENT = """SELECT s.money_management_json FROM walkforward_scores w
   JOIN strategy_definitions s USING(strategy_number)
   WHERE s.family=? AND w.eligible=1
   ORDER BY w.median_score DESC, w.consistency DESC LIMIT 1"""

# The original ranking, kept as the fallback for a family that has no fold
# evidence yet. It reads the window the sweep also explored, so it is in-sample
# by construction and correlates +0.06 with forward rank; it is a starting
# point when nothing better exists, never a preference.
IN_SAMPLE_PARENT = """SELECT s.money_management_json FROM portfolio_backtest_runs p
   JOIN strategy_definitions s USING(strategy_number)
   WHERE s.family=? AND p.status='COMPLETE' AND p.max_drawdown<0.25
   ORDER BY (p.return_pct-p.max_drawdown) DESC LIMIT 1"""


class ExecutionOptimizer:
    """Deterministic seed population followed by bounded evolutionary mutations."""

    def __init__(self, memory: ExperimentMemory, base: dict[str, Any], seed: int = 42):
        self.memory, self.base, self.seed = memory, dict(base), seed

    def propose(self, family: str, cycle: int) -> dict[str, Any]:
        family_trial = (cycle - 1) // 3
        generation, index = divmod(family_trial, len(SEED_POLICIES))
        risk, cap, stop, reward_risk, vol_target, concurrent, confidence = (
            SEED_POLICIES[index]
        )
        policy = dict(self.base)
        source = "latin_hypercube_seed"
        if generation:
            with self.memory.session() as db:
                best = db.execute(WALKFORWARD_PARENT, (family,)).fetchone()
                parent_source = "walkforward_elite_mutation"
                if best is None:
                    best = db.execute(IN_SAMPLE_PARENT, (family,)).fetchone()
                    parent_source = "feasible_elite_mutation"
            if best:
                parent = json.loads(best["money_management_json"])
                rng = random.Random(self.seed + cycle)
                risk = float(parent["risk_per_trade"]) * rng.choice(
                    (0.8, 0.9, 1.1, 1.2)
                )
                cap = float(parent["maximum_position_fraction"]) * rng.choice(
                    (0.85, 1.0, 1.15)
                )
                stop = float(parent["stop_loss_pct"]) * rng.choice((0.85, 1.0, 1.15))
                reward_risk = float(parent["take_profit_pct"]) / max(
                    float(parent["stop_loss_pct"]), 1e-9
                )
                reward_risk *= rng.choice((0.9, 1.0, 1.1))
                vol_target = float(parent.get("volatility_target", 0.025)) * rng.choice(
                    (0.85, 1.0, 1.15)
                )
                concurrent = int(
                    round(
                        int(parent["maximum_concurrent_assets"])
                        * rng.choice((0.8, 1.0, 1.2))
                    )
                )
                confidence = float(parent["minimum_confidence"])
                source = parent_source
        policy.update(
            {
                "risk_per_trade": round(min(0.01, max(0.0005, risk)), 6),
                "maximum_position_fraction": round(min(0.20, max(0.02, cap)), 4),
                "stop_loss_pct": round(min(0.12, max(0.015, stop)), 4),
                "take_profit_pct": round(min(0.30, max(0.025, stop * reward_risk)), 4),
                "volatility_target": round(min(0.05, max(0.01, vol_target)), 4),
                "volatility_lookback": 20,
                "maximum_concurrent_assets": max(3, min(40, concurrent)),
                "minimum_confidence": confidence,
                "maximum_drawdown": 0.25,
                "drawdown_safety_buffer": 0.05,
                "optimizer_variant": f"MM-{family_trial + 1:05d}",
                "optimizer_generation": generation,
                "optimizer_source": source,
                "objective": "maximize_return_subject_to_max_drawdown_lt_25pct",
            }
        )
        return policy
