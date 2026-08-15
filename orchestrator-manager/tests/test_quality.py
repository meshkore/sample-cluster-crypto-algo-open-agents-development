"""Scoring a curve by what it does to someone who bought at the worst moment.

Written because the champion's equity curve was flat for three years, earned
everything in the 2021 bull run, gave 24% back from its peak, spent four
consecutive months losing, and ended below its own high -- and had the best final
return on the board. Every score used here ranked on final return, which asks
only what happened to the person who bought on day one.

`test_the_champions_shape_scores_below_a_modest_steady_one` is the load-bearing
test: the spike curve has THREE TIMES the final return of the steady one and must
still lose.
"""

from __future__ import annotations

import math
import unittest

from quantlab_manager.quality import (
    MANDATE,
    MINIMUM_MONTHS,
    from_curve,
    judge,
    stability,
    ulcer,
    worst_entry,
)


def _days(n, start="2018-01-01"):
    import datetime

    origin = datetime.date.fromisoformat(start)
    return [(origin + datetime.timedelta(days=i)).isoformat() for i in range(n)]


def _steady(n=1200, rate=0.0009):
    """Compounding at a constant rate: the shape being selected FOR."""
    return [100.0 * math.exp(rate * i) for i in range(n)]


def _spike(n=1200):
    """The champion's shape: flat, a bull run, then a long giveback."""
    out = []
    for i in range(n):
        if i < n * 0.35:
            out.append(100.0)
        elif i < n * 0.6:
            out.append(100.0 * (1 + 5.0 * (i - n * 0.35) / (n * 0.25)))
        else:
            out.append(600.0 * (1 - 0.24 * (i - n * 0.6) / (n * 0.4)))
    return out


class TheUnluckiestInvestor(unittest.TestCase):
    def test_a_curve_ending_below_its_high_punishes_whoever_bought_there(self):
        """The operator's question, stated arithmetically: buy at the top, hold
        to the end. A 24% giveback is a 24% loss for that investor no matter what
        the headline return says."""
        value, at = worst_entry([100.0, 200.0, 152.0])

        self.assertAlmostEqual(value, -0.24, places=6)
        self.assertEqual(at, 1)

    def test_a_curve_ending_at_its_high_leaves_nobody_underwater(self):
        value, _ = worst_entry([100.0, 90.0, 150.0])

        self.assertGreaterEqual(value, 0.0)

    def test_final_return_cannot_see_this_at_all(self):
        """Both curves triple. One leaves its worst buyer whole, the other does
        not, and the measure this laboratory ranked on calls them equal."""
        recovering = [100.0, 50.0, 300.0]
        giving_back = [100.0, 600.0, 300.0]

        self.assertAlmostEqual(recovering[-1] / recovering[0], 3.0)
        self.assertAlmostEqual(giving_back[-1] / giving_back[0], 3.0)
        self.assertGreater(worst_entry(recovering)[0], worst_entry(giving_back)[0])


class TimeSpentUnderwater(unittest.TestCase):
    def test_the_ulcer_index_separates_a_quick_fall_from_a_long_one(self):
        """Same depth, different lives. A maximum drawdown records one moment;
        this records how much of the curve was spent below its high."""
        quick = [100.0, 80.0] + [100.0] * 20
        lingering = [100.0, 80.0] + [80.0] * 20

        self.assertLess(ulcer(quick), ulcer(lingering))

    def test_a_curve_that_never_falls_has_no_ulcer(self):
        self.assertAlmostEqual(ulcer([100.0, 110.0, 120.0]), 0.0, places=9)


class GrowthThatIsALineNotASpike(unittest.TestCase):
    def test_steady_compounding_is_a_straight_line_in_log_space(self):
        self.assertGreater(stability(_steady()), 0.99)

    def test_a_flat_stretch_then_a_spike_is_not(self):
        self.assertLess(stability(_spike()), 0.95)

    def test_a_curve_that_only_falls_earns_nothing_for_fitting_a_line(self):
        """A steady decline fits a line beautifully. Rewarding the fit alone
        would rank the worst possible curve highly."""
        self.assertEqual(
            stability([100.0 * math.exp(-0.001 * i) for i in range(500)]), 0.0
        )


class TheScoreRanksShapeOverSize(unittest.TestCase):
    def test_the_champions_shape_scores_below_a_modest_steady_one(self):
        """THE test. The spike curve ends up 3.6x; the steady one ends up 2.9x.
        Ranked on final return the spike wins, which is how it got its seat."""
        spike = judge(_days(1200), _spike())
        steady = judge(_days(1200), _steady())

        self.assertGreater(spike.final_return, 0.0)
        self.assertLess(spike.score, steady.score)

    def test_the_spike_is_recognised_as_the_operator_described_it(self):
        spike = judge(_days(1200), _spike())

        self.assertLess(spike.worst_entry_return, -0.20, "24% below its own peak")
        self.assertGreater(spike.ulcer_index, 0.05, "a long time underwater")

    def test_a_breach_of_the_mandate_is_flagged_whatever_else_is_true(self):
        deep = judge(_days(4), [100.0, 200.0, 140.0, 260.0])

        self.assertTrue(deep.breaches_mandate)
        self.assertGreaterEqual(deep.maximum_drawdown, MANDATE)

    def test_the_score_is_a_product_so_one_bad_property_vetoes(self):
        """A weighted sum lets a spectacular return buy its way past a
        catastrophic drawdown. That is exactly how this laboratory got its
        champion, so the score multiplies instead."""
        n = 1200
        curve = _steady(n)
        # Same growth, one deep hole two-thirds of the way through.
        holed = list(curve)
        for i in range(int(n * 0.6), int(n * 0.66)):
            holed[i] *= 0.6

        self.assertLess(judge(_days(n), holed).score, judge(_days(n), curve).score)

    def test_too_short_to_judge_scores_zero_rather_than_well(self):
        """A curve with a few months cannot be shown to be steady, and the
        absence of evidence must not read as evidence."""
        self.assertEqual(judge(_days(40), _steady(40)).score, 0.0)

    def test_four_losing_months_in_a_row_is_counted(self):
        import datetime

        stamps, equity, value = [], [], 100.0
        for month in range(14):
            for day in range(28):
                stamps.append(
                    (
                        datetime.date(2020, 1, 1)
                        + datetime.timedelta(days=month * 28 + day)
                    ).isoformat()
                )
                equity.append(value)
            value *= 0.95 if 4 <= month <= 8 else 1.05

        self.assertGreaterEqual(judge(stamps, equity).longest_losing_months, 4)


