from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from quantlab_manager.config import Settings
from quantlab_manager.loop import ResearchDirector
from quantlab_trading.strategies import initial_hypotheses


class LoopTest(unittest.TestCase):
    def test_end_to_end_cycle_and_resume(self):
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
            reports = ResearchDirector(settings).run(1)
            self.assertEqual(len(reports), 1)
            self.assertTrue((Path(reports[0]) / "results.json").exists())
            status = ResearchDirector(settings).status()
            self.assertEqual(status["state"], "OBSERVE")
            self.assertEqual(status["cycle"], 2)
            self.assertEqual(status["experiments"], 1)

    def test_multiple_cycles_hold_signal_while_varying_execution(self):
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
            director = ResearchDirector(Settings.load(config))
            # One full pass over every hypothesis family, plus one, so the
            # first and last cycle land back on the same family (index 0)
            # regardless of how many families exist.
            cycles = len(initial_hypotheses("exploitation")) + 1
            self.assertEqual(len(director.run(cycles)), cycles)
            experiments = director.memory.experiments()
            self.assertEqual(len(experiments), cycles)
            parameters = [json.loads(row["parameters_json"]) for row in experiments]
            first, repeated = parameters[0], parameters[-1]
            self.assertNotEqual(
                first["_execution_variant"], repeated["_execution_variant"]
            )
            self.assertEqual(
                {k: v for k, v in first.items() if not k.startswith("_")},
                {k: v for k, v in repeated.items() if not k.startswith("_")},
            )


if __name__ == "__main__":
    unittest.main()
