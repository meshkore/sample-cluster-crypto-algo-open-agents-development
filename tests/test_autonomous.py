from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from quantlab.autonomous import AutonomousService, DashboardData
from quantlab.config import Settings


class AutonomousTest(unittest.TestCase):
    def settings(self, root: Path) -> Settings:
        raw = json.loads(Path("config/default.json").read_text())
        raw.update(
            {
                "database_path": str(root / "lab.db"),
                "research_root": str(root / "research"),
                "data_root": str(root / "data"),
            }
        )
        raw["autonomous"].update({"agent_enabled": False, "dashboard_port": 0})
        config = root / "config.json"
        config.write_text(json.dumps(raw))
        return Settings.load(config)

    def test_dashboard_hides_history_and_labels_unvalidated_best(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self.settings(root)
            service = AutonomousService(settings, root)
            service.director.run(2)
            snapshot = DashboardData(settings).snapshot()
            self.assertIsNone(snapshot["champion"])
            self.assertIsNotNone(snapshot["best_unvalidated_candidate"])
            self.assertNotIn("history", snapshot)
            self.assertIn("committee", snapshot)
            self.assertIn("current_strategy", snapshot)
            self.assertIn("last_completed_strategy", snapshot)
            self.assertIn("best_strategy", snapshot)
            self.assertIn("activity", snapshot)
            self.assertIn("current engine", snapshot["warning"])
            self.assertIsNone(snapshot["best_strategy"])
            self.assertIsNone(snapshot["champion_record"])

    def test_agent_unavailable_is_recorded_without_crashing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self.settings(root)
            service = AutonomousService(settings, root)
            service.run_agent()
            with service.director.memory.session() as db:
                event = db.execute(
                    "SELECT level FROM daemon_events ORDER BY id DESC LIMIT 1"
                ).fetchone()
            self.assertEqual(event["level"], "WARNING")

    def test_committee_runs_every_anthropic_reviewer_then_the_builder(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = AutonomousService(self.settings(root), root)
            order = []
            service.run_anthropic_agent = lambda spec: order.append(spec["id"]) or True
            service.run_agent = lambda role="builder": order.append(role) or True
            self.assertTrue(service.run_committee())
            self.assertEqual(order[-1], "builder")
            self.assertEqual(
                sorted(order[:-1]), ["claude-opus-critic", "claude-sonnet-critic"]
            )

    def test_the_panel_carries_two_distinct_anthropic_models(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            panel = AutonomousService(self.settings(root), root).anthropic_panel()
            models = [agent["model"] for agent in panel]
            self.assertEqual(models, ["claude-opus-5", "claude-sonnet-5"])
            # Separate advisory files, or the second review overwrites the first.
            self.assertEqual(len({agent["advisory"] for agent in panel}), len(panel))
            self.assertEqual(len({agent["wall_agent"] for agent in panel}), len(panel))

    def test_a_disabled_reviewer_is_skipped(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self.settings(root)
            settings.autonomous["anthropic_agents"][1]["enabled"] = False
            panel = AutonomousService(settings, root).anthropic_panel()
            self.assertEqual([agent["id"] for agent in panel], ["claude-opus-critic"])


if __name__ == "__main__":
    unittest.main()
