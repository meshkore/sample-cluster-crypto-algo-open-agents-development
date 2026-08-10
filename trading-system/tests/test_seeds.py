"""The seed library: valid, reachable, and honest about what it is.

A seed the grammar refuses is worse than no seed at all -- it is discarded
silently, the population starts from noise, and the iteration reports that the
advisor suggested nothing. Every rule here has to survive the same validation
an invented one does.
"""

import unittest

from quantlab_trading import grammar, seeds


class TestTheSeedsAreLegal(unittest.TestCase):
    def test_every_seed_validates(self):
        for module, rules in seeds.BY_MODULE.items():
            for index, rule in enumerate(rules):
                with self.subTest(module=module, index=index):
                    grammar.validate(rule)

    def test_no_seed_is_degenerate(self):
        """Sabotage: seed `high > low`. The grammar accepts it as a tree and
        `degenerate` is the only thing that catches that it says nothing."""
        for module, rules in seeds.BY_MODULE.items():
            for index, rule in enumerate(rules):
                with self.subTest(module=module, index=index):
                    self.assertIsNone(grammar.degenerate(rule), grammar.describe(rule))

    def test_every_seed_fits_the_size_limit(self):
        """A seed larger than the search's own cap could never be bred from."""
        for rules in seeds.BY_MODULE.values():
            for rule in rules:
                self.assertLessEqual(grammar.size(rule), grammar.MAXIMUM_SIZE)

    def test_the_seeds_only_name_columns_that_exist(self):
        for rules in seeds.BY_MODULE.values():
            for rule in rules:
                self.assertEqual(
                    grammar.columns_used(rule) - grammar.KNOWN_COLUMNS, set()
                )


class TestWhatEachModuleGets(unittest.TestCase):
    def test_the_bear_module_gets_the_bounce_family(self):
        """The operator asked for bear-market bounce trading, and the measured
        survivor of the falling fold is the capitulation reversal. It has to be
        in the pool the bear module breeds from."""
        described = [grammar.describe(r) for r in seeds.seeds_for("BEAR")]
        self.assertTrue(
            any("volume_ratio_20" in text and "return_1" in text for text in described),
            described,
        )

    def test_a_module_that_moves_numbers_gets_no_rule_seeds(self):
        """DETECTOR and POLICY have no rule slots. Handing them a tree would
        put a rule where the search has nowhere to place it."""
        self.assertEqual(seeds.seeds_for("DETECTOR"), [])
        self.assertEqual(seeds.seeds_for("POLICY"), [])

    def test_an_unknown_module_is_empty_rather_than_an_error(self):
        self.assertEqual(seeds.seeds_for("NONSENSE"), [])

    def test_the_limit_is_honoured(self):
        self.assertLessEqual(len(seeds.seeds_for("BEAR", limit=2)), 2)


if __name__ == "__main__":
    unittest.main()
