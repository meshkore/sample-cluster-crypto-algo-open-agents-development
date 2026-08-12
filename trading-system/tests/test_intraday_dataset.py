"""Windows, the era boundary, and the payload the session is handed.

The tests that matter here are the ones about the 2026 lock. A training window
that can see one post-lock bar is not a slightly wrong measurement, it is a
destroyed experiment -- the forward window is the only untouched evidence this
project has and it cannot be un-seen.

All sabotage-verified. Each test names the mutation it was checked against.
"""

from datetime import datetime, timedelta, timezone
import unittest

from quantlab_backtester.models import Bar
from quantlab_intraday.dataset import (
    LOCK,
    WARMUP_BARS,
    IntradayDataset,
    Window,
)

UTC = timezone.utc
STEP = timedelta(minutes=15)


def _bars(count, start=datetime(2020, 1, 1, tzinfo=UTC), price=100.0):
    return [
        Bar(
            timestamp=start + STEP * index,
            open=price,
            high=price * 1.002,
            low=price * 0.998,
            close=price,
            volume=1_000.0,
        )
        for index in range(count)
    ]


class BlockTest(unittest.TestCase):
    def test_blocks_are_ordered_non_overlapping_and_warm(self):
        bars = {"BTCUSDT": _bars(30_000)}
        windows = IntradayDataset.blocks(bars, count=4)
        self.assertEqual(len(windows), 4)
        for previous, window in zip(windows, windows[1:]):
            self.assertLess(previous.end, window.start)
        for window in windows:
            # Trading opens exactly `WARMUP_BARS` after the first served bar,
            # or the brain's own volatility state starts cold and no result
            # says so.
            self.assertEqual(window.trade_from, window.start + STEP * WARMUP_BARS)
            self.assertGreater(window.end, window.trade_from)

    def test_the_count_is_capped_by_the_history_available(self):
        """Sabotage: without the cap, eight windows over 12,000 bars overlap
        each other and the same tape is reported as eight measurements."""
        bars = {"BTCUSDT": _bars(12_000)}
        windows = IntradayDataset.blocks(bars, count=8)
        self.assertEqual(len(windows), 2)
        self.assertLess(windows[0].end, windows[1].start)

    def test_too_little_history_is_an_error_rather_than_a_short_window(self):
        with self.assertRaises(ValueError):
            IntradayDataset.blocks({"BTCUSDT": _bars(1_000)}, count=1)

    def test_the_timeline_is_the_union_the_session_will_build(self):
        early = _bars(10)
        late = _bars(10, start=datetime(2020, 1, 1, tzinfo=UTC) + STEP * 5)
        stamps = IntradayDataset.timeline({"A": early, "B": late})
        self.assertEqual(len(stamps), 15)
        self.assertEqual(stamps, sorted(set(stamps)))


class ForwardWindowTest(unittest.TestCase):
    def _split(self):
        lock = datetime.fromisoformat(LOCK)
        history = _bars(2_000, start=lock - STEP * 2_000)
        forward = _bars(1_000, start=lock)
        return lock, {"BTCUSDT": history + forward}

    def test_trading_opens_at_the_lock_and_warm_up_comes_from_before_it(self):
        lock, bars = self._split()
        window = IntradayDataset.forward_window(bars, lock)
        self.assertEqual(window.trade_from, lock)
        self.assertEqual(window.start, lock - STEP * WARMUP_BARS)
        self.assertLess(window.start, lock)

    def test_the_whole_sealed_window_is_served_not_a_sample_of_it(self):
        """Capping the forward window would mean choosing which part of the
        only untouched evidence in the project to look at."""
        lock, bars = self._split()
        window = IntradayDataset.forward_window(bars, lock)
        self.assertEqual(window.end, bars["BTCUSDT"][-1].timestamp)

    def test_a_series_that_never_reaches_the_lock_is_refused(self):
        """Sabotage: returning the last 5,000 research bars instead of raising
        reports a pre-2026 result as forward evidence."""
        lock = datetime.fromisoformat(LOCK)
        bars = {"BTCUSDT": _bars(2_000, start=lock - STEP * 2_000)}
        with self.assertRaises(ValueError):
            IntradayDataset.forward_window(bars, lock)

    def test_too_little_history_before_the_lock_is_refused(self):
        lock = datetime.fromisoformat(LOCK)
        bars = {"BTCUSDT": _bars(10, start=lock - STEP * 10) + _bars(100, start=lock)}
        with self.assertRaises(ValueError):
            IntradayDataset.forward_window(bars, lock)


