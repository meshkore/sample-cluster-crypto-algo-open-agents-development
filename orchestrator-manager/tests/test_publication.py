"""The chain from a finished run to a stranger's browser.

Every link in it failed silently at least once, which is the theme: publication
is best effort by design, so nothing here raises when it breaks. That makes
these the tests that have to be explicit, because the system will not complain.

* the mirror configuration was read from a field that does not exist
* the champion was a run that never traded
* the loop's thirteen-minute fits left no trace anywhere a reader could see
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import json
import sqlite3
import unittest

from quantlab_backtester.models import utc_now
from quantlab_manager.sessions import open_database


def _insert(store, backtest_id, label, return_pct, trades, window_end="2026-12-31"):
    with store._connect() as connection:
        connection.execute(
            """INSERT INTO backtest_runs (
                 backtest_id, label, created_at, status, submitted_by,
                 strategy_family, strategy_params_json, policy_json,
                 universe_size, window_start, window_end, initial_capital,
                 return_pct, trades, updated_at
               ) VALUES (?,?,?,'complete','test','four-module','{}','{}',
                         1,'2026-01-01',?,10000.0,?,?,?)""",
            (backtest_id, label, utc_now(), window_end, return_pct, trades, utc_now()),
        )


class ChampionTest(unittest.TestCase):
    """What the page calls the best 2026 result."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.store = open_database(Path(self.tmp.name) / "lab.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_run_that_never_traded_cannot_be_the_champion(self):
        """The bug, exactly as it happened.

        A configuration gated out of the whole forward window finishes at
        +0.00%. Sorted by return that beats every honest loss, so the public
        champion was a flat line on zero trades while eighteen real results sat
        below it. Standing aside is not a result.
        """
        _insert(self.store, "abstained", "loop-001-bear-2026", 0.0, 0)
        _insert(self.store, "traded", "loop-045-bull-2026", -0.0711, 67)

        best = self.store.sidebar()["best_2026"]

        self.assertEqual(best["backtest_id"], "traded")
        self.assertEqual(best["trades"], 67)

    def test_the_champion_may_be_a_loss(self):
        """A negative champion is the honest state of this research, and the
        page must be able to say so. Filtering losses would leave the panel
        empty and imply nothing had run."""
        _insert(self.store, "worse", "a", -0.20, 12)
        _insert(self.store, "better", "b", -0.05, 9)

        self.assertEqual(self.store.sidebar()["best_2026"]["backtest_id"], "better")

    def test_no_traded_forward_run_leaves_the_panel_empty(self):
        _insert(self.store, "abstained", "loop-001-bear-2026", 0.0, 0)

        self.assertIsNone(self.store.sidebar()["best_2026"])


class HeartbeatTest(unittest.TestCase):
    """What the loop is doing between finished runs."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.store = open_database(Path(self.tmp.name) / "lab.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_heartbeat_is_one_row_rewritten(self):
        self.store.set_activity({"iteration": 46, "stage": "fit"})
        self.store.set_activity({"iteration": 47, "stage": "frame"})

        self.assertEqual(self.store.activity()["iteration"], 47)
        with self.store._connect() as connection:
            rows = connection.execute("SELECT COUNT(*) FROM loop_activity").fetchone()
        self.assertEqual(rows[0], 1)

    def test_a_database_without_the_table_has_no_heartbeat(self):
        """The monitor opens databases written before this table existed. An
        observer that dies on a missing table takes the whole page with it."""
        path = Path(self.tmp.name) / "old.db"
        sqlite3.connect(path).close()
        store = type(self.store)(path)

        self.assertIsNone(store.activity())

    def test_the_document_survives_the_round_trip(self):
        document = {
            "iteration": 47,
            "module": "BEAR",
            "fit": {"generation": 2, "of": 4, "evaluations": 31},
            "recent": [{"iteration": 46, "verdict": "REFUTED"}],
        }
        self.store.set_activity(document)

        read = self.store.activity()
        self.assertEqual(read["fit"]["evaluations"], 31)
        self.assertEqual(read["recent"][0]["verdict"], "REFUTED")
        self.assertIn("updated_at", read)


@dataclass
class _Settings:
    """Just enough of `Settings` to exercise the lookup."""

    autonomous: dict[str, Any] = field(default_factory=dict)


class MirrorConfigurationTest(unittest.TestCase):
    def test_the_configuration_is_read_from_the_field_that_exists(self):
        """The regression, named.

        `Settings` is a frozen dataclass with an `autonomous` field. The loop
        read `settings.raw` behind a `hasattr` guard, so it silently took the
        else branch on every start and ran with no mirror at all -- for a whole
        night, while `_publish` returned at its first line by design.
        """
        from quantlab_manager.cli import mirror_credentials

        settings = _Settings(
            autonomous={
                "public_mirror": {"url": "https://edge.example", "token_env": "T"}
            }
        )
        import os

        os.environ["T"] = "secret"
        try:
            mirror, token = mirror_credentials(settings)
        finally:
            del os.environ["T"]

        self.assertEqual(mirror["url"], "https://edge.example")
        self.assertEqual(token, "secret")

    def test_settings_has_no_raw_attribute(self):
        """The guard that hid the bug assumed one. Pin it, so a future guard
        written the same way fails here instead of in production."""
        from quantlab_manager.config import Settings

        self.assertFalse(hasattr(Settings(), "raw"))
        self.assertTrue(hasattr(Settings(), "autonomous"))


class ActivityPublicationTest(unittest.TestCase):
    def test_no_mirror_configured_is_a_silent_no_op(self):
        from quantlab_manager.orchestration import Orchestrator

        with TemporaryDirectory() as tmp:
            lab = Orchestrator(database=Path(tmp) / "lab.db")
            lab.publish_activity({"iteration": 1})  # must not raise
            self.assertIsNone(lab.last_publish_error)

    def test_the_heartbeat_is_posted_with_the_write_token(self):
        from quantlab_manager import orchestration

        seen: dict[str, Any] = {}

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def _urlopen(request, timeout=0):
            seen["url"] = request.full_url
            seen["body"] = json.loads(request.data)
            seen["auth"] = request.headers.get("Authorization")
            return _Response()

        with TemporaryDirectory() as tmp:
            lab = orchestration.Orchestrator(
                database=Path(tmp) / "lab.db",
                mirror_url="https://edge.example/",
                mirror_token="secret",
            )
            original = orchestration.urllib.request.urlopen
            orchestration.urllib.request.urlopen = _urlopen
            try:
                lab.publish_activity({"iteration": 47, "module": "BEAR"})
            finally:
                orchestration.urllib.request.urlopen = original

        self.assertEqual(seen["url"], "https://edge.example/api/loop")
        self.assertEqual(seen["body"]["iteration"], 47)
        self.assertEqual(seen["auth"], "Bearer secret")


if __name__ == "__main__":
    unittest.main()
