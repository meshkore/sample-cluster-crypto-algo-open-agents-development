"""The observation-table cache: exact on a hit, a miss on anything doubtful.

The table over eight years of five-minute bars costs minutes of arithmetic that
does not change between experiments -- it was rebuilt three times in one
afternoon while a single filter was being measured. Caching it is worth doing and
is also the most dangerous kind of optimisation in this package: a silently STALE
table would let every downstream number be computed correctly from the wrong data,
and nothing in any metric would say so.

So the tests come in two halves. That a hit reproduces the table exactly, field
for field -- including the timestamps, which are stored as integers and would
silently fail `barrier_sigma`'s equality match if they came back a microsecond
off. And that everything which could change the table changes the key: the
closes, the barriers, the volatility span, and the module's own version.

Sabotage-verified: dropping the closes from `fingerprint` turns the repaired-tape
test red, dropping `CACHE_VERSION` turns the version test red, and removing the
integer cast when timestamps are READ turns both timestamp tests red.

Worth recording how that last one was arrived at, because the first sabotage tried
was the wrong one. Storing the timestamps as drifted floats changed nothing --
every test stayed green -- since the read path casts back to `int` and repairs any
sub-second error. The guard is on the read, not the write, and the sabotage that
proves a test has to be the one that removes the guard that is actually load-
bearing. A test docstring naming a mutation it was never checked against is how a
bug gets certified.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from quantlab_backtester.indicators import IndicatorSpec
from quantlab_backtester.models import Bar
from quantlab_ml import dataset as md
from quantlab_ml.labels import Barriers

UTC = timezone.utc
STEP = timedelta(minutes=5)
BARRIERS = Barriers(target=2.0, stop=1.0, horizon=24)
SPAN = 48


def _bars(start: datetime, count: int, seed: int) -> list[Bar]:
    rng = np.random.default_rng(seed)
    price = 100.0
    out: list[Bar] = []
    for i in range(count):
        price *= float(np.exp(rng.normal(0.0, 0.004)))
        out.append(
            Bar(
                timestamp=start + i * STEP,
                open=price,
                high=price * 1.002,
                low=price * 0.998,
                close=price,
                volume=1_000.0 + i,
            )
        )
    return out


def _tape(count: int = 900):
    origin = datetime(2020, 1, 1, tzinfo=UTC)
    return {
        "AAA": _bars(origin, count, seed=1),
        "BBB": _bars(origin + timedelta(days=1), count, seed=2),
    }


def _build(bars, cache, **kwargs):
    return md.build(bars, BARRIERS, volatility_span=SPAN, cache=cache, **kwargs)


class AHitReproducesTheTable(unittest.TestCase):
    def test_the_second_build_is_identical_field_for_field(self):
        bars = _tape()
        with TemporaryDirectory() as directory:
            first = _build(bars, directory)
            files = list(Path(directory).glob("observations-*.npz"))
            second = _build(bars, directory)

        self.assertEqual(len(files), 1, "the first build must write exactly one file")
        np.testing.assert_array_equal(first.X, second.X)
        np.testing.assert_array_equal(first.y, second.y)
        np.testing.assert_array_equal(first.ret, second.ret)
        np.testing.assert_array_equal(first.ends_at, second.ends_at)
        np.testing.assert_array_equal(first.symbols, second.symbols)
        self.assertEqual(first.names, second.names)

    def test_the_timestamps_survive_the_round_trip_exactly(self):
        """`barrier_sigma` matches these against the bar's own timestamp with
        `==`. A microsecond of float drift leaves every row unpriced, and the run
        reports no signal rather than an error."""
        bars = _tape()
        with TemporaryDirectory() as directory:
            first = _build(bars, directory)
            second = _build(bars, directory)

        self.assertEqual(len(first.timestamps), len(second.timestamps))
        for a, b in zip(first.timestamps, second.timestamps):
            self.assertEqual(a, b)

    def test_a_cached_table_still_prices_its_volatility(self):
        """The end-to-end version of the test above: the cached table must work
        with the rest of the package, not merely compare equal to itself."""
        bars = _tape()
        with TemporaryDirectory() as directory:
            _build(bars, directory)
            cached = _build(bars, directory)

        sigma = md.barrier_sigma(cached, bars, horizon=BARRIERS.horizon, span=SPAN)

        self.assertTrue(np.isfinite(sigma).all(), "a cached row failed to find its bar")

    def test_the_meta_survives_including_the_sort_marker(self):
        bars = _tape()
        with TemporaryDirectory() as directory:
            _build(bars, directory)
            cached = _build(bars, directory)

        self.assertEqual(cached.meta.get("sorted_by"), "timestamp")
        self.assertEqual(cached.meta["barriers"]["horizon"], BARRIERS.horizon)


class ADoubtfulCacheIsAMiss(unittest.TestCase):
    def _key(self, bars, barriers=BARRIERS, span=SPAN):
        return md.fingerprint(bars, barriers, span, IndicatorSpec())

    def test_a_repaired_tape_changes_the_key(self):
        """THE load-bearing test. A cache keyed on metadata alone -- symbols,
        counts, first and last timestamp -- would serve the old table after the
        tape was refetched or a bad bar was corrected."""
        bars = _tape()
        before = self._key(bars)
        repaired = {symbol: list(rows) for symbol, rows in bars.items()}
        middle = repaired["AAA"][400]
        repaired["AAA"][400] = Bar(
            timestamp=middle.timestamp,
            open=middle.open,
            high=middle.high,
            low=middle.low,
            close=middle.close * 1.05,
            volume=middle.volume,
        )

        self.assertNotEqual(before, self._key(repaired))

    def test_different_barriers_change_the_key(self):
        bars = _tape()
        self.assertNotEqual(
            self._key(bars), self._key(bars, barriers=Barriers(3.0, 1.0, 24))
        )
        self.assertNotEqual(
            self._key(bars), self._key(bars, barriers=Barriers(2.0, 1.0, 48))
        )

    def test_a_different_volatility_span_changes_the_key(self):
        bars = _tape()
        self.assertNotEqual(self._key(bars), self._key(bars, span=SPAN * 2))

    def test_a_different_symbol_set_changes_the_key(self):
        bars = _tape()
        self.assertNotEqual(self._key(bars), self._key({"AAA": bars["AAA"]}))

    def test_the_same_tape_gives_the_same_key(self):
        """A key that changed between identical calls would make the cache dead
        weight while looking like it worked."""
        bars = _tape()
        self.assertEqual(self._key(bars), self._key(_tape()))

    def test_a_corrupt_file_is_rebuilt_rather_than_raised(self):
        """The cache is never load-bearing: deleting or breaking it may change
        how long a call takes and nothing else."""
        bars = _tape()
        with TemporaryDirectory() as directory:
            expected = _build(bars, directory)
            path = next(Path(directory).glob("observations-*.npz"))
            path.write_bytes(b"not an npz file at all")
            rebuilt = _build(bars, directory)

        np.testing.assert_array_equal(rebuilt.ends_at, expected.ends_at)

    def test_no_cache_directory_means_no_caching_and_no_error(self):
        bars = _tape()
        with TemporaryDirectory() as directory:
            md.build(bars, BARRIERS, volatility_span=SPAN, cache=None)

            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_the_version_is_part_of_the_key(self):
        """The time-sort fix landed the day before this cache existed. Serving a
        pre-sort table from disk would have quietly restored the bug it cured."""
        bars = _tape()
        before = self._key(bars)
        original = md.CACHE_VERSION
        try:
            md.CACHE_VERSION = original + 1
            after = self._key(bars)
        finally:
            md.CACHE_VERSION = original

        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
