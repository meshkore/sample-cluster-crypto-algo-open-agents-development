from pathlib import Path
from tempfile import TemporaryDirectory
import json
import threading
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

    def test_a_committee_round_runs_one_reviewer_then_the_builder(self):
        """Rotation: one agent session per round, not two, to halve the cost."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = AutonomousService(self.settings(root), root)
            order = []
            service.run_anthropic_agent = lambda spec: order.append(spec["id"]) or True
            service.run_agent = lambda role="builder": order.append(role) or True
            self.assertTrue(service.run_committee())
            self.assertEqual(order[-1], "builder")
            self.assertEqual(len(order[:-1]), 1)
            self.assertIn(order[0], {"claude-opus-critic", "claude-sonnet-critic"})

    def test_the_configured_panel_carries_two_distinct_anthropic_models(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = AutonomousService(self.settings(root), root)
            service.options = {**service.options, "committee_rotate": False}
            panel = service.anthropic_panel()
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


class CommitteeRotationTest(unittest.TestCase):
    """Two full agent sessions an hour was the laboratory's largest expense."""

    def panel(self, completed: int, rotate: bool = True):
        from unittest.mock import MagicMock

        service = AutonomousService.__new__(AutonomousService)
        service.options = {
            "committee_rotate": rotate,
            "anthropic_agents": [
                {"id": "opus", "enabled": True},
                {"id": "sonnet", "enabled": True},
            ],
        }
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (completed,)
        memory = MagicMock()
        memory.session.return_value.__enter__.return_value = db
        service.director = MagicMock(memory=memory)
        return [spec["id"] for spec in service.anthropic_panel()]

    def test_one_reviewer_runs_per_round_and_they_alternate(self):
        self.assertEqual(self.panel(0), ["opus"])
        self.assertEqual(self.panel(1), ["sonnet"])
        self.assertEqual(self.panel(2), ["opus"])

    def test_rotation_can_be_switched_off(self):
        self.assertEqual(self.panel(0, rotate=False), ["opus", "sonnet"])


class WallBudgetTest(unittest.TestCase):
    """Individual call sites were each reasonable and together flooded."""

    def service(self, **options):
        service = AutonomousService.__new__(AutonomousService)
        service.options = options
        service._wall_lock = threading.Lock()
        service._wall_posts = []
        return service

    def test_posts_are_rate_limited_per_hour(self):
        service = self.service(cluster_max_per_hour=3)
        self.assertEqual(
            [service._wall_budget_allows() for _ in range(5)],
            [True, True, True, False, False],
        )

    def test_posts_are_spaced_apart(self):
        service = self.service(cluster_min_interval_seconds=600)
        self.assertTrue(service._wall_budget_allows())
        self.assertFalse(service._wall_budget_allows())

    def test_no_limits_configured_means_no_throttle(self):
        service = self.service()
        self.assertTrue(all(service._wall_budget_allows() for _ in range(50)))

    def test_the_hourly_window_forgets_old_posts(self):
        service = self.service(cluster_max_per_hour=2)
        self.assertTrue(service._wall_budget_allows())
        self.assertTrue(service._wall_budget_allows())
        self.assertFalse(service._wall_budget_allows())
        # Pretend the recorded posts happened over an hour ago.
        service._wall_posts = [t - 3601 for t in service._wall_posts]
        self.assertTrue(service._wall_budget_allows())