class MagnitudeStillCounts(unittest.TestCase):
    """The operator's other requirement, which the first version of this score
    broke: a system up 6,000% in training IS better in absolute terms than one up
    353%, and a growth term that divided by 3.0 gave both of them a flat 1.0."""

    def test_a_far_larger_return_scores_higher_on_an_otherwise_equal_curve(self):
        modest = judge(_days(1200), _steady(1200, rate=0.0012))  # about +200%
        vast = judge(_days(1200), _steady(1200, rate=0.0035))  # about +6,000%

        self.assertGreater(vast.final_return, 20 * modest.final_return)
        self.assertGreater(vast.score, modest.score)

    def test_the_reward_for_more_return_diminishes(self):
        """Log, not linear. A linear term would make growth the only term that
        matters and hand the board straight back to the spike.

        Compared at equal steps of RETURN -- +100%, +200%, +300%. Equal steps of
        the compounding RATE would prove nothing: `log1p` of a compounded return
        is the log return, which is exactly linear in the rate, and the first
        version of this test measured that identity and called it a curve."""
        n = 1200

        def ending_at(total):
            rate = math.log1p(total) / (n - 1)
            return judge(_days(n), _steady(n, rate=rate)).terms()["growth"]

        step_one = ending_at(2.0) - ending_at(1.0)
        step_two = ending_at(3.0) - ending_at(2.0)

        self.assertGreater(step_two, 0.0)
        self.assertLess(step_two, step_one)

    def test_a_curve_that_loses_money_scores_nothing_however_smooth(self):
        """A perfectly steady decline has an excellent stability and a placid
        ulcer index. Growth is the term that must veto it."""
        falling = [100.0 * math.exp(-0.0005 * i) for i in range(1200)]

        self.assertEqual(judge(_days(1200), falling).terms()["growth"], 0.0)
        self.assertEqual(judge(_days(1200), falling).score, 0.0)

    def test_the_spike_still_loses_to_the_steady_curve_under_log_growth(self):
        """The load-bearing test, re-run against the new term. The spike ends up
        3.6x and the steady one 2.9x, so the spike now scores HIGHER on growth
        than it used to relative to its rival -- and must still lose overall."""
        spike = judge(_days(1200), _spike())
        steady = judge(_days(1200), _steady())

        self.assertGreater(spike.terms()["growth"], steady.terms()["growth"])
        self.assertLess(spike.score, steady.score)


class TheSealedWindowIsShortAndStillJudgeable(unittest.TestCase):
    def test_seven_months_can_be_scored(self):
        """2026 is seven and a half months. A twelve-month floor scored every
        forward run at exactly zero, which reads as "worthless" and means "short",
        and those must never be the same number."""
        self.assertLessEqual(MINIMUM_MONTHS, 7)
        self.assertGreater(judge(_days(220), _steady(220)).score, 0.0)

    def test_a_few_weeks_still_cannot_be(self):
        self.assertEqual(judge(_days(40), _steady(40)).score, 0.0)


class TheRunUpIsNotPartOfTheResult(unittest.TestCase):
    """A 2026 run is served forty thousand bars of history it is forbidden to
    trade in. That stretch is a flat line at the opening capital by construction,
    and scoring it as part of the curve describes the harness, not the strategy."""

    def _points(self):
        warmup = [
            {"timestamp": f"2025-{m:02d}-01", "equity": 100.0} for m in range(1, 13)
        ]
        traded = [
            {"timestamp": f"2026-{m:02d}-01", "equity": 100.0 + 3.0 * m}
            for m in range(1, 8)
        ]
        return warmup + traded

    def test_the_flat_run_up_is_cut_at_trade_from(self):
        graded = from_curve(self._points(), "2026-01-01")

        self.assertEqual(graded.months, 6)
        self.assertAlmostEqual(graded.final_return, 121.0 / 103.0 - 1.0, places=9)

    def test_keeping_the_run_up_makes_a_rising_curve_look_like_a_spike(self):
        with_runup = from_curve(self._points())
        without = from_curve(self._points(), "2026-01-01")

        self.assertLess(with_runup.log_stability, without.log_stability)

    def test_no_trade_from_keeps_everything_rather_than_guessing(self):
        """Nineteen calendar months on the curve, eighteen returns between them.
        Guessing where trading opened would be worse than keeping the run-up: a
        wrong cut is invisible, and a kept run-up shows up as a bad `steady`."""
        self.assertEqual(from_curve(self._points()).months, 18)


if __name__ == "__main__":
    unittest.main()
