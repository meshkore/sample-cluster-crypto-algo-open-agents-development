"""The rule grammar: three-valued logic, causality, and refusing to say nothing.

This is the piece that lets the loop invent mechanisms rather than tune them, so
the failure that matters is not "a rule is wrong" -- a wrong rule loses money and
the objective rejects it. The failure that matters is a rule that LOOKS like a
mechanism and is a constant, or one that reads an unfilled column as zero.

All sabotage-verified.
"""

import random
import unittest

from quantlab_trading import grammar as g
from quantlab_trading.regime_system import EvolvedBranch, SymbolState

COL = lambda name: {"t": "col", "name": name}  # noqa: E731
PX = lambda name: {"t": "px", "name": name}  # noqa: E731
NUM = lambda v: {"t": "num", "v": v}  # noqa: E731

CANDLE = {"open": 100.0, "high": 106.0, "low": 99.0, "close": 105.0, "volume": 5_000.0}
ROW = {
    "sma_50": 100.0,
    "sma_200": 90.0,
    "adx": 30.0,
    "rsi_14": 60.0,
    "volume_sma_20": 1_000.0,
}
PREV_ROW = {"sma_50": 100.0, "sma_200": 101.0, "adx": 10.0, "rsi_14": 40.0}


class TestEvaluation(unittest.TestCase):
    def test_an_unfilled_column_is_unknown_and_not_false(self):
        """Sabotage: `return None if value is None else float(value)` becomes
        `float(value or 0.0)`. An unfilled 200-day average then reads as zero,
        every price is above it, and a warm-up bar becomes a trade signal --
        which this laboratory has done in two separate places."""
        rule = {"t": "gt", "a": PX("close"), "b": COL("sma_100")}
        self.assertIsNone(g.evaluate(rule, CANDLE, ROW, PREV_ROW, CANDLE))

    def test_unknown_propagates_through_and_but_false_still_wins(self):
        known_false = {"t": "gt", "a": NUM(1.0), "b": NUM(2.0)}
        unknown = {"t": "gt", "a": COL("sma_100"), "b": NUM(1.0)}
        # False AND unknown is False: no value of the unknown term can rescue it.
        self.assertIs(
            g.evaluate(
                {"t": "and", "xs": [known_false, unknown]},
                CANDLE,
                ROW,
                PREV_ROW,
                CANDLE,
            ),
            False,
        )
        # True AND unknown is genuinely unknown.
        known_true = {"t": "gt", "a": NUM(2.0), "b": NUM(1.0)}
        self.assertIsNone(
            g.evaluate(
                {"t": "and", "xs": [known_true, unknown]}, CANDLE, ROW, PREV_ROW, CANDLE
            )
        )

    def test_unknown_propagates_through_or_but_true_still_wins(self):
        known_true = {"t": "gt", "a": NUM(2.0), "b": NUM(1.0)}
        unknown = {"t": "gt", "a": COL("sma_100"), "b": NUM(1.0)}
        self.assertIs(
            g.evaluate(
                {"t": "or", "xs": [known_true, unknown]}, CANDLE, ROW, PREV_ROW, CANDLE
            ),
            True,
        )

    def test_a_crossing_reads_both_bars(self):
        """A crossing is a change, and a served column is a level.

        Sabotage: evaluate `cross_up` as a plain `gt` on the current bar. The
        second assertion -- already above, no crossing -- then returns True and
        the rule re-enters a position on every bar it is already in.
        """
        crossing = {"t": "cross_up", "a": COL("sma_50"), "b": COL("sma_200")}
        self.assertIs(g.evaluate(crossing, CANDLE, ROW, PREV_ROW, CANDLE), True)
        already_above = {"sma_50": 100.0, "sma_200": 95.0}
        self.assertIs(g.evaluate(crossing, CANDLE, ROW, already_above, CANDLE), False)

    def test_a_band_around_a_level_is_expressible(self):
        rule = {
            "t": "gt",
            "a": PX("close"),
            "b": {"t": "mul", "a": COL("sma_50"), "b": NUM(1.02)},
        }
        self.assertIs(g.evaluate(rule, CANDLE, ROW, PREV_ROW, CANDLE), True)
        self.assertIs(
            g.evaluate(
                {
                    "t": "gt",
                    "a": PX("close"),
                    "b": {"t": "mul", "a": COL("sma_50"), "b": NUM(1.20)},
                },
                CANDLE,
                ROW,
                PREV_ROW,
                CANDLE,
            ),
            False,
        )

    def test_an_unknown_column_is_refused_rather_than_ignored(self):
        with self.assertRaises(g.GrammarError):
            g.evaluate(
                {"t": "gt", "a": COL("moon_phase"), "b": NUM(1.0)},
                CANDLE,
                ROW,
                PREV_ROW,
                CANDLE,
            )

    def test_a_malformed_node_is_refused(self):
        for broken in ({"t": "wat"}, {"t": "and", "xs": []}, "not a node"):
            with self.assertRaises(g.GrammarError):
                g.evaluate(broken, CANDLE, ROW, PREV_ROW, CANDLE)


