import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from quantlab_manager.public_ledger import GitLedgerPublisher, PublicResearchLedger


def context() -> dict:
    return {
        "iteration_id": "000001",
        "experiment_id": "EXP-000001-test",
        "strategy_number": 1,
        "hypothesis": {"family": "trade_abstention"},
        "spec": {"training_period": "2021-01-01/2023-12-31", "parameters": {"fast": 8}},
        "decision": "REJECT",
        "decision_reason": "Synthetic evidence cannot be promoted.",
        "result": {
            "net_return": 0.02,
            "drawdown": 0.04,
            "sharpe": 1.2,
            "sortino": 1.4,
            "profit_factor": 1.1,
            "trades": 7,
        },
        "execution_policy": {"side": "LONG_ONLY"},
        "money_management": {"risk_per_trade": 0.01},
    }


class PublicLedgerTest(unittest.TestCase):
    def test_writes_history_and_never_promotes_a_rejected_candidate(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = PublicResearchLedger(root)
            ledger.write(context())
            ledger.write(context())
            history = json.loads((root / "public" / "iterations.json").read_text())
            best = json.loads((root / "public" / "best-strategy.json").read_text())
            self.assertEqual(len(history), 1)
            self.assertEqual(best["best_provisional"]["strategy"], "S00001")
            self.assertFalse(best["forward_2026_authorized"])
            self.assertIsNone(best["best_promoted"])

    def test_publisher_is_off_without_an_explicit_repository_root(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(GitLedgerPublisher().enabled)
