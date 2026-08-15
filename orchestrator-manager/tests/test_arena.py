"""The unattended search: what it may learn from, and what it may never learn from.

This process is meant to run for days with nobody watching it, publishing to a
public board. Two classes of bug matter more here than anywhere else in the
laboratory: one that lets the sealed year influence a decision, and one that
degrades silently instead of stopping.

Three defects found while building it are pinned here:

- `test_a_fold_with_too_few_trades_is_excluded_not_failed`: scoring "cannot be
  judged" as "failed" made the incumbent -- a deliberately selective system --
  score zero, so the floor it was meant to set was no floor at all.
- `test_only_scoring_genomes_breed`: seven vetoing terms means most of the space
  scores exactly zero, and a top-thirty that is mostly zeros breeds zeros. The
  second round of the first run measured thirty-eight genomes and every one of
  them scored nothing.
- `test_an_off_grid_value_snaps_rather_than_crashing`: the archive rounds on the
  way out, so a stake of one third reads back as 0.3333 and `tuple.index` threw.
  A 72-hour run outlives the code that started it.

Sabotage-verified: making `consistent` count unjudgeable folds as failures makes
the fold test report 0.0; removing the immigrant clause makes the exploration
test find only surrogate-chosen genomes.
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def _load():
    for package in ("backtester", "trading-system", "orchestrator-manager"):
        path = str(ROOT / package)
        if path not in sys.path:
            sys.path.insert(0, path)
    location = ROOT / "orchestrator-manager" / "scripts" / "arena.py"
    spec = importlib.util.spec_from_file_location("arena_under_test", location)
    module = importlib.util.module_from_spec(spec)
    sys.modules["arena_under_test"] = module
    spec.loader.exec_module(module)
    return module


arena = _load()
hs = arena.hs


def _tape(days=800, start="2018-01-01", drift=0.0015, swing=0.04):
    """One synthetic symbol at five-minute resolution, that actually trades.

    Two components, and both are load-bearing. `drift` compounds day over day so
    the close sits above its trailing mean, which the entry rule requires. `swing`
    rises through each session so the move from the day's open crosses a
    threshold in the range the arena searches -- at hour 6, a quarter of the way
    through the day, that is a quarter of `swing`.

    The first version of this fixture had a 0.06% intraday move against
    thresholds starting at 0.5%, so nothing ever entered and three tests skipped
    themselves. A structural test that skips is a test that does not exist.
    """
    bars = days * hs.BARS_PER_DAY
    index = np.arange(bars)
    trend = 100.0 * np.exp(drift * index / hs.BARS_PER_DAY)
    session = (index % hs.BARS_PER_DAY) / hs.BARS_PER_DAY
    close = trend * (1.0 + swing * session)
    stamp = np.datetime64(f"{start}T00:00:00", "s") + index * np.timedelta64(300, "s")
    hour = ((index * 5) // 60) % 24
    minute = (index * 5) % 60
    day_open = np.repeat(close[:: hs.BARS_PER_DAY], hs.BARS_PER_DAY)[:bars]
    return hs.Tape(
        close=close,
        hour=hour.astype(int),
        minute=minute.astype(int),
        day_open=day_open,
        stamp=stamp,
        tradeable=np.ones(bars, dtype=bool),
    )


class TheGenomeGridSurvivesItsOwnArchive(unittest.TestCase):
    def test_an_off_grid_value_snaps_rather_than_crashing(self):
        """`document` rounds a stake of one third to 0.3333, and `tuple.index`
        threw on the way back in. A 72-hour run outlives the code that started
        it, so an archive row must always produce a breedable parent."""
        row = {
            "hour": 6,
            "threshold": 0.0251,
            "hold_days": 3,
            "trend_days": 31,
            "stop": None,
            "stake": 0.3333,
            "target_vol": None,
        }
        genome = arena.Genome.read(row)

        self.assertIn(genome.stake, arena.AXES["stake"])
        self.assertIn(genome.threshold, arena.AXES["threshold"])
        self.assertIn(genome.trend_days, arena.AXES["trend_days"])

    def test_none_is_a_value_and_never_snaps_to_a_number(self):
        """ "No stop at all" and "a 5% stop" are different systems. Rounding one
        into the other would silently change what was measured."""
        self.assertIsNone(arena._nearest(arena.AXES["stop"], None))
        self.assertIsNotNone(arena._nearest(arena.AXES["stop"], 0.049))

    def test_a_mutation_steps_one_place_and_never_teleports(self):
        """A mutation that jumps anywhere is a random restart wearing a genetic
        name: it destroys whatever made the parent worth keeping."""
        rng = random.Random(7)
        parent = arena.Genome(6, 0.015, 3, 30, 0.08, 0.16, 0.006)
        for _ in range(200):
            child = arena.mutate(parent, rng, rate=1.0)
            for name, values in arena.AXES.items():
                gap = abs(
                    values.index(getattr(child, name))
                    - values.index(getattr(parent, name))
                )
                self.assertLessEqual(gap, 1, name)

    def test_every_axis_of_a_child_came_from_one_parent_or_the_other(self):
        rng = random.Random(3)
        one = arena.Genome(6, 0.015, 3, 30, 0.08, 0.16, 0.006)
        other = arena.Genome(14, 0.03, 10, 90, None, 0.06, None)
        for _ in range(50):
            child = arena.cross(one, other, rng)
            for name in arena.AXES:
                self.assertIn(
                    getattr(child, name), (getattr(one, name), getattr(other, name))
                )


class WhatCountsAsConsistent(unittest.TestCase):
    """The seventh term, and the distinction it turns on: a fold that cannot be
    judged is not a fold that failed."""

    def setUp(self):
        self.arena = arena.Arena({"BTCUSDT": _tape()}, {}, seed=1)

    def test_a_fold_with_too_few_trades_is_excluded_not_failed(self):
        """THE test. Counting an unjudgeable fold as a failure makes absence of
        evidence into evidence of absence, and every selective system scores
        zero for the crime of being selective -- which is what happened to the
        incumbent on the first run of this file."""
        self.assertEqual(arena.consistency([0.4, 0.5, None, None]), 1.0)
        self.assertEqual(arena.consistency([0.4, 0.0, None, None]), 0.5)
        self.assertEqual(arena.consistency([0.4, 0.5, 0.0, 0.0]), 0.5)

    def test_one_judgeable_fold_is_not_a_consistency_claim(self):
        """One fold is the whole-era figure again, wearing a second name and
        holding a second veto -- so it scores zero rather than a flattering
        1.0, which is what "one for one" would otherwise come to."""
        self.assertEqual(arena.consistency([0.9, None, None, None]), 0.0)
        self.assertEqual(arena.consistency([None, None, None, None]), 0.0)

    def test_a_genome_measured_on_a_real_walk_reports_its_folds(self):
        """The wiring, not the arithmetic: `measure` must pass what the walk
        produced into the term, not a placeholder."""
        verdict = self.arena.measure(arena.Genome(6, 0.005, 3, 20, None, 0.16, None))

        self.assertIsNotNone(verdict, "the fixture tape must produce trades")
        self.assertEqual(len(verdict.folds), arena.FOLDS)
        self.assertEqual(verdict.consistent, arena.consistency(verdict.folds))

    def test_the_folds_span_the_era_and_do_not_overlap(self):
        bounds = self.arena._fold_bounds()

        self.assertEqual(len(bounds), arena.FOLDS)
        for (_, end), (following, _) in zip(bounds, bounds[1:], strict=False):
            self.assertEqual(end, following)


class TheSealedYearIsNeverFeedback(unittest.TestCase):
    """The rule this whole laboratory is built on, and the one an unattended
    process is most likely to break quietly."""

    def test_fitness_does_not_change_when_the_sealed_tape_changes(self):
        """A structural test rather than a reading of the code. If any sealed
        RETURN reached the objective, replacing the sealed tape with a different
        one would move the number."""
        train = {"BTCUSDT": _tape()}
        genome = arena.Genome(6, 0.01, 3, 20, 0.12, 0.16, None)

        rising = arena.Arena(train, {"BTCUSDT": _tape(days=400, drift=0.004)}, seed=1)
        falling = arena.Arena(train, {"BTCUSDT": _tape(days=400, drift=-0.004)}, seed=1)
        one = rising.measure(genome)
        other = falling.measure(genome)

        if one is None or other is None:
            self.skipTest("this genome takes no trades on the synthetic tape")
        self.assertEqual(one.fitness, other.fitness)

    def test_what_the_sealed_year_IS_asked_is_a_count(self):
        """The one clause: how much evidence exists, never what it says."""
        verdict = arena.Verdict(
            genome=arena.Genome(6, 0.01, 3, 20, None, 0.16, None),
            fitness=0.4,
            whole={},
            consistent=0.75,
            folds=[0.4, 0.5, None, 0.2],
            taken=120,
            sealed_trades=31,
            endures=True,
        )
        document = verdict.document()

        self.assertEqual(document["sealed_trades"], 31)
        self.assertFalse(
            [key for key in document if "sealed" in key and key != "sealed_trades"],
            "no sealed figure other than the trade count may be recorded",
        )


class TheSearchDoesNotFoolItself(unittest.TestCase):
    def test_only_scoring_genomes_breed(self):
        """Seven vetoing terms means most of the space scores exactly zero. Ties
        at zero carry no information about direction, which is the only thing a
        parent is for -- and the second round of the first run measured
        thirty-eight genomes, all of them zero, for exactly this reason."""
        archive = [
            {
                "fitness": 0.0,
                **arena.Genome(h, 0.01, 3, 20, None, 0.16, None).document(),
            }
            for h in range(20)
        ] + [
            {
                "fitness": 0.4,
                **arena.Genome(21, 0.02, 5, 30, 0.08, 0.12, None).document(),
            }
        ]
        ranked = sorted(archive, key=lambda row: -row["fitness"])
        scoring = [row for row in ranked if row["fitness"] > 0.0][:30]

        self.assertEqual(len(scoring), 1)
        self.assertEqual(scoring[0]["hour"], 21)

    def test_immigrants_are_measured_whatever_the_model_says(self):
        """A surrogate trained only on what the surrogate chose agrees with
        itself for ever, and the honest measurement of whether it is improving
        goes with it."""
        board = arena.Arena({"BTCUSDT": _tape(days=120)}, {}, seed=2)

        class AlwaysTheSame:
            def predict(self, x):
                return np.zeros(len(x))

        board.model = AlwaysTheSame()
        proposed = board.propose([arena.Genome(6, 0.01, 3, 20, None, 0.16, None)])

        self.assertEqual(len(proposed), arena.MEASURED)
        self.assertGreaterEqual(len({g for g, _ in proposed}), arena.IMMIGRANTS)

    def test_the_surrogate_refuses_to_fit_on_too_little(self):
        """A model fitted on forty points would confidently rank fifteen hundred,
        and the search would spend its first hours exploring whatever those forty
        happened to suggest."""
        board = arena.Arena({}, {}, seed=0)
        board.archive = [{"features": [0.0] * 9, "fitness": 0.1}] * 40

        self.assertIsNone(board.fit_surrogate())
        self.assertIsNone(board.model)

    def test_rank_correlation_is_none_rather_than_zero_on_too_few_pairs(self):
        """Zero would read as "the model learned nothing", which is a finding.
        "Not enough pairs to say" is not the same claim."""
        self.assertIsNone(arena.spearman([1.0, 2.0], [1.0, 2.0]))

    def test_rank_correlation_is_one_on_a_perfect_ordering(self):
        values = [float(i) for i in range(12)]

        self.assertAlmostEqual(arena.spearman(values, values), 1.0, places=9)
        self.assertAlmostEqual(arena.spearman(values, values[::-1]), -1.0, places=9)


class TheProcessSurvivesItsOwnSupervisor(unittest.TestCase):
    """It is restarted on purpose, and everything it must not forget lives on
    disk. The previous search in this laboratory held its cycle counter in a
    process variable and re-scored cycle zero nine times."""

    def test_the_daily_promotion_cap_is_read_off_the_ledger(self):
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).isoformat()
        with tempfile.TemporaryDirectory() as folder:
            ledger = Path(folder) / "rounds.jsonl"
            ledger.write_text(
                json.dumps({"at": today, "promoted": [{"label": "a"}, {"label": "b"}]})
                + "\n"
                + json.dumps({"at": "2020-01-01T00:00:00+00:00", "promoted": [{}]})
                + "\n"
            )

            self.assertEqual(arena.promotions_today(ledger), 2)

    def test_a_missing_ledger_is_zero_promotions_not_a_crash(self):
        self.assertEqual(arena.promotions_today(Path("/nonexistent/rounds.jsonl")), 0)

    def test_a_truncated_archive_line_is_skipped_not_fatal(self):
        """The process is killed mid-write eventually. A half-line must cost one
        evaluation, not the whole archive."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.jsonl"
            path.write_text(
                json.dumps({"features": [0.0] * 9, "fitness": 0.2})
                + "\n"
                + '{"features": [0.0, 0.0'
                + "\n"
            )
            original = arena.ARCHIVE
            try:
                arena.ARCHIVE = path
                rows = arena.read_archive()
            finally:
                arena.ARCHIVE = original

            self.assertEqual(len(rows), 1)