class TestSayingNothing(unittest.TestCase):
    def test_a_field_compared_with_itself_is_rejected(self):
        """`low > low` is a constant. The first generator produced it and each
        one costs four full backtests to discover it says nothing."""
        self.assertIsNotNone(g.degenerate({"t": "gt", "a": PX("low"), "b": PX("low")}))
        with self.assertRaises(g.GrammarError):
            g.validate({"t": "gt", "a": PX("low"), "b": PX("low")})

    def test_a_field_against_a_multiple_of_itself_is_rejected(self):
        """`high > high*0.998` is also a constant, wearing a comparison's
        clothes. Sabotage: drop the `mul` arm of `degenerate` and this passes."""
        rule = {
            "t": "gt",
            "a": PX("high"),
            "b": {"t": "mul", "a": PX("high"), "b": NUM(0.998)},
        }
        self.assertIsNotNone(g.degenerate(rule))
        with self.assertRaises(g.GrammarError):
            g.validate(rule)

    def test_two_parts_of_the_same_bar_are_rejected(self):
        """`high > close` is true on every candle but a doji, and `high crosses
        above low` can never fire at all -- low <= close <= high is what a bar
        IS, not something the market does. All three of these reached the ledger
        as invented rules before the guard existed.

        Sabotage: drop the OHLC arm of `degenerate` and every one of these
        passes as a signal.
        """
        for a, b, kind in (
            ("high", "close", "gt"),
            ("high", "close", "cross_down"),
            ("high", "low", "cross_up"),
            ("low", "open", "lt"),
        ):
            rule = {"t": kind, "a": PX(a), "b": PX(b)}
            self.assertIsNotNone(g.degenerate(rule), f"{a} {kind} {b}")
            with self.assertRaises(g.GrammarError):
                g.validate(rule)

    def test_the_open_against_the_close_stays_legal(self):
        """`close > open` is an up candle -- the oldest signal there is, and the
        one pair in a bar that is unbounded in both directions. The first
        version of the same-bar guard rejected the whole of OHLC and took this
        with it.

        Sabotage: drop the BAR_BOUNDS condition and every one of these fails.
        """
        for a, b, kind in (
            ("close", "open", "gt"),
            ("open", "close", "gt"),
            ("close", "open", "cross_up"),
            ("close", "open", "lt"),
        ):
            rule = {"t": kind, "a": PX(a), "b": PX(b)}
            self.assertIsNone(g.degenerate(rule), f"{a} {kind} {b}")
            g.validate(rule)

    def test_a_bar_component_against_an_indicator_is_still_allowed(self):
        """The guard must not cost the grammar its most ordinary comparison:
        `close > sma_50` is the shape of nearly every trend rule there is."""
        for column in ("sma_50", "ema_21", "bb_upper", "keltner_mid"):
            rule = {"t": "gt", "a": PX("close"), "b": COL(column)}
            self.assertIsNone(g.degenerate(rule), f"close > {column}")

    def test_a_degenerate_term_buried_in_a_tree_is_still_found(self):
        rule = {
            "t": "and",
            "xs": [
                {"t": "gt", "a": PX("close"), "b": COL("sma_50")},
                {
                    "t": "or",
                    "xs": [
                        {"t": "lt", "a": COL("adx"), "b": NUM(20.0)},
                        {"t": "gt", "a": PX("low"), "b": PX("low")},
                    ],
                },
            ],
        }
        self.assertIsNotNone(g.degenerate(rule))

    def test_an_oversized_rule_is_rejected(self):
        deep = {"t": "gt", "a": PX("close"), "b": COL("sma_50")}
        for _ in range(30):
            deep = {
                "t": "and",
                "xs": [deep, {"t": "gt", "a": COL("adx"), "b": NUM(20)}],
            }
        with self.assertRaises(g.GrammarError):
            g.validate(deep)

    def test_a_real_mechanism_survives_validation(self):
        """The open-gate control. If `validate` rejected everything, every test
        above would pass and the grammar would be unable to express anything."""
        rule = {
            "t": "and",
            "xs": [
                {"t": "gt", "a": PX("close"), "b": COL("sma_200")},
                {"t": "gt", "a": COL("adx"), "b": NUM(25.0)},
                {"t": "cross_up", "a": COL("sma_50"), "b": COL("sma_200")},
            ],
        }
        self.assertIsNone(g.degenerate(rule))
        self.assertIs(g.validate(rule), rule)


