"""The 2025-12-31 lock, and the splice that reaches past it deliberately.

The forward window is the only untouched evidence this project has. It lives in
its own file and the loader ignored it entirely, so the forward evaluation was
not merely discouraged -- it was impossible, and a 2026 window silently returned
a tape that stopped at the last research bar.

All sabotage-verified.
"""

from datetime import datetime, timedelta, timezone
import unittest

from quantlab_backtester.models import Bar
from quantlab_backtester.server import _splice

UTC = timezone.utc
START = datetime(2025, 12, 29, tzinfo=UTC)


def _bars(days, close, start=START):
    return [
        Bar(
            timestamp=start + timedelta(days=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1.0,
        )
        for i in range(days)
    ]


class TestSplice(unittest.TestCase):
    def test_the_forward_window_is_appended_in_order(self):
        research = _bars(3, 100.0)
        forward = _bars(2, 200.0, START + timedelta(days=3))
        spliced = _splice(research, forward)
        self.assertEqual(len(spliced), 5)
        self.assertEqual(
            [bar.timestamp for bar in spliced], sorted(b.timestamp for b in spliced)
        )
        self.assertEqual(spliced[-1].close, 200.0)

    def test_an_overlapping_bar_always_resolves_to_the_research_copy(self):
        """Sabotage: prefer the forward bar. The same window then returns
        different candles depending on which download ran last, and every
        `backtest_id` derived from a universe digest becomes unstable."""
        research = _bars(3, 100.0)
        forward = _bars(3, 999.0)  # same three timestamps, different prices
        spliced = _splice(research, forward)
        self.assertEqual(len(spliced), 3)
        self.assertTrue(all(bar.close == 100.0 for bar in spliced))

    def test_splicing_nothing_changes_nothing(self):
        research = _bars(4, 100.0)
        self.assertEqual(_splice(research, []), research)


if __name__ == "__main__":
    unittest.main()
