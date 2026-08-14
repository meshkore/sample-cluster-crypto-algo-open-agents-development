"""The market gate: stand aside while the market as a whole is deeply down.

A long-only book has no way to express "the trend is against me" except by not
being in the market. `trend_ma_days` asks that question per asset, and every
asset can pass it individually on the way down; this asks it once about the
market and answers it the same way for all of them.

Measured in the fast screen on 2026-08-14 over twelve assets, with money
management fitted on training evidence alone: gating at 40% took the sealed 2026
median from -7.7% to -2.1% and the share of systems positive in 2026 from 5% to
23%, nine of 657 clearing the incumbent against zero without it.

The threshold is disclosed as tainted -- 0.40 was chosen by comparing sealed
distributions -- and `test_the_gate_is_off_by_default` is why that disclosure is
survivable: nothing inherits it silently.
"""

from __future__ import annotations

import datetime
import unittest

from quantlab_intraday.momentum import DEFAULTS, IntradayMomentumBrain


def _brain(**over):
    params = dict(DEFAULTS)
    params.update(over)
    return IntradayMomentumBrain(**params)


def _feed(brain, closes, symbol="BTCUSDT", start=datetime.date(2020, 1, 1)):
    """One close per DAY, because the trailing high is kept at daily resolution."""
    for offset, close in enumerate(closes):
        moment = datetime.datetime.combine(
            start + datetime.timedelta(days=offset), datetime.time()
        )
        brain._observe_market({symbol: {"close": close, "open": close}}, moment)


class TheGateWatchesTheMarketNotTheAsset(unittest.TestCase):
    def test_the_gate_is_off_by_default(self):
        """It carries a threshold chosen against sealed data, so no run may
        inherit it without saying so on the command line."""
        self.assertEqual(DEFAULTS["market_gate_drawdown"], 1.0)
        self.assertTrue(_brain()._market_allows())

    def test_a_market_far_below_its_peak_closes_the_book(self):
        brain = _brain(market_gate_drawdown=0.40)
        _feed(brain, [100.0, 120.0, 60.0])  # 50% off the peak

        self.assertFalse(brain._market_allows())

    def test_a_market_near_its_peak_leaves_it_open(self):
        brain = _brain(market_gate_drawdown=0.40)
        _feed(brain, [100.0, 120.0, 110.0])  # 8% off the peak

        self.assertTrue(brain._market_allows())

    def test_the_edge_is_inclusive_so_the_threshold_is_a_threshold(self):
        brain = _brain(market_gate_drawdown=0.40)
        _feed(brain, [100.0, 60.0])  # exactly 40% off

        self.assertTrue(brain._market_allows())

    def test_the_high_is_remembered_across_days(self):
        """A fall is measured from the high behind it. Recovering part of the way
        must not forgive the rest."""
        brain = _brain(market_gate_drawdown=0.40)
        _feed(brain, [100.0, 200.0, 150.0, 100.0])

        self.assertFalse(brain._market_allows(), "50% below the earlier high")

    def test_the_high_is_the_TRAILING_year_and_not_all_time(self):
        """An all-time high is seeded by whatever bar the run starts on, which
        made the gate a different rule in each half of a pair -- the first gated
        forward run was byte-identical to its ungated control."""
        brain = _brain(market_gate_drawdown=0.40, market_peak_days=10)
        _feed(brain, [1000.0] + [500.0] * 20)

        self.assertTrue(
            brain._market_allows(), "the 1000 high aged out of the trailing window"
        )

    def test_the_gate_reads_the_market_symbol_and_not_whatever_arrives(self):
        """With twelve symbols in the basket, reading the wrong series would make
        the gate a per-asset filter wearing a market's name."""
        brain = _brain(market_gate_drawdown=0.40, market_symbol="BTCUSDT")
        _feed(brain, [100.0, 95.0])
        brain._observe_market({"DOGEUSDT": {"close": 1.0}})

        self.assertTrue(brain._market_allows(), "DOGE is not the market")

    def test_a_missing_market_candle_leaves_the_state_alone(self):
        brain = _brain(market_gate_drawdown=0.40)
        _feed(brain, [100.0, 90.0])
        brain._observe_market({"ETHUSDT": {"close": 1.0}})

        self.assertEqual(brain.market_close, 90.0)

    def test_warm_up_passes_rather_than_refusing(self):
        """Unlike `_above_trend`, which refuses until its window fills. A peak
        seeded from the first bar IS that bar, so the drawdown reads zero and is
        informative immediately -- there is no uninformed period to protect."""
        self.assertTrue(_brain(market_gate_drawdown=0.40)._market_allows())

    def test_the_refusal_is_counted_under_its_own_name(self):
        """The refusal ledger is how a run explains a book that stood still, and
        a gate folded into another reason's count is invisible."""
        brain = _brain(market_gate_drawdown=0.40)
        brain._refuse("market_gate")

        self.assertEqual(brain.refusals["market_gate"], 1)


if __name__ == "__main__":
    unittest.main()
