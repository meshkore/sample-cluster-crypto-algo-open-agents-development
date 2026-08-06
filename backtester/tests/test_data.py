from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import unittest

from quantlab_backtester.data import (
    DataError,
    DataManager,
    ForwardDataManager,
    SyntheticProvider,
)
from quantlab_backtester.models import Bar


class DataTest(unittest.TestCase):
    def test_synthetic_is_deterministic(self):
        start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        end = start + timedelta(days=10)
        provider = SyntheticProvider(42)
        self.assertEqual(
            provider.bars("BTC", "1d", start, end),
            provider.bars("BTC", "1d", start, end),
        )

    def test_future_lock_is_enforced(self):
        with TemporaryDirectory() as tmp:
            manager = DataManager(Path(tmp), "2026-01-01T00:00:00Z")
            data = SyntheticProvider().bars(
                "BTC",
                "1d",
                datetime(2025, 12, 30, tzinfo=timezone.utc),
                datetime(2026, 1, 3, tzinfo=timezone.utc),
            )
            with self.assertRaises(DataError):
                manager.validate(data)
            with self.assertRaises(DataError):
                manager.validate_window(
                    datetime(2025, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 1, 2, tzinfo=timezone.utc),
                )

    def test_2026_is_accepted_only_by_forward_store(self):
        with TemporaryDirectory() as tmp:
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            data = SyntheticProvider().bars(
                "BTC", "1d", start, start + timedelta(days=3)
            )
            research = DataManager(Path(tmp) / "research", "2026-01-01T00:00:00Z")
            forward = ForwardDataManager(Path(tmp) / "forward", "2026-01-01T00:00:00Z")
            with self.assertRaises(DataError):
                research.validate(data)
            forward.validate(data)

    def test_audit_reports_missing_bars_and_clock_drift(self):
        with TemporaryDirectory() as tmp:
            manager = DataManager(Path(tmp), "2026-01-01T00:00:00Z")
            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            data = [
                Bar(start, 1, 1, 1, 1, 1),
                Bar(start + timedelta(days=2), 1, 1, 1, 1, 1),
                Bar(start + timedelta(days=3, minutes=1), 1, 1, 1, 1, 1),
            ]
            audit = manager.audit(data, "1d")
            self.assertFalse(audit.passed)
            self.assertEqual(audit.missing_intervals[0]["missing_bars"], 1)
            self.assertEqual(len(audit.off_grid_timestamps), 1)
            self.assertEqual(len(audit.irregular_intervals), 1)

    def test_processed_dataset_has_verified_lineage_manifest(self):
        with TemporaryDirectory() as tmp:
            manager = DataManager(Path(tmp), "2026-01-01T00:00:00Z")
            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end = start + timedelta(days=3)
            data = SyntheticProvider(42).bars("BTCUSDT", "1d", start, end)
            audit = manager.audit(data, "1d", start, end)
            path = manager.save_csv(data, "synthetic", "BTCUSDT", "1d", audit)
            manifest = json.loads(path.with_suffix(".manifest.json").read_text())
            self.assertIn(
                manager.version(data, "synthetic", "BTCUSDT", "1d"), path.name
            )
            self.assertEqual(
                manifest["file_sha256"], hashlib.sha256(path.read_bytes()).hexdigest()
            )
            self.assertTrue(manifest["audit"]["passed"])
            self.assertEqual(manager.verify_csv(path), manifest)
            path.write_text(path.read_text() + "corruption")
            with self.assertRaisesRegex(DataError, "checksum"):
                manager.verify_csv(path)

    def test_dataset_version_covers_optional_market_fields(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        first = [
            Bar(start + timedelta(days=i), 1, 1, 1, 1, 1, funding_rate=0.001)
            for i in range(3)
        ]
        second = [
            Bar(
                bar.timestamp,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                funding_rate=0.002,
            )
            for bar in first
        ]
        self.assertNotEqual(
            DataManager.version(first, "x", "BTC", "1d"),
            DataManager.version(second, "x", "BTC", "1d"),
        )

    def test_failed_audit_is_not_persisted(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = DataManager(root, "2026-01-01T00:00:00Z")
            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            data = [
                Bar(start, 1, 1, 1, 1, 1),
                Bar(start + timedelta(days=2), 1, 1, 1, 1, 1),
                Bar(start + timedelta(days=3), 1, 1, 1, 1, 1),
            ]
            with self.assertRaises(DataError):
                manager.save_csv(data, "test", "BTC", "1d")
            self.assertFalse((root / "processed").exists())

    def test_require_clean_audit_false_persists_a_gap_anyway(self):
        """A real exchange's documented downtime (Binance's first months, at
        fine intraday resolution) is an operational fact, not a bug in this
        pipeline. `require_clean_audit=False` is the disclosed exception to
        the gate above: `validate()` still runs regardless.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = DataManager(root, "2026-01-01T00:00:00Z")
            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            data = [
                Bar(start, 1, 1, 1, 1, 1),
                Bar(start + timedelta(days=2), 1, 1, 1, 1, 1),
                Bar(start + timedelta(days=3), 1, 1, 1, 1, 1),
            ]
            path = manager.save_csv(
                data, "test", "BTC", "1d", require_clean_audit=False
            )
            self.assertTrue(path.exists())
            manifest = json.loads(path.with_suffix(".manifest.json").read_text())
            self.assertFalse(manifest["audit"]["passed"])
            self.assertEqual(len(DataManager.load_csv(path)), 3)


if __name__ == "__main__":
    unittest.main()
