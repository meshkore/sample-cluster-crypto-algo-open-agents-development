from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from quantlab.data import MarketSnapshot
from quantlab.memory import ExperimentMemory
from quantlab.universe import UniverseManager


class UniverseLiquidityTest(unittest.TestCase):
    def test_current_liquid_slice_uses_turnover_trade_count_and_top_n(self):
        with TemporaryDirectory() as tmp:
            manager = UniverseManager(
                ExperimentMemory(Path(tmp) / "lab.db"),
                Path(tmp) / "data",
                "2026-01-01T00:00:00Z",
                {
                    "maximum_assets": 2,
                    "minimum_quote_volume_24h": 5_000_000,
                    "minimum_trade_count_24h": 1_000,
                },
            )
            snapshots = {
                "BTCUSDT": MarketSnapshot("BTCUSDT", 100_000_000, 10_000),
                "ETHUSDT": MarketSnapshot("ETHUSDT", 50_000_000, 10_000),
                "THINUSDT": MarketSnapshot("THINUSDT", 100_000_000, 10),
                "SMALLUSDT": MarketSnapshot("SMALLUSDT", 2_000_000, 10_000),
            }
            self.assertEqual(
                manager.select_liquid_symbols(list(snapshots), snapshots),
                {"BTCUSDT", "ETHUSDT"},
            )


if __name__ == "__main__":
    unittest.main()