class PayloadTest(unittest.TestCase):
    def _window(self, bars):
        stamps = [bar.timestamp for bar in bars]
        return Window(0, stamps[10], stamps[20], stamps[50], "test")

    def test_only_the_window_is_served(self):
        bars = _bars(100)
        window = self._window(bars)
        payload = IntradayDataset.candles_payload({"BTCUSDT": bars}, window)
        rows = payload["BTCUSDT"]
        self.assertEqual(len(rows), 41)
        self.assertEqual(rows[0]["timestamp"], window.start.isoformat())
        self.assertEqual(rows[-1]["timestamp"], window.end.isoformat())

    def test_a_symbol_that_did_not_exist_yet_is_dropped_not_padded(self):
        bars = _bars(100)
        window = self._window(bars)
        payload = IntradayDataset.candles_payload(
            {"BTCUSDT": bars, "LATE": bars[:11]}, window
        )
        self.assertEqual(sorted(payload), ["BTCUSDT"])

    def test_warmup_leaves_the_brain_something_to_warm_up_on(self):
        """If the indicator catalogue ever grows a window longer than the
        warm-up served here, the volatility veto silently starts cold."""
        self.assertLess(IntradayDataset.warmup_check(), WARMUP_BARS)


class PanelCacheTest(unittest.TestCase):
    """One cache root per window, because the store cannot key on the candles.

    Sabotage-verified: returning `self.indicators` from `store_for` — which is
    what this package did until two windows in one launch were measured — makes
    every one of these fail.
    """

    def _dataset(self):
        import tempfile

        self.addCleanup(lambda: None)
        return IntradayDataset(tempfile.mkdtemp(), LOCK, ["BTCUSDT"])

    def _window(self, index, start, end, label="block"):
        return Window(
            index=index,
            start=start,
            trade_from=start + STEP,
            end=end,
            label=label,
        )

    def test_two_windows_do_not_share_a_path(self):
        data = self._dataset()
        base = datetime(2020, 1, 1, tzinfo=UTC)
        first = self._window(0, base, base + STEP * 100)
        second = self._window(1, base + STEP * 200, base + STEP * 300)
        self.assertNotEqual(data.store_for(first).root, data.store_for(second).root)

    def test_the_same_window_is_the_same_store(self):
        """Or a second call would recompute the panel it just paid for."""
        data = self._dataset()
        base = datetime(2020, 1, 1, tzinfo=UTC)
        window = self._window(0, base, base + STEP * 100)
        self.assertIs(data.store_for(window), data.store_for(window))

    def test_the_label_alone_does_not_decide_the_path(self):
        """`block00-2020-01` names a different slice at a different
        `--window-bars`, and two slices sharing a path is the whole bug."""
        data = self._dataset()
        base = datetime(2020, 1, 1, tzinfo=UTC)
        short = self._window(0, base, base + STEP * 100, label="block00-2020-01")
        long = self._window(0, base, base + STEP * 5_000, label="block00-2020-01")
        self.assertNotEqual(data.store_for(short).root, data.store_for(long).root)

    def test_the_same_tape_under_two_names_is_one_cache(self):
        """`--phase training` and `--phase continuous` build the same eight-year
        window. Keying on the label would discard a warmed panel over a rename,
        which costs twenty-five minutes and looks like nothing at all."""
        data = self._dataset()
        base = datetime(2020, 1, 1, tzinfo=UTC)
        end = base + STEP * 5_000
        self.assertEqual(
            data.store_for(self._window(0, base, end, label="training")).root,
            data.store_for(self._window(7, base, end, label="continuous")).root,
        )

    def test_the_root_stays_under_the_interval_directory(self):
        data = self._dataset()
        base = datetime(2020, 1, 1, tzinfo=UTC)
        window = self._window(0, base, base + STEP * 100)
        self.assertEqual(data.store_for(window).root.parent, data.indicators.root)


if __name__ == "__main__":
    unittest.main()
