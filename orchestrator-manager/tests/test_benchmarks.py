"""Reading a return against what the market did over the same window.

The laboratory reported 2026 as an absolute number for ninety iterations and
concluded it was failing. It was not obviously failing: over the same window the
equal-weight basket of its own universe fell about a third. A scoreboard read
against zero cannot tell "correctly refused to participate" from "did nothing" --
they are the same number and opposite findings.

The rule these tests hold is that the benchmark is COMMENTARY. It is computed
after a result exists, it never enters selection, and it may never take an
iteration down: a missing database, an unreadable CSV or an empty window all
have to come back as an honest `None` rather than an exception.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import sqlite3
import unittest

from quantlab_manager import benchmarks
from quantlab_manager.config import Settings


def _write_series(path: Path, closes: list[float], start_day: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for index, close in enumerate(closes):
            day = start_day + index
            writer.writerow(
                [
                    f"2026-01-{day:02d}T00:00:00+00:00",
                    close,
                    close,
                    close,
                    close,
                    1000.0,
                ]
            )


class _Lab:
    """A universe on disk with a database pointing at it."""

    def __init__(self, directory: str, series: dict[str, list[float]]):
        self.root = Path(directory)
        database = self.root / "quantlab.db"
        connection = sqlite3.connect(database)
        connection.execute(
            "CREATE TABLE asset_universe (symbol TEXT PRIMARY KEY, "
            "research_path TEXT, forward_path TEXT)"
        )
        for symbol, closes in series.items():
            path = self.root / "forward" / f"{symbol}.csv"
            _write_series(path, closes)
            connection.execute(
                "INSERT INTO asset_universe VALUES (?, ?, ?)",
                (symbol, None, str(path)),
            )
        connection.commit()
        connection.close()
        self.settings = Settings(database_path=database, data_root=self.root)


class TestTheMarketIsMeasuredNotAssumed(unittest.TestCase):
    def test_a_falling_basket_is_reported_as_falling(self):
        with TemporaryDirectory() as directory:
            lab = _Lab(
                directory,
                {
                    "BTCUSDT": [100.0, 90.0, 80.0, 70.0],
                    "ETHUSDT": [100.0, 80.0, 60.0, 50.0],
                },
            )
            report = benchmarks.market(
                lab.settings, "2026-01-01", "2026-01-04", strategy_return=0.0
            )
        self.assertIsNone(report["error"])
        self.assertLess(report["equal_weight"], -0.2)
        self.assertLess(report["buy_and_hold"], -0.2)

    def test_standing_in_cash_through_a_crash_is_positive_excess(self):
        """The finding the laboratory could not state. A flat book in a market
        that fell 30% has done something, and against zero it looks like
        nothing."""
        with TemporaryDirectory() as directory:
            lab = _Lab(
                directory,
                {"BTCUSDT": [100.0, 80.0, 70.0], "ETHUSDT": [100.0, 75.0, 65.0]},
            )
            report = benchmarks.market(
                lab.settings, "2026-01-01", "2026-01-03", strategy_return=0.0
            )
        self.assertGreater(report["excess_return"], 0.25)
        self.assertIn("excess", benchmarks.describe(report))

    def test_the_reference_is_the_harder_of_the_two(self):
        """Beat the better benchmark, so a strategy cannot look good merely by
        picking the weaker comparison."""
        with TemporaryDirectory() as directory:
            lab = _Lab(
                directory,
                {"BTCUSDT": [100.0, 130.0, 150.0], "ALTUSDT": [100.0, 60.0, 50.0]},
            )
            report = benchmarks.market(
                lab.settings, "2026-01-01", "2026-01-03", strategy_return=0.10
            )
        self.assertEqual(report["reference_name"], "buy_and_hold")
        self.assertLess(report["excess_return"], 0.0)

    def test_only_the_named_symbols_are_compared(self):
        with TemporaryDirectory() as directory:
            lab = _Lab(
                directory,
                {"BTCUSDT": [100.0, 110.0, 120.0], "ALTUSDT": [100.0, 10.0, 5.0]},
            )
            narrow = benchmarks.market(
                lab.settings, "2026-01-01", "2026-01-03", symbols=["BTCUSDT"]
            )
            wide = benchmarks.market(lab.settings, "2026-01-01", "2026-01-03")
        self.assertEqual(narrow["assets"], 1)
        self.assertEqual(wide["assets"], 2)
        self.assertGreater(narrow["equal_weight"], wide["equal_weight"])


class TestABenchmarkNeverTakesAnIterationDown(unittest.TestCase):
    """Commentary on a result must not be able to destroy the result."""

    def test_a_machine_with_no_universe_table_reports_rather_than_raises(self):
        with TemporaryDirectory() as directory:
            settings = Settings(database_path=Path(directory) / "absent.db")
            report = benchmarks.market(settings, "2026-01-01", "2026-12-31")
        self.assertIsNone(report["reference"])
        self.assertIsNotNone(report["error"])
        self.assertIn("unavailable", benchmarks.describe(report))

    def test_an_unreadable_series_is_skipped_not_fatal(self):
        with TemporaryDirectory() as directory:
            lab = _Lab(directory, {"BTCUSDT": [100.0, 90.0, 80.0]})
            broken = lab.root / "forward" / "BROKEN.csv"
            broken.write_text("this is not a csv this laboratory can read")
            connection = sqlite3.connect(lab.settings.database_path)
            connection.execute(
                "INSERT INTO asset_universe VALUES (?, ?, ?)",
                ("BROKENUSDT", None, str(broken)),
            )
            connection.commit()
            connection.close()
            report = benchmarks.market(lab.settings, "2026-01-01", "2026-01-03")
        self.assertEqual(report["assets"], 1)
        self.assertIsNotNone(report["equal_weight"])

    def test_a_window_with_no_bars_in_it_is_not_an_exception(self):
        with TemporaryDirectory() as directory:
            lab = _Lab(directory, {"BTCUSDT": [100.0, 90.0, 80.0]})
            report = benchmarks.market(lab.settings, "2026-06-01", "2026-06-30")
        self.assertIsNone(report["reference"])

    def test_a_nonsense_window_is_reported_rather_than_raised(self):
        with TemporaryDirectory() as directory:
            lab = _Lab(directory, {"BTCUSDT": [100.0, 90.0, 80.0]})
            report = benchmarks.market(lab.settings, "not-a-date", "2026-01-03")
        self.assertIsNotNone(report["error"])
        self.assertIsNone(report["reference"])

    def test_describing_nothing_does_not_raise(self):
        self.assertIn("unavailable", benchmarks.describe({}))
        self.assertIn("unavailable", benchmarks.describe(None))


if __name__ == "__main__":
    unittest.main()
