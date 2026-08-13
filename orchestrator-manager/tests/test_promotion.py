"""The promotion rule: win in both periods, or do not take the seat.

Written because a candidate was announced as the record on its sealed figure
alone. `itsm-h04` returned +10.77% in 2026 against the incumbent's +5.05% and was
published as the winner while its training half had breached the drawdown mandate
and stopped in JULY 2021 -- three and a half years into an eight-year era, with no
evidence whatever for the four and a half years after it.

The load-bearing test is `test_a_candidate_that_dies_in_2021_is_not_the_record`.
Everything else here guards the edges of that.

Sabotage-verified: dropping the survival clause makes that test pass a run that
aborted, and widening the tolerance past 15% admits a candidate the operator's
rule excludes.
"""

from __future__ import annotations

import unittest

from quantlab_manager.promotion import TRAINING_TOLERANCE, judge

INCUMBENT_SEALED = 0.0505
BEST_TRAINING = 1.4929  # generation 5, the only run that survives the era


def _training(**over):
    row = {
        "return_pct": 1.4929,
        "status": "complete",
        "aborted": 0,
        "abort_reason": None,
        "last_active_timestamp": "2025-12-15T00:00:00+00:00",
    }
    row.update(over)
    return row


def _sealed(return_pct=0.10):
    return {"return_pct": return_pct}


class WinningInBothPeriods(unittest.TestCase):
    def test_a_candidate_that_dies_in_2021_is_not_the_record(self):
        """THE test. itsm-h04 exactly: best sealed figure in the laboratory,
        training aborted on 2021-07-19."""
        verdict = judge(
            _training(
                return_pct=0.9163,
                status="stopped",
                aborted=1,
                abort_reason="drawdown mandate breached",
                last_active_timestamp="2021-07-19T00:00:00+00:00",
            ),
            _sealed(0.1077),
            INCUMBENT_SEALED,
            BEST_TRAINING,
        )

        self.assertFalse(verdict.promotable)
        self.assertFalse(verdict.survives_training)
        self.assertTrue(verdict.beats_incumbent, "it did win the sealed window")

    def test_surviving_the_era_but_losing_2026_is_not_enough_either(self):
        """Generation 5. The other half of the rule, and the reason it is a rule
        rather than a preference: a system that survives eight years and cannot
        beat the record forward has not earned the seat."""
        verdict = judge(_training(), _sealed(-0.0103), INCUMBENT_SEALED, BEST_TRAINING)

        self.assertFalse(verdict.promotable)
        self.assertTrue(verdict.survives_training)
        self.assertFalse(verdict.beats_incumbent)

    def test_winning_both_is_promotable(self):
        """The positive case. Without this every other test here passes for a
        rule that promotes nothing, which is not a rule."""
        verdict = judge(_training(), _sealed(0.12), INCUMBENT_SEALED, BEST_TRAINING)

        self.assertTrue(verdict.promotable, verdict.reasons)

    def test_the_tolerance_admits_a_slightly_weaker_training_half(self):
        """15%: near the previous winner is good enough when the rest is better.
        Demanding the maximum on both axes selects for a curve that fits both."""
        just_inside = BEST_TRAINING * (1 - TRAINING_TOLERANCE) + 0.001
        verdict = judge(
            _training(return_pct=just_inside),
            _sealed(0.12),
            INCUMBENT_SEALED,
            BEST_TRAINING,
        )

        self.assertTrue(verdict.training_within_tolerance, verdict.reasons)

    def test_but_not_a_much_weaker_one(self):
        outside = BEST_TRAINING * (1 - TRAINING_TOLERANCE) - 0.001
        verdict = judge(
            _training(return_pct=outside),
            _sealed(0.12),
            INCUMBENT_SEALED,
            BEST_TRAINING,
        )

        self.assertFalse(verdict.training_within_tolerance)
        self.assertFalse(verdict.promotable)

    def test_a_run_that_goes_quiet_years_early_has_not_survived(self):
        """A status column can say `complete` while the equity curve stopped
        moving in 2022, which is the same missing evidence wearing a better word."""
        verdict = judge(
            _training(last_active_timestamp="2022-06-01T00:00:00+00:00"),
            _sealed(0.12),
            INCUMBENT_SEALED,
            BEST_TRAINING,
        )

        self.assertFalse(verdict.survives_training)

    def test_stopping_a_few_weeks_early_is_still_surviving(self):
        """The grace exists so a run that closes its last position in November is
        not failed for a technicality. It is bounded so 2021 can never qualify."""
        verdict = judge(
            _training(last_active_timestamp="2025-10-01T00:00:00+00:00"),
            _sealed(0.12),
            INCUMBENT_SEALED,
            BEST_TRAINING,
        )

        self.assertTrue(verdict.survives_training)

    def test_matching_the_incumbent_is_not_beating_it(self):
        verdict = judge(
            _training(), _sealed(INCUMBENT_SEALED), INCUMBENT_SEALED, BEST_TRAINING
        )

        self.assertFalse(verdict.beats_incumbent)

    def test_every_failure_is_explained(self):
        """A verdict a reader cannot act on is a verdict that gets overridden."""
        verdict = judge(
            _training(
                return_pct=0.20,
                status="stopped",
                aborted=1,
                last_active_timestamp="2021-07-19T00:00:00+00:00",
            ),
            _sealed(-0.05),
            INCUMBENT_SEALED,
            BEST_TRAINING,
        )

        self.assertEqual(len(verdict.reasons), 3)
        self.assertFalse(verdict.promotable)


if __name__ == "__main__":
    unittest.main()
