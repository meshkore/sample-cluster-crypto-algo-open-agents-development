"""Generation 5's filter: it vetoes entries, and it fails in the loud direction.

The load-bearing test is `test_an_approved_entry_still_reaches_the_book`. Every
other assertion here is of the form "it did not trade", and a brain that never
trades passes all of them -- which in this repository is a bug that has shipped
twice. A filter makes that failure mode much more likely, not less: a wrong key
format, a missing table or an unparsed timestamp all produce a run that refuses
everything and reports it as no signal.

Sabotage-verified. Each test names the mutation it was checked against.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from quantlab_system05.strategy import CHAMPION, MetaLabelledITSM
from quantlab_trading.brains import build

UTC = timezone.utc
BAR = datetime(2026, 3, 2, 6, 0, tzinfo=UTC)


def _table(rows: list[tuple[str, datetime, float]]) -> str:
    """A verdict file on disk, keyed the way `quantlab_ml.meta` writes it."""
    directory = TemporaryDirectory()
    _table.keep.append(directory)  # type: ignore[attr-defined]
    path = Path(directory.name) / "verdicts.json"
    path.write_text(
        json.dumps(
            {
                "table": [
                    {"symbol": s, "timestamp": str(t), "value": v, "source": "fold-0"}
                    for s, t, v in rows
                ]
            }
        )
    )
    return str(path)


_table.keep = []  # type: ignore[attr-defined]


class _Primary:
    """A stand-in for the champion that asks to buy on the bar under test.

    The real momentum brain needs a warm 30-day window and a liquid tape to emit
    anything, so driving it here would test the fixture rather than the filter.
    What matters is that the filter sees a BUY and decides.
    """

    def __init__(self, orders):
        self._orders = orders
        self.policy = object()

    def decide(self, tick):
        from quantlab_trading.runner import Decision

        decision = Decision()
        decision.orders = [dict(order) for order in self._orders]
        return decision

    def parameters(self):
        return {"entry_rule": "itsm", "itsm_hour": 6}

    def diagnostics(self):
        return {"entries": 0}


def _brain(table: str, orders=None, **params) -> MetaLabelledITSM:
    brain = MetaLabelledITSM(verdict_table=table, **params)
    brain.primary = _Primary(
        orders
        if orders is not None
        else [
            {"symbol": "BTCUSDT", "side": "BUY", "notional": 1000.0, "reason": "itsm"}
        ]
    )
    return brain


def _tick(moment=BAR):
    return {"timestamp": moment.isoformat(), "candles": {}, "indicators": {}}


class TheFilterDecides(unittest.TestCase):
    def test_an_approved_entry_still_reaches_the_book(self):
        """THE load-bearing test. Sabotage: invert the comparison to `value <
        self.margin` and this is the test that catches it."""
        brain = _brain(_table([("BTCUSDT", BAR, 0.004)]))

        decision = brain.decide(_tick())

        self.assertEqual(len(decision.orders), 1)
        self.assertEqual(brain.approved, 1)
        self.assertIn("E[net]", decision.orders[0]["rationale"])

    def test_a_negative_expectation_is_vetoed(self):
        brain = _brain(_table([("BTCUSDT", BAR, -0.002)]))

        decision = brain.decide(_tick())

        self.assertEqual(decision.orders, [])
        self.assertEqual(brain.vetoed, 1)
        self.assertIn("filter refused", decision.note)

    def test_an_expectation_at_the_margin_is_not_enough(self):
        """`>` not `>=`: a trade expected to exactly break even pays the toll for
        nothing. Sabotage: `>=` turns this red."""
        brain = _brain(_table([("BTCUSDT", BAR, 0.0)]))

        self.assertEqual(brain.decide(_tick()).orders, [])

    def test_the_margin_is_honoured(self):
        brain = _brain(_table([("BTCUSDT", BAR, 0.004)]), verdict_margin=0.01)

        self.assertEqual(brain.decide(_tick()).orders, [])
        self.assertEqual(brain.vetoed, 1)

    def test_a_bar_the_table_never_judged_is_refused(self):
        """The whole reason the default is refusal: bars before the first
        walk-forward test block have no honest verdict, and letting them through
        would report the champion's results for those years and the filter's for
        the rest -- a card describing no strategy at all."""
        brain = _brain(_table([("BTCUSDT", datetime(2020, 1, 1, 6, tzinfo=UTC), 0.05)]))

        decision = brain.decide(_tick())

        self.assertEqual(decision.orders, [])
        self.assertEqual(brain.unjudged, 1)
        self.assertEqual(brain.vetoed, 0, "unjudged is not the same as vetoed")

    def test_a_verdict_for_another_symbol_does_not_leak(self):
        """Sabotage: keying the table on timestamp alone makes this red."""
        brain = _brain(_table([("ETHUSDT", BAR, 0.05)]))

        self.assertEqual(brain.decide(_tick()).orders, [])
        self.assertEqual(brain.unjudged, 1)

    def test_exits_are_never_filtered(self):
        """Vetoing a SELL would leave a position the primary believes it closed,
        with its stop and its timer already forgotten."""
        brain = _brain(
            _table([("BTCUSDT", BAR, -0.9)]),
            orders=[{"symbol": "BTCUSDT", "side": "SELL", "reason": "time_stop"}],
        )

        decision = brain.decide(_tick())

        self.assertEqual(len(decision.orders), 1)
        self.assertEqual(brain.vetoed, 0)

    def test_allow_unjudged_lets_the_silent_era_through(self):
        """Configurable for measuring the filter's effect on the covered era in
        isolation. Never for a published run."""
        brain = _brain(_table([]), allow_unjudged=True)

        self.assertEqual(len(brain.decide(_tick()).orders), 1)
        self.assertEqual(brain.unjudged, 1)

    def test_no_table_at_all_refuses_everything_rather_than_trading_blind(self):
        """The loud failure of the two. A brain that silently ignores a missing
        filter publishes the champion's genome under generation 5's name."""
        brain = _brain("")

        self.assertEqual(brain.decide(_tick()).orders, [])
        self.assertEqual(brain.verdicts, {})


class TheContractIsIntact(unittest.TestCase):
    def test_the_brain_is_registered_and_buildable(self):
        brain = build("meta-labelled-itsm", bars_per_day=288)

        for member in ("decide", "parameters", "diagnostics"):
            self.assertTrue(callable(getattr(brain, member)), member)
        self.assertTrue(hasattr(brain, "policy"))

    def test_the_primary_is_the_recorded_champion_genome(self):
        """The claim of this generation is "the champion plus a filter". If the
        primary drifts, the run measures two variables and says so nowhere."""
        brain = build("meta-labelled-itsm", bars_per_day=288)
        parameters = brain.parameters()

        for key, value in CHAMPION.items():
            self.assertEqual(parameters[key], value, key)

    def test_the_harness_may_still_set_trade_from_and_the_costs(self):
        """Freezing the genome must not freeze the fields every run sets, or the
        sealed half would trade the warm-up and both halves would share a
        cost model that is not the one they were charged."""
        brain = build(
            "meta-labelled-itsm",
            bars_per_day=288,
            trade_from="2026-01-01T00:00:00+00:00",
            commission_bps=10.0,
            slippage_bps=5.0,
        )
        parameters = brain.parameters()

        self.assertEqual(parameters["trade_from"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(parameters["commission_bps"], 10.0)

    def test_the_table_path_is_part_of_the_genome(self):
        """`pair_key` hashes the parameters. Two runs filtered by different
        tables are not two halves of one hypothesis, and the monitor would pair
        them anyway if the path were invisible."""
        path = _table([("BTCUSDT", BAR, 0.004)])
        brain = build("meta-labelled-itsm", bars_per_day=288, verdict_table=path)

        self.assertEqual(brain.parameters()["verdict_table"], path)

    def test_a_path_that_does_not_exist_fails_the_run(self):
        """Louder than an empty table, and deliberately so. A typo in the path
        would otherwise produce a run that refuses every entry and reports it as
        no signal -- which is exactly how a night was lost in this laboratory
        once already. An EMPTY path means "no filter configured" and is a
        different statement; that one is tested above."""
        with self.assertRaises(FileNotFoundError):
            build("meta-labelled-itsm", bars_per_day=288, verdict_table="a/b/none.json")

    def test_the_diagnostics_carry_the_filter_counts(self):
        brain = build("meta-labelled-itsm", bars_per_day=288)
        diagnostics = brain.diagnostics()

        for key in ("filter_approved", "filter_vetoed", "filter_unjudged"):
            self.assertIn(key, diagnostics)


if __name__ == "__main__":
    unittest.main()
