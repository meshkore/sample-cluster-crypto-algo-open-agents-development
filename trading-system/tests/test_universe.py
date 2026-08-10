"""The per-bar tradeable set.

Every test here carries an OPEN-GATE CONTROL where it can: a gate that admits
nothing passes every "it refused to buy" assertion, and this laboratory has
already shipped one silently-never-fires branch.

Sabotage-verified; each test names the change that breaks it.
"""

import unittest

from quantlab_trading.universe import TURNOVER_KEY, LiquidityGate


def _rows(**turnovers):
    return {symbol: {TURNOVER_KEY: value} for symbol, value in turnovers.items()}


class TestLiquidityGate(unittest.TestCase):
    def test_an_unconfigured_gate_admits_everything(self):
        """The default has to be harmless, or adding the field changes results."""
        gate = LiquidityGate()
        self.assertFalse(gate.enabled)
        self.assertEqual(
            gate.tradeable(_rows(AAA=1.0, BBB=2.0)), frozenset({"AAA", "BBB"})
        )

    def test_the_floor_excludes_what_cannot_be_filled(self):
        gate = LiquidityGate(minimum_turnover=10_000_000)
        # OPEN-GATE CONTROL: something above the floor must be admitted.
        admitted = gate.tradeable(_rows(BIG=50_000_000, SMALL=50_000))
        self.assertEqual(admitted, frozenset({"BIG"}))

    def test_the_cap_takes_the_most_liquid_not_the_first_seen(self):
        """Sabotage: drop the sort. A dict-order top-N is the alphabetical bug
        this whole change exists to remove, one layer down."""
        gate = LiquidityGate(maximum_assets=2)
        rows = _rows(AAA=1.0, BBB=500.0, CCC=300.0)
        self.assertEqual(gate.tradeable(rows), frozenset({"BBB", "CCC"}))

    def test_a_tie_resolves_the_same_way_everywhere(self):
        """A run has to be reproducible by a stranger, ties included."""
        gate = LiquidityGate(maximum_assets=1)
        rows = _rows(ZZZ=100.0, AAA=100.0)
        self.assertEqual(gate.tradeable(rows), frozenset({"AAA"}))

    def test_an_asset_with_no_turnover_yet_is_not_tradeable(self):
        """Inside its first twenty bars a listing has no trailing turnover.

        Sabotage: treat a missing value as 0.0 and compare with >=. With a zero
        floor that admits every freshly listed coin on its first day, which is
        the most expensive thing this laboratory could buy.
        """
        gate = LiquidityGate(minimum_turnover=1.0)
        rows = {"NEW": {}, "NONE": {TURNOVER_KEY: None}, "OLD": {TURNOVER_KEY: 5.0}}
        self.assertEqual(gate.tradeable(rows), frozenset({"OLD"}))

    def test_nan_never_ranks(self):
        """NaN fails every comparison silently, so it would sort to the top."""
        gate = LiquidityGate(maximum_assets=1)
        rows = {"NAN": {TURNOVER_KEY: float("nan")}, "REAL": {TURNOVER_KEY: 1.0}}
        self.assertEqual(gate.tradeable(rows), frozenset({"REAL"}))

    def test_membership_is_recomputed_from_each_bar(self):
        """The point of the whole design: no list, no rebalance date.

        A coin that lists mid-history enters on the bar it becomes liquid, and
        one whose turnover collapses leaves on the bar it does -- both without
        anybody maintaining anything.
        """
        gate = LiquidityGate(minimum_turnover=10_000_000)
        early = gate.tradeable(_rows(OLD=40_000_000))
        later = gate.tradeable(_rows(OLD=1_000_000, NEW=90_000_000))
        self.assertEqual(early, frozenset({"OLD"}))
        self.assertEqual(later, frozenset({"NEW"}))

    def test_it_reads_the_trailing_column_not_this_bar_volume(self):
        """`dollar_volume_20` is a trailing mean, which is what makes the gate
        causal. Pointing it at a raw volume column would make membership a
        function of the bar the decision is made on."""
        self.assertEqual(TURNOVER_KEY, "dollar_volume_20")
        self.assertEqual(LiquidityGate().turnover_key, TURNOVER_KEY)

    def test_it_describes_the_scope_it_ran_at(self):
        """A return without its universe is unreadable, and the universe here
        is a rule -- so the rule is what a run has to carry."""
        described = LiquidityGate(
            minimum_turnover=10_000_000, maximum_assets=100
        ).describe()
        self.assertEqual(described["minimum_turnover"], 10_000_000)
        self.assertEqual(described["maximum_assets"], 100)
        self.assertEqual(described["turnover_key"], TURNOVER_KEY)


if __name__ == "__main__":
    unittest.main()
