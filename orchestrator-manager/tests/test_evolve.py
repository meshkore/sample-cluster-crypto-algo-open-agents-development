"""The loop reviewing itself, and the fence around what that is allowed to mean.

Self-improvement is the part of this design that could go wrong quietly, so the
tests here are mostly about what the evolve session CANNOT do. A knob outside
its range, a knob nobody defined, a request to change a strategy parameter, a
reply that is not JSON at all -- each has to end with the loop unchanged and
still running.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from quantlab_manager import evolve, tuning
from quantlab_manager.loop import ResearchLoop


class TestTheKnobsAreFenced(unittest.TestCase):
    def test_defaults_are_inside_their_own_ranges(self):
        # A default outside its range would make the very first `load` a change.
        for knob in tuning.KNOBS:
            self.assertIsNotNone(
                knob.clean(knob.default), f"{knob.name} default is inadmissible"
            )

    def test_a_value_outside_the_range_is_discarded_not_clamped(self):
        """Clamping would let a model that asked for ten thousand quietly get
        the maximum and believe it got what it asked for, which makes the record
        of what was tried a lie."""
        self.assertIsNone(tuning.BY_NAME["population"].clean(10_000))
        self.assertIsNone(tuning.BY_NAME["population"].clean(1))
        self.assertIsNone(tuning.BY_NAME["gate"].clean(-0.5))

    def test_integers_are_integers(self):
        self.assertIsNone(tuning.BY_NAME["generations"].clean(4.5))
        self.assertEqual(tuning.BY_NAME["generations"].clean(4.0), 4)

    def test_junk_is_rejected_without_raising(self):
        for junk in (None, "many", [], {}, float("nan"), float("inf")):
            self.assertIsNone(tuning.BY_NAME["population"].clean(junk))

    def test_an_unknown_knob_never_reaches_the_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tuning.json"
            changes = tuning.apply(
                path, {"maximum_drawdown": 0.9, "trade_from": "2026-01-01"}
            )
        self.assertEqual(changes, [])

    def test_a_corrupt_file_degrades_to_defaults_rather_than_stopping_the_loop(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tuning.json"
            path.write_text("{not json at all")
            self.assertEqual(tuning.load(path), tuning.defaults())

    def test_applying_reports_exactly_what_moved(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tuning.json"
            changes = tuning.apply(path, {"population": 16, "generations": 4})
            # generations was already 4, so it did not move.
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]["knob"], "population")
            self.assertEqual(changes[0]["to"], 16)
            self.assertEqual(tuning.load(path)["population"], 16)

    def test_a_proposal_that_changes_nothing_writes_nothing(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tuning.json"
            self.assertEqual(tuning.apply(path, tuning.defaults()), [])
            self.assertFalse(path.exists(), "an empty change created a file")


class TestTheEvolveReplyIsValidated(unittest.TestCase):
    def test_only_whitelisted_knobs_survive(self):
        answer = evolve.validate(
            {
                "knobs": {"population": 12, "maximum_drawdown": 0.9, "gate": 99},
                "memory_note": "hello",
                "reasoning": "because",
            }
        )
        self.assertEqual(answer["knobs"], {"population": 12})

    def test_anything_that_is_not_an_object_is_rejected(self):
        for junk in (None, "raise the population", [1, 2], 7):
            self.assertIsNone(evolve.validate(junk))

    def test_an_empty_proposal_is_a_valid_answer(self):
        answer = evolve.validate({"knobs": {}, "memory_note": "all well"})
        self.assertEqual(answer["knobs"], {})
        self.assertEqual(answer["memory_note"], "all well")

    def test_the_briefing_never_carries_source_code(self):
        """A reviewer shown `loop.py` proposes changes to `loop.py`, which is
        the one thing it may not have."""
        brief = evolve.briefing({"iterations_recorded": 3}, tuning.defaults(), [])
        self.assertNotIn("def ", brief)
        self.assertIn("knobs_you_may_change", brief)
        self.assertIn("you_may_not_change", brief)


class TestTheNotebookOnlyGrows(unittest.TestCase):
    def test_a_second_note_does_not_replace_the_first(self):
        """A process that can rewrite its account of being wrong can delete the
        evidence, and the deletion looks exactly like a tidy-up."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "MEMORY.md"
            evolve.append_memory(path, "the first thing we learned", 10)
            evolve.append_memory(path, "the second thing we learned", 20)
            text = path.read_text()
        self.assertIn("the first thing we learned", text)
        self.assertIn("the second thing we learned", text)
        self.assertIn("Iteration 10", text)
        self.assertIn("Iteration 20", text)

    def test_an_empty_note_writes_nothing(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "MEMORY.md"
            self.assertFalse(evolve.append_memory(path, "   ", 1))
            self.assertFalse(path.exists())

    def test_an_unwritable_path_is_false_rather_than_an_exception(self):
        # A failed notebook write must not cost an iteration.
        self.assertFalse(evolve.append_memory("/nope/nowhere/MEMORY.md", "x", 1))


class TestTheLoopSurvivesItsOwnReview(unittest.TestCase):
    def _loop(self, directory, reviewer):
        (Path(directory) / "CONTRACT.md").write_text("x")
        return ResearchLoop(
            lab_fit=None,
            lab_forward=None,
            store=None,
            symbols=["BTCUSDT"],
            repository=directory,
            reviewer_of_self=reviewer,
            state_path=Path(directory) / "state.json",
            ledger_path=Path(directory) / "l.jsonl",
        )

    @staticmethod
    def _answering(payload):
        class _Reviewer:
            available = True
            handle = "self-reviewer"
            last_error = None

            @staticmethod
            def ask(briefing):
                return payload

        return _Reviewer()

    def test_a_review_moves_a_knob_and_records_the_change(self):
        with TemporaryDirectory() as directory:
            loop = self._loop(
                directory,
                self._answering(
                    {
                        "knobs": {"population": 18},
                        "memory_note": "BEAR is exhausted; see H-L083.",
                        "reasoning": "the population is too small to recombine",
                    }
                ),
            )
            loop.state.iteration = 10
            record = loop.evolve()

            self.assertIsNotNone(record)
            self.assertEqual(loop.settings()["population"], 18)
            self.assertEqual(record["metrics"]["knob_changes"][0]["to"], 18)
            self.assertTrue(record["metrics"]["memory_note_written"])
            # It is in the append-only ledger, not only in memory.
            written = [
                json.loads(line)
                for line in (Path(directory) / "l.jsonl").read_text().splitlines()
                if line.strip()
            ]
            self.assertEqual(written[-1]["piece"], "loop")

    def test_the_new_setting_reaches_the_search(self):
        with TemporaryDirectory() as directory:
            loop = self._loop(directory, self._answering({"knobs": {"generations": 7}}))
            loop.state.iteration = 10
            loop.evolve()
            loop.apply_settings()
        self.assertEqual(loop.generations, 7)

    def test_a_review_that_asks_for_a_strategy_parameter_changes_nothing(self):
        with TemporaryDirectory() as directory:
            loop = self._loop(
                directory,
                self._answering(
                    {"knobs": {"bear_breadth": 0.9, "maximum_drawdown": 0.5}}
                ),
            )
            loop.state.iteration = 10
            record = loop.evolve()
        self.assertEqual(record["metrics"]["knob_changes"], [])

    def test_an_unusable_reply_costs_nothing(self):
        with TemporaryDirectory() as directory:
            loop = self._loop(directory, self._answering(None))
            loop.state.iteration = 10
            self.assertIsNone(loop.evolve())

    def test_no_reviewer_is_a_supported_state(self):
        with TemporaryDirectory() as directory:
            self.assertIsNone(self._loop(directory, None).evolve())


if __name__ == "__main__":
    unittest.main()
