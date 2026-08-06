from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantlab_manager.memory import ExperimentMemory
from quantlab_backtester.models import ExperimentSpec, ResearchState
from quantlab_trading.strategies import initial_hypotheses


class MemoryTest(unittest.TestCase):
    def test_transition_persists(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "lab.db"
            memory = ExperimentMemory(path)
            memory.save_transition(
                ResearchState.OBSERVE, ResearchState.RESEARCH, 1, {"x": 1}
            )
            self.assertEqual(
                ExperimentMemory(path).load_state(),
                (ResearchState.RESEARCH, 1, {"x": 1}),
            )

    def test_run_label_does_not_defeat_duplicate_hash(self):
        hypothesis = initial_hypotheses("test")[0]
        base = ExperimentSpec(
            "A", hypothesis, "d" * 64, ["BTC"], {}, "train", "val", "test", {}
        )
        self.assertEqual(base.digest(), replace(base, experiment_id="B").digest())

    def test_scheduler_provenance_does_not_defeat_duplicate_hash(self):
        first = initial_hypotheses("exploitation")[0]
        second = initial_hypotheses("contrarian")[0]
        a = ExperimentSpec(
            "A", first, "d" * 64, ["BTC"], {}, "train", "val", "test", {}
        )
        b = ExperimentSpec(
            "B", second, "d" * 64, ["BTC"], {}, "train", "val", "test", {}
        )
        self.assertEqual(a.digest(), b.digest())

    def test_hypothesis_deduplicates(self):
        with TemporaryDirectory() as tmp:
            memory = ExperimentMemory(Path(tmp) / "lab.db")
            document = initial_hypotheses("test")[0].canonical()
            self.assertTrue(memory.store_hypothesis(document)[1])
            self.assertFalse(memory.store_hypothesis(document)[1])

    def test_strategy_numbers_are_incremental_and_deduplicated(self):
        with TemporaryDirectory() as tmp:
            memory = ExperimentMemory(Path(tmp) / "lab.db")
            one = memory.register_strategy(
                "momentum", {"x": 1}, {"fill": "next"}, {"risk": 0.01}
            )
            duplicate = memory.register_strategy(
                "momentum", {"x": 1}, {"fill": "next"}, {"risk": 0.01}
            )
            two = memory.register_strategy(
                "reversal", {"x": 2}, {"fill": "next"}, {"risk": 0.01}
            )
            self.assertEqual(one, duplicate)
            self.assertEqual(two, one + 1)


if __name__ == "__main__":
    unittest.main()