class TestGeneration(unittest.TestCase):
    def test_everything_generated_is_valid_and_says_something(self):
        rng = random.Random(11)
        for _ in range(400):
            rule = g.random_rule(rng, depth=2)
            g.validate(rule)  # raises on degenerate, oversized or unknown

    def test_mutation_keeps_the_tree_valid(self):
        """Sabotage: let `mutate_rule` graft a value node where a predicate
        belongs. Evaluation then raises for every descendant and the whole
        lineage is dead."""
        rng = random.Random(3)
        rule = g.random_rule(rng, depth=2)
        for _ in range(300):
            rule = g.mutate_rule(rule, rng, depth=2)
            g.evaluate(rule, CANDLE, ROW, PREV_ROW, CANDLE)  # must not raise

    def test_crossover_keeps_the_tree_evaluable(self):
        rng = random.Random(5)
        for _ in range(200):
            a, b = g.random_rule(rng, 2), g.random_rule(rng, 2)
            child = g.crossover_rules(a, b, rng)
            g.evaluate(child, CANDLE, ROW, PREV_ROW, CANDLE)

    def test_a_rule_reads_back_as_something_a_person_can_argue_with(self):
        rule = {
            "t": "and",
            "xs": [
                {"t": "gt", "a": PX("close"), "b": COL("sma_200")},
                {"t": "gt", "a": COL("adx"), "b": NUM(25.0)},
            ],
        }
        self.assertEqual(g.describe(rule), "(close > sma_200 AND adx > 25)")

    def test_generation_is_reproducible_from_its_seed(self):
        first = [g.describe(g.random_rule(random.Random(9), 2)) for _ in range(5)]
        second = [g.describe(g.random_rule(random.Random(9), 2)) for _ in range(5)]
        self.assertEqual(first, second)


class TestEvolvedBranch(unittest.TestCase):
    def _state(self):
        state = SymbolState()
        state.previous, state.previous_candle = PREV_ROW, CANDLE
        return state

    def test_it_enters_on_the_rule_and_exits_when_the_rule_fails(self):
        branch = EvolvedBranch(
            {"bear_entry_rule": {"t": "gt", "a": PX("close"), "b": COL("sma_50")}},
            "bear_",
        )
        state = self._state()
        self.assertTrue(branch.evaluate(CANDLE, ROW, state))
        cold = {**CANDLE, "close": 80.0}
        self.assertFalse(branch.evaluate(cold, ROW, state))

    def test_a_separate_exit_rule_is_honoured(self):
        branch = EvolvedBranch(
            {
                "bear_entry_rule": {"t": "gt", "a": PX("close"), "b": COL("sma_50")},
                "bear_exit_rule": {"t": "gt", "a": COL("rsi_14"), "b": NUM(70.0)},
            },
            "bear_",
        )
        state = self._state()
        self.assertTrue(branch.evaluate(CANDLE, ROW, state))
        # Entry no longer true, but the EXIT rule has not fired: still held.
        self.assertTrue(branch.evaluate({**CANDLE, "close": 80.0}, ROW, state))
        self.assertFalse(branch.evaluate(CANDLE, {**ROW, "rsi_14": 80.0}, state))

    def test_an_unknown_verdict_holds_the_position(self):
        """Sabotage: treat `None` as an exit. Every position is liquidated on
        any bar where a referenced window is still warming."""
        branch = EvolvedBranch(
            {"bear_entry_rule": {"t": "gt", "a": PX("close"), "b": COL("sma_50")}},
            "bear_",
        )
        state = self._state()
        self.assertTrue(branch.evaluate(CANDLE, ROW, state))
        self.assertTrue(branch.evaluate(CANDLE, {"sma_50": None}, state))

    def test_a_malformed_rule_stands_aside_rather_than_killing_the_run(self):
        branch = EvolvedBranch({"bear_entry_rule": {"t": "nonsense"}}, "bear_")
        self.assertFalse(branch.evaluate(CANDLE, ROW, self._state()))

    def test_no_rule_at_all_never_trades(self):
        self.assertFalse(
            EvolvedBranch({}, "bear_").evaluate(CANDLE, ROW, self._state())
        )


if __name__ == "__main__":
    unittest.main()
