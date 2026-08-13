"""This market has no closing bell, so nothing closes a position by the clock.

The intraday momentum rule as published closes everything at the end of the
session, and that is right for equities: the bell forces the exit and an
overnight hold carries gap risk nobody can manage. Crypto trades continuously.
Selling at 23:55 sells a position that has not finished doing what it was opened
to do, and pays a full round trip to reopen the same idea in the morning.

It defaulted to ON, and it changed what runs measured without appearing in any
result. `itsm-h08` was published at +6.07% in the sealed window against the
incumbent's +5.05% while carrying this flag the other way -- so it was never a
comparison of entry hours. With a daily close the three-day holding cap can never
be reached, and a three-day drift bet became a one-day trade that turned over 824
times and paid 74.9% of capital in toll.

A mixed book is the intended behaviour: some positions close the same day, some
run for days. The cost of the long ones is that they hold a slot and their
capital until they close, which is a capital-allocation question and not a reason
to force an exit by the clock.

Sabotage-verified: flipping the default back to True turns the first two red.
"""

from __future__ import annotations

import unittest

from quantlab_intraday.momentum import DEFAULTS
from quantlab_trading.brains import build


class NothingClosesBecauseOfTheClock(unittest.TestCase):
    def test_the_default_is_off(self):
        """The load-bearing assertion. Every run that does not name this flag
        inherits it, and the two that did not were measuring another strategy."""
        self.assertFalse(DEFAULTS["exit_end_of_day"])

    def test_a_brain_built_without_the_flag_holds_overnight(self):
        brain = build("intraday-momentum", bars_per_day=288)

        self.assertFalse(brain.parameters()["exit_end_of_day"])

    def test_the_holding_cap_is_reachable(self):
        """The two settings interact, and that interaction is the whole bug. A
        daily close makes any `maximum_holding_bars` above one day unreachable,
        so the run silently measures a one-day rule while reporting a three-day
        genome."""
        brain = build("intraday-momentum", bars_per_day=288, maximum_holding_bars=864)
        parameters = brain.parameters()

        self.assertGreater(parameters["maximum_holding_bars"], 288)
        self.assertFalse(
            parameters["exit_end_of_day"],
            "a daily close would make this holding period unreachable",
        )

    def test_it_can_still_be_asked_for_explicitly(self):
        """Removing the capability would be the opposite mistake: the equity
        version of the rule is a real comparison worth being able to run."""
        brain = build("intraday-momentum", bars_per_day=288, exit_end_of_day=True)

        self.assertTrue(brain.parameters()["exit_end_of_day"])


if __name__ == "__main__":
    unittest.main()