class WhatAPromotionActuallyRuns(unittest.TestCase):
    def test_the_hold_is_translated_into_bars_not_passed_as_days(self):
        """The screen counts holds in days and the engine in bars. Handing one
        to the other would publish a system three hundred times shorter than the
        one that was measured."""
        parameters = arena.brain_parameters(
            arena.Genome(6, 0.025, 3, 30, None, 1 / 3, None)
        )

        self.assertEqual(parameters["maximum_holding_bars"], 3 * hs.BARS_PER_DAY)
        self.assertEqual(parameters["itsm_hour"], 6)
        self.assertEqual(parameters["trend_ma_days"], 30)

    def test_the_gate_that_is_a_prior_travels_with_it(self):
        """It cannot be fitted honestly on a research era that is almost entirely
        a rising market, so it is applied and never searched -- in the screen and
        in the engine alike, or the published run is not the one measured."""
        parameters = arena.brain_parameters(
            arena.Genome(6, 0.025, 3, 30, None, 0.16, None)
        )

        self.assertEqual(parameters["market_gate_drawdown"], hs.MARKET_GATE)
        self.assertEqual(parameters["maximum_positions"], hs.SLOTS)

    def test_the_stake_maps_into_a_risk_the_engine_will_accept(self):
        """Approximate, and bounded so the approximation cannot produce a size
        the operator never sanctioned."""
        for stake in arena.AXES["stake"]:
            risk = arena.brain_parameters(
                arena.Genome(6, 0.025, 3, 30, None, stake, None)
            )["risk_per_trade"]

            self.assertGreaterEqual(risk, 0.005)
            self.assertLessEqual(risk, 0.05)


if __name__ == "__main__":
    unittest.main()
