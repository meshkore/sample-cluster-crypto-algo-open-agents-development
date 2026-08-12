"""The signal study itself: no lookahead, and error bars that are not inflated.

Two properties are worth a test rather than a comment.

**The entry price is the NEXT open.** A decision is made on a closed bar and
filled at the following one, so a study that measures from the closing price it
just looked at hands itself the move it is trying to detect. That is the single
most common way an intraday backtest lies, and it does not announce itself --
it simply reports a better number.

**Overlapping observations do not count as independent ones.** At a 288-bar
horizon on 5-minute candles, one day's move is counted by up to 288 nearly
identical observations, and the standard error then divides by a sample size
that does not exist. That is not hypothetical: it printed t = 6.7 on a mean
that thins to a fraction of it. `scan` therefore reports both, and this file
checks the thinning actually thins.

Sabotage-verified: entry from `close` fails the first test; returning `signal`
in place of `independent` fails the second.
"""

from datetime import datetime, timedelta, timezone
import unittest

from quantlab_backtester.models import Bar
from quantlab_intraday import edge

UTC = timezone.utc
STEP = timedelta(minutes=15)
START = datetime(2021, 1, 1, tzinfo=UTC)

# Every gate wide open, so every warm bar becomes an observation and the
# arithmetic can be checked directly rather than through a filter.
OPEN_GATES = {
    "minimum_displacement_atr": -99.0,
    "maximum_ibs": 1.0,
    "maximum_rsi": 100.0,
    "cost_multiple": -99.0,
    "volatility_quantile": 1.0,
    "minimum_daily_turnover": 0.0,
}


def _tape(count=600):
    """A deterministic zigzag with a non-zero range on every bar.

    The open of each bar is deliberately NOT the close of the previous one:
    a study that entered at the close would be measuring from a price that was
    never available, and the gap is what makes the difference visible.
    """
    bars = []
    for index in range(count):
        base = 100.0 + (index % 7) - (index % 3)
        close = base * (1.004 if index % 2 else 0.996)
        bars.append(
            Bar(
                timestamp=START + STEP * index,
                open=base,
                high=max(base, close) * 1.001,
                low=min(base, close) * 0.999,
                close=close,
                volume=10_000.0,
            )
        )
    return {"SYNTH": bars}


class NoLookaheadTest(unittest.TestCase):
    def test_the_entry_is_the_next_open_not_the_close_just_seen(self):
        bars = _tape()["SYNTH"]
        report = edge.scan({"SYNTH": bars}, horizons=(1,), **OPEN_GATES)
        row = report["signal"][0]
        self.assertGreater(row["n"], 100, "the fixture stopped producing signals")

        # Rebuild what the study should have recorded, from the bars alone.
        from quantlab_backtester.indicators import IndicatorSpec, panel_for

        warmup = panel_for(bars, IndicatorSpec()).warmup_bars
        expected = [
            bars[index + 2].open / bars[index + 1].open - 1
            for index in range(warmup, len(bars) - 2)
        ]
        wanted = sum(expected) / len(expected)
        self.assertAlmostEqual(row["gross_mean"], wanted, places=9)

        # And the number it must NOT be: entry at the close it just saw.
        from_close = [
            bars[index + 1].open / bars[index].close - 1
            for index in range(warmup, len(bars) - 2)
        ]
        self.assertNotAlmostEqual(
            row["gross_mean"], sum(from_close) / len(from_close), places=6
        )

    def test_the_baseline_is_measured_the_same_way(self):
        """Otherwise the signal is compared against a differently-built number
        and the comparison that decides everything is meaningless."""
        bars = _tape()["SYNTH"]
        report = edge.scan({"SYNTH": bars}, horizons=(1,), **OPEN_GATES)
        self.assertAlmostEqual(
            report["signal"][0]["gross_mean"],
            report["baseline"][0]["gross_mean"],
            places=9,
            msg="with every gate open the signal IS the baseline",
        )


class IndependenceTest(unittest.TestCase):
    def test_overlapping_windows_are_thinned_before_the_error_bar(self):
        report = edge.scan(_tape(), horizons=(1, 32), **OPEN_GATES)
        rows = {row["horizon"]: row for row in report["signal"]}
        thinned = {row["horizon"]: row for row in report["independent"]}

        # At a one-bar horizon nothing overlaps, so nothing is dropped.
        self.assertEqual(thinned[1]["n"], rows[1]["n"])
        # At 32 bars, one observation in 32 survives.
        self.assertLess(thinned[32]["n"], rows[32]["n"] / 8)
        self.assertGreater(thinned[32]["n"], 0)

    def test_thinning_shrinks_the_t(self):
        report = edge.scan(_tape(), horizons=(32,), **OPEN_GATES)
        full = report["signal"][0]
        thin = report["independent"][0]
        self.assertLess(abs(thin["net_t"]), abs(full["net_t"]))

    def test_the_survivors_are_spaced_a_full_horizon_apart(self):
        """The count is what the spacing rule implies, and nothing else.

        Note what is NOT asserted: that the thinned mean matches the full one.
        A subsample has its own sampling error and may land anywhere inside it
        -- on this deliberately periodic fixture, taking every 32nd bar lands
        on one phase of the cycle and the mean moves a long way. That is the
        estimate being noisier, which is exactly the honesty being bought, and
        an earlier version of this test asserted the opposite and was wrong.
        """
        report = edge.scan(_tape(), horizons=(32,), **OPEN_GATES)
        full = report["signal"][0]["n"]
        thin = report["independent"][0]["n"]
        # Every bar qualifies here, so the picks are exactly every 32nd one.
        self.assertLessEqual(abs(thin - full / 32), 1.0)


if __name__ == "__main__":
    unittest.main()
