import unittest

from quantlab import deliberation


DEFINITION = {
    "family": "volatility_expansion",
    "signal": {
        "hypothesis": {
            "id": "H-MOM-001",
            "title": "Persistent return after breakout",
            "market_mechanism": "Information arrival rather than a one-tick breach.",
            "economic_or_behavioral_story": "Slow information diffusion.",
            "trigger": "close[t] > max(close[t-20:t])",
            "entry_logic": "long after trigger",
            "exit_logic": "exit below the 10-bar mean",
            "time_horizon": "days to weeks",
            "regime": "all",
            "expected_failure_modes": ["false breakouts", "crowded momentum"],
            "invalidators": ["cost-adjusted edge <= 0"],
        },
        "parameters": {"lookback": 38},
    },
    "execution": {"commission_bps": 10.0, "slippage_bps": 5.0},
    "money_management": {
        "risk_per_trade": 0.0014,
        "stop_loss_pct": 0.079,
        "take_profit_pct": 0.138,
        "maximum_concurrent_assets": 35,
    },
}

EXPERIMENT = {
    "status": "REJECT",
    "net_return": 0.1183,
    "drawdown": 0.2198,
    "sharpe": 0.285,
    "profit_factor": 1.078,
    "trades": 28,
    "exposure": 0.3857,
    "failure_reason": "Synthetic evidence is rejected for promotion.",
    "robustness": {
        "checks": {"both_halves_positive": False, "finite_metrics": True},
        "double_cost_net_return": 0.0722,
        "half_returns": [0.1072, -0.047],
    },
    "critic": {
        "verdict": "REJECT",
        "confidence": 0.95,
        "critical_failures": ["Result uses synthetic data."],
        "suspected_biases": ["Not temporally stable."],
        "required_tests": ["purged walk-forward validation"],
    },
}

PHASE1 = {
    "status": "COMPLETE",
    "return_pct": -0.0916,
    "max_drawdown": 0.1252,
    "trades": 1961,
    "assets_traded": 118,
    "win_rate": 0.3666,
}


class DeliberationTest(unittest.TestCase):
    def test_brief_states_mechanism_parameters_and_prior_evidence(self):
        prior = {
            "family_experiments": 114,
            "family_promoted": 0,
            "family_best_score": -0.101,
            "total_experiments": 340,
        }
        message = deliberation.research_brief(
            "S00340", DEFINITION, {"lookback": 38}, prior
        )
        self.assertIn("Research brief · S00340", message)
        self.assertIn("H-MOM-001", message)
        self.assertIn("Information arrival", message)
        self.assertIn("114 experiments, 0 promoted", message)
        self.assertIn("false breakouts", message)
        self.assertLessEqual(len(message), deliberation.MAXIMUM_MESSAGE)

    def test_red_team_names_the_failed_checks_and_the_cost_stress(self):
        message = deliberation.red_team_review("S00339", EXPERIMENT)
        self.assertIn("Verdict `REJECT`", message)
        self.assertIn("both_halves_positive", message)
        self.assertIn("doubled costs give 7.22%", message)
        self.assertIn("purged walk-forward validation", message)

    def test_decision_record_carries_the_phase1_score_and_next_step(self):
        message = deliberation.decision_record("S00339", EXPERIMENT, PHASE1)
        self.assertIn("→ `REJECT`", message)
        self.assertIn("score -0.2168", message)
        self.assertIn("2026 data stays locked", message)

    def test_promoted_decision_points_at_the_forward_phase(self):
        message = deliberation.decision_record(
            "S00341", {**EXPERIMENT, "status": "PROMOTE"}, PHASE1
        )
        self.assertIn("Promote to the untouched 2026 forward phase", message)

    def test_retrospective_reports_the_champion_or_its_absence(self):
        champion = {
            "label": "S00200",
            "evidence": "FORWARD_2026",
            "score": -0.2074,
            "evaluations_considered": 298,
        }
        message = deliberation.result_retrospective("S00339", PHASE1, champion)
        self.assertIn("Public champion is now `S00200`", message)
        self.assertIn("Open question for the room", message)
        empty = deliberation.result_retrospective("S00339", PHASE1, None)
        self.assertIn("No evaluation is eligible", empty)

    def test_missing_fields_never_raise(self):
        message = deliberation.research_brief(
            "S1",
            {},
            {},
            {
                "family_experiments": 0,
                "family_promoted": 0,
                "family_best_score": None,
                "total_experiments": 0,
            },
        )
        self.assertIn("Research brief · S1", message)
        self.assertIn("n/a", message)
        self.assertIn("none recorded", deliberation.red_team_review("S1", {}))


if __name__ == "__main__":
    unittest.main()
