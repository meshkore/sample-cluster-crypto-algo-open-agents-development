"""The backfilled indicator cache, and the catalogue it stores.

Two things must hold or the cache is worse than no cache: a stored panel must be
identical to a freshly computed one, and a panel about different candles must
never be served. A stale cache is indistinguishable from a correct one until a
result has already been published.
"""

from array import array
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import gzip
import unittest

from quantlab_backtester.indicator_store import IndicatorStore
from quantlab_backtester.indicators import (
    IndicatorSpec,
    column_names,
    panel_for,
)
from quantlab_backtester.models import Bar

UTC = timezone.utc


def _bars(count: int = 400, seed: float = 100.0) -> list[Bar]:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    out, price = [], seed
    for i in range(count):
        price *= 1.012 if i % 3 else 0.985
        out.append(
            Bar(
                timestamp=start + timedelta(days=i),
                open=price * 0.999,
                high=price * 1.02,
                low=price * 0.98,
                close=price,
                volume=1_000_000.0 + i * 1_000,
            )
        )
    return out


class CatalogueTest(unittest.TestCase):
    def test_the_catalogue_is_broad_and_named(self):
        names = column_names()
        self.assertGreater(len(names), 60, "the catalogue collapsed")
        for expected in (
            "sma_200",
            "ema_50",
            "rsi_14",
            "macd_hist",
            "atr_14",
            "bb_percent_b",
            "adx",
            "di_plus",
            "stoch_k",
            "williams_r",
            "cci",
            "obv",
            "money_flow_index",
            "chaikin_money_flow",
            "supertrend_direction",
            "aroon_osc",
            "vortex_plus",
            "keltner_upper",
            "pct_below_high_200",
            "drawdown_from_high",
            "vwap_rolling",
            "force_index",
        ):
            self.assertIn(expected, names)

    def test_every_column_is_populated_once_warmed_up(self):
        """A column that is always None is a formula that silently never fires."""
        spec = IndicatorSpec()
        bars = _bars(spec.warmup_bars() + 120)
        panel = panel_for(bars, spec)
        row = panel.at(len(bars) - 1)
        empty = sorted(name for name, value in row.items() if value is None)
        self.assertEqual(empty, [], f"columns never produced a value: {empty}")

    def test_warm_up_is_none_not_zero(self):
        panel = panel_for(_bars(60), IndicatorSpec())
        self.assertIsNone(panel.at(0)["sma_200"])
        self.assertIsNone(panel.at(10)["sma_20"])
        self.assertIsNotNone(panel.at(30)["sma_20"])

    def test_the_catalogue_is_causal_under_truncation(self):
        """Prefix equality over EVERY column. Any forward-looking window fails
        this at every cut point."""
        spec = IndicatorSpec()
        bars = _bars(420)
        full = panel_for(bars, spec)
        for cut in (300, 350, 419):
            truncated = panel_for(bars[:cut], spec)
            for key, value in truncated.at(cut - 1).items():
                expected = full.at(cut - 1)[key]
                if value is None or expected is None:
                    self.assertEqual(value, expected, f"{key} at cut {cut}")
                else:
                    self.assertAlmostEqual(
                        value, expected, places=6, msg=f"{key} at cut {cut}"
                    )

    def test_known_values(self):
        """Anchors against arithmetic done by hand, so a plausible-but-wrong
        formula cannot pass by merely being self-consistent."""
        start = datetime(2020, 1, 1, tzinfo=UTC)
        closes = [float(x) for x in range(1, 31)]
        bars = [
            Bar(
                timestamp=start + timedelta(days=i),
                open=c,
                high=c,
                low=c,
                close=c,
                volume=100.0,
            )
            for i, c in enumerate(closes)
        ]
        panel = panel_for(bars, IndicatorSpec())
        # closes 6..25 average to 15.5
        self.assertAlmostEqual(panel.at(24)["sma_20"], 15.5, places=9)
        # a monotone rise has no down moves, so RSI pins at 100
        self.assertAlmostEqual(panel.at(24)["rsi_14"], 100.0, places=6)
        # five bars back from 25 is 20
        self.assertAlmostEqual(panel.at(24)["return_5"], 25 / 20 - 1, places=9)
        # never below its own running high
        self.assertAlmostEqual(panel.at(24)["drawdown_from_high"], 0.0, places=9)

    def test_rsi_uses_wilder_smoothing_not_a_plain_average(self):
        """Hand-computed, because a monotone series pins RSI at 100 either way
        and prefix equality is satisfied by any causal window -- so nothing else
        here can tell Wilder from a simple moving average.

        closes 10, 11, 10.5, 11.5, 11, 12 with period 3.
          seed:   avg gain 2/3, avg loss 1/6            -> RSI 80 at bar 3
          then:   gain 0,   loss 0.5                    -> RSI 61.538 at bar 4
          then:   gain 1,   loss 0                      -> RSI 77.273 at bar 5
        A plain average would give 80 again at bar 5.
        """
        start = datetime(2020, 1, 1, tzinfo=UTC)
        closes = [10.0, 11.0, 10.5, 11.5, 11.0, 12.0]
        bars = [
            Bar(
                timestamp=start + timedelta(days=i),
                open=c,
                high=c,
                low=c,
                close=c,
                volume=100.0,
            )
            for i, c in enumerate(closes)
        ]
        panel = panel_for(bars, IndicatorSpec(rsi_periods=(3,)))
        self.assertAlmostEqual(panel.at(3)["rsi_3"], 80.0, places=6)
        self.assertAlmostEqual(panel.at(4)["rsi_3"], 61.538461, places=5)
        self.assertAlmostEqual(panel.at(5)["rsi_3"], 77.272727, places=5)

    def test_the_spec_key_changes_with_the_spec(self):
        self.assertNotEqual(
            IndicatorSpec().cache_key(),
            IndicatorSpec(rsi_periods=(9,)).cache_key(),
        )


class IndicatorStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.store = IndicatorStore(Path(self.tmp.name))
        self.spec = IndicatorSpec()
        self.bars = _bars(320)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_saved_panel_reloads_identically(self):
        fresh = panel_for(self.bars, self.spec)
        self.store.save("AAA", self.bars, fresh, self.spec)
        loaded = self.store.load("AAA", self.bars, self.spec)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.names, fresh.names)
        self.assertEqual(loaded.warmup_bars, fresh.warmup_bars)
        for index in (0, 50, 200, len(self.bars) - 1):
            self.assertEqual(loaded.at(index), fresh.at(index), f"bar {index}")

    def test_a_cache_about_different_candles_is_refused(self):
        """The failure this design exists to prevent."""
        self.store.save("AAA", self.bars, panel_for(self.bars, self.spec), self.spec)
        # same dates and bar count, different prices: the header must catch it
        self.assertIsNone(
            self.store.load("AAA", _bars(320, seed=250.0), self.spec),
            "a cache built on different prices was served",
        )
        self.assertIsNone(self.store.load("AAA", self.bars[:-1], self.spec))

    def test_a_different_spec_uses_a_different_file(self):
        other = IndicatorSpec(rsi_periods=(9,))
        self.assertNotEqual(
            self.store.path_for("AAA", self.spec), self.store.path_for("AAA", other)
        )
        self.store.save("AAA", self.bars, panel_for(self.bars, self.spec), self.spec)
        self.assertIsNone(self.store.load("AAA", self.bars, other))

    def test_a_corrupt_cache_is_ignored_rather_than_fatal(self):
        path = self.store.path_for("AAA", self.spec)
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt") as handle:
            handle.write("this is not a panel\n")
        self.assertIsNone(self.store.load("AAA", self.bars, self.spec))
        # and `panel` still returns a usable one
        self.assertIsNotNone(self.store.panel("AAA", self.bars, self.spec))

    def test_panel_computes_then_reuses(self):
        first = self.store.panel("AAA", self.bars, self.spec)
        self.assertTrue(self.store.path_for("AAA", self.spec).exists())
        second = self.store.panel("AAA", self.bars, self.spec)
        self.assertEqual(first.at(300), second.at(300))

    def test_backfill_reports_what_it_did(self):
        universe = {
            "AAA": self.bars,
            "BBB": _bars(300, seed=7.0),
            "TINY": self.bars[:1],
        }
        report = self.store.backfill(universe, self.spec)
        self.assertEqual(report["written"], 2)
        self.assertEqual(report["reused"], 1)  # TINY is too short
        self.assertGreater(report["columns"], 60)
        self.assertEqual(report["warmup_bars"], self.spec.warmup_bars())
        again = self.store.backfill(universe, self.spec)
        self.assertEqual(again["written"], 0)
        self.assertEqual(again["reused"], 3)

    def test_an_interrupted_write_leaves_no_readable_half_file(self):
        path = self.store.path_for("AAA", self.spec)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".partial")
        partial.write_bytes(b"half a file")
        self.assertIsNone(self.store.load("AAA", self.bars, self.spec))
        self.store.save("AAA", self.bars, panel_for(self.bars, self.spec), self.spec)
        self.assertIsNotNone(self.store.load("AAA", self.bars, self.spec))

    def test_nan_survives_the_round_trip_as_none(self):
        columns = {"x": array("d", [float("nan"), 1.0])}
        from quantlab_backtester.indicators import panel_from_columns

        panel = panel_from_columns(["x"], columns, 2, 0, self.spec.cache_key())
        self.store.save("ZZZ", self.bars[:2], panel, self.spec)
        loaded = self.store.load("ZZZ", self.bars[:2], self.spec)
        self.assertIsNone(loaded.at(0)["x"])
        self.assertEqual(loaded.at(1)["x"], 1.0)


if __name__ == "__main__":
    unittest.main()
