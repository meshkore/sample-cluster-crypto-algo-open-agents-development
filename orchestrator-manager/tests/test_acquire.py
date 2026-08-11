"""Bootstrapping a machine that has never held this project's data.

The bug these tests exist for was invisible from the operator's machine: the
`asset_universe` table every component reads was created by code that is not in
this repository, and the documented `download` command crashed on its first
line. Both are fine forever if your machine already has the table. Neither is
fine for anybody else.

Nothing here touches the network. What is worth pinning down is the part that
decides whether a download is safe to start and what survives a failed one.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import sqlite3
import unittest

from quantlab_manager import acquire
from quantlab_manager.config import Settings


def _settings(directory: str) -> Settings:
    root = Path(directory)
    return Settings(
        database_path=root / "research" / "quantlab.db",
        research_root=root / "research",
        data_root=root / "data",
        splits={"future_lock_start": "2026-01-01T00:00:00Z"},
    )


class TestTheUniverseTableIsCreatedNotAssumed(unittest.TestCase):
    def test_a_machine_with_no_database_gets_one(self):
        with TemporaryDirectory() as directory:
            settings = _settings(directory)
            self.assertFalse(settings.database_path.exists())
            acquire.ensure_schema(settings.database_path)
            connection = sqlite3.connect(settings.database_path)
            try:
                names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            finally:
                connection.close()
        self.assertIn("asset_universe", names)

    def test_creating_twice_is_not_an_error(self):
        # `download` is resumable, so this runs on every invocation.
        with TemporaryDirectory() as directory:
            path = Path(directory) / "quantlab.db"
            acquire.ensure_schema(path)
            acquire.ensure_schema(path)


class TestAFailedSymbolDoesNotEraseAGoodOne(unittest.TestCase):
    """The store is built over ~15 minutes of network calls and symbols get
    delisted mid-run. A later failure overwriting an earlier success would turn
    a partial refresh into data loss, and the loss is silent -- the row is still
    there, just pointing at nothing."""

    def _connect(self, directory):
        path = Path(directory) / "quantlab.db"
        acquire.ensure_schema(path)
        return sqlite3.connect(path)

    def test_an_error_keeps_the_paths_it_could_not_replace(self):
        with TemporaryDirectory() as directory:
            connection = self._connect(directory)
            acquire._record(
                connection,
                "BTCUSDT",
                status="TRADING",
                research="data/research/BTCUSDT.csv",
                forward="data/forward/BTCUSDT.csv",
                error=None,
            )
            acquire._record(
                connection,
                "BTCUSDT",
                status="ERROR",
                research=None,
                forward=None,
                error="Binance download failed: 451",
            )
            row = connection.execute(
                "SELECT status, research_path, forward_path, last_error "
                "FROM asset_universe WHERE symbol = 'BTCUSDT'"
            ).fetchone()
            connection.close()

        self.assertEqual(row[0], "ERROR")
        self.assertEqual(row[1], "data/research/BTCUSDT.csv")
        self.assertEqual(row[2], "data/forward/BTCUSDT.csv")
        self.assertIn("451", row[3])

    def test_a_successful_refresh_clears_the_previous_error(self):
        with TemporaryDirectory() as directory:
            connection = self._connect(directory)
            acquire._record(
                connection,
                "ETHUSDT",
                status="ERROR",
                research=None,
                forward=None,
                error="timed out",
            )
            acquire._record(
                connection,
                "ETHUSDT",
                status="TRADING",
                research="r.csv",
                forward="f.csv",
                error=None,
            )
            row = connection.execute(
                "SELECT status, research_path, last_error FROM asset_universe "
                "WHERE symbol = 'ETHUSDT'"
            ).fetchone()
            connection.close()
        self.assertEqual(row[0], "TRADING")
        self.assertEqual(row[1], "r.csv")
        self.assertIsNone(row[2])


class TestTheDiskIsCheckedBeforeAnythingIsWritten(unittest.TestCase):
    def test_the_estimate_counts_the_backfill_not_just_the_candles(self):
        """Candles are the small half. A contributor told only the candle
        figure budgets 53 MB for something that ends up costing 650 MB."""
        with TemporaryDirectory() as directory:
            budget = acquire.disk_budget(_settings(directory), 386)
        self.assertGreater(budget["indicators_bytes"], budget["candles_bytes"] * 5)
        self.assertGreater(
            budget["total_bytes_needed"],
            budget["candles_bytes"] + budget["indicators_bytes"],
        )

    def test_it_reports_free_space_whether_or_not_it_passes(self):
        with TemporaryDirectory() as directory:
            small = acquire.disk_budget(_settings(directory), 2)
            huge = acquire.disk_budget(_settings(directory), 100_000_000)
        self.assertTrue(small["sufficient"])
        self.assertFalse(huge["sufficient"])
        self.assertGreater(huge["free_bytes"], 0)

    def test_a_download_that_cannot_fit_refuses_before_the_first_request(self):
        """It must refuse without touching the network. A disk check that only
        fires after fifteen minutes of downloading is not a check."""
        from quantlab_backtester.data import DataError

        full = SimpleNamespace(total=1 << 40, used=1 << 40, free=1_000_000)
        with TemporaryDirectory() as directory:
            with patch.object(acquire.shutil, "disk_usage", return_value=full):
                with self.assertRaises(DataError) as caught:
                    acquire.acquire(
                        _settings(directory), symbols=["BTCUSDT", "ETHUSDT"]
                    )
        message = str(caught.exception)
        self.assertIn("free", message)
        self.assertIn("--limit", message)


class TestTheLockHasOneOwner(unittest.TestCase):
    def test_the_boundary_comes_from_the_config(self):
        with TemporaryDirectory() as directory:
            self.assertEqual(
                acquire.lock_of(_settings(directory)), "2026-01-01T00:00:00Z"
            )

    def test_a_config_without_splits_still_seals_2026(self):
        # Degrading to "no lock" would be the one failure mode this project
        # cannot survive, so the default is the lock rather than nothing.
        self.assertTrue(acquire.lock_of(Settings()).startswith("2026-01-01"))


if __name__ == "__main__":
    unittest.main()
