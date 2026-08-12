"""The diary is derived. Every test here is about it not lying.

Sabotage-verified; each test names what it was checked against.
"""

import json
import tempfile
import unittest
from pathlib import Path

from quantlab_manager import diary


def _record(identifier, **overrides):
    base = {
        "id": identifier,
        "iteration": 7,
        "piece": "bear",
        "verdict": "REFUTED",
        "statement": "A claim about the bear branch.",
        "notes": "What was found.",
        "metrics": {"score": 1.5},
        "opened_2026": False,
    }
    base.update(overrides)
    return base


class SystemAttributionTest(unittest.TestCase):
    def test_an_explicit_system_wins(self):
        self.assertEqual(diary.system_of({"system": "intraday"}), "intraday")

    def test_a_record_from_before_the_field_is_the_system_that_existed(self):
        # Guessing forward would be a lie. Guessing backward is the history:
        # four-module was the only system when these were written.
        self.assertEqual(diary.system_of({"piece": "policy"}), "four-module")

    def test_an_unfamiliar_piece_does_not_invent_a_system(self):
        # Sabotage: return the piece itself when unrecognised. The index then
        # grows a section per typo and stops being an index.
        self.assertEqual(diary.system_of({"piece": "wat"}), "four-module")

    def test_a_strategy_family_is_honoured_when_there_is_no_system(self):
        self.assertEqual(
            diary.system_of({"strategy_family": "intraday-momentum"}),
            "intraday-momentum",
        )


class RenderingTest(unittest.TestCase):
    def test_the_index_separates_the_two_systems(self):
        # THE point of the whole module. A flat list implies one line of
        # research; these are two systems with different tapes and bar
        # intervals, and a result from one is not evidence about the other.
        page = diary.render_index(
            [
                _record("H-L001"),
                _record("H-I001", system="intraday", piece="momentum"),
            ]
        )
        self.assertIn("## four-module", page)
        self.assertIn("## intraday", page)
        self.assertIn("2 trading systems", page)
        four = page.index("## four-module")
        intra = page.index("## intraday")
        self.assertIn("H-L001", page[four:intra])
        self.assertNotIn("H-I001", page[four:intra])

    def test_the_index_counts_verdicts_rather_than_asserting_success(self):
        page = diary.render_index(
            [
                _record("H-L001", verdict="REFUTED"),
                _record("H-L002", verdict="CONFIRMED"),
            ]
        )
        self.assertIn("1 confirmed", page)
        self.assertIn("1 refuted", page)

    def test_a_record_with_no_verdict_reads_as_open_not_as_passed(self):
        # Sabotage: default to "CONFIRMED". An in-flight iteration then reads as
        # a success in the index, which is the one direction this must not fail.
        page = diary.render_index([_record("H-L009", verdict=None)])
        self.assertIn("OPEN", page)
        self.assertNotIn("CONFIRMED", page)

    def test_a_pipe_in_a_claim_cannot_break_the_table(self):
        page = diary.render_index([_record("H-L001", statement="a | b | c")])
        row = [line for line in page.splitlines() if "H-L001" in line][0]
        self.assertEqual(row.count("|") - row.count("\\|"), 6)

    def test_the_page_carries_the_claim_the_verdict_and_the_numbers(self):
        page = diary.render_hypothesis(_record("H-L001"), [])
        self.assertIn("H-L001 — REFUTED", page)
        self.assertIn("A claim about the bear branch.", page)
        self.assertIn("What was found.", page)
        self.assertIn('"score": 1.5', page)

    def test_a_page_says_when_it_consulted_the_sealed_year(self):
        # The single fact a reader of this laboratory most needs to see.
        self.assertIn(
            "**Consulted 2026**: yes",
            diary.render_hypothesis(_record("H-L001", opened_2026=True), []),
        )

    def test_the_stages_keep_the_order_the_loop_walked_them(self):
        # Counts alone cannot answer "is it exploring or circling"; order can.
        page = diary.render_hypothesis(
            _record("H-L001"),
            [
                {"stage": "propose"},
                {"stage": "fit"},
                {"stage": "fit"},
                {"stage": "record"},
            ],
        )
        self.assertLess(page.index("`propose`"), page.index("`fit`"))
        self.assertLess(page.index("`fit`"), page.index("`record`"))
        self.assertIn("`fit` × 2", page)

    def test_a_hypothesis_with_no_journal_says_so_instead_of_implying_idleness(self):
        page = diary.render_hypothesis(_record("H-SIZE-001"), [])
        self.assertIn("No journal for this hypothesis", page)


class WriteTest(unittest.TestCase):
    def _laboratory(self, root, records, journals=None):
        ledger = Path(root) / "ledger" / "hypotheses.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("".join(json.dumps(r) + "\n" for r in records))
        journal = Path(root) / "journal"
        journal.mkdir(parents=True, exist_ok=True)
        for identifier, events in (journals or {}).items():
            (journal / f"{identifier}.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in events)
            )
        return ledger, journal, Path(root) / "diary"

    def test_it_writes_a_page_per_hypothesis_under_its_own_system(self):
        with tempfile.TemporaryDirectory() as root:
            ledger, journal, out = self._laboratory(
                root,
                [_record("H-L001"), _record("H-I001", system="intraday")],
                {"H-L001": [{"stage": "fit"}]},
            )
            summary = diary.write(ledger, journal, out)
            self.assertEqual(summary["hypotheses"], 2)
            self.assertEqual(summary["systems"], ["four-module", "intraday"])
            self.assertTrue((out / "four-module" / "H-L001.md").exists())
            self.assertTrue((out / "intraday" / "H-I001.md").exists())
            self.assertTrue((out / "INDEX.md").exists())

    def test_regenerating_replaces_a_stale_verdict_rather_than_appending(self):
        # A hypothesis resolves AFTER its page is first written. If the diary
        # appended, the page would carry both verdicts and the reader would have
        # to guess which one is current.
        with tempfile.TemporaryDirectory() as root:
            ledger, journal, out = self._laboratory(
                root, [_record("H-L001", verdict=None)]
            )
            diary.write(ledger, journal, out)
            page = out / "four-module" / "H-L001.md"
            self.assertIn("OPEN", page.read_text())
            ledger.write_text(json.dumps(_record("H-L001", verdict="REFUTED")) + "\n")
            diary.write(ledger, journal, out)
            text = page.read_text()
            self.assertIn("REFUTED", text)
            self.assertNotIn("OPEN", text)

    def test_a_corrupt_ledger_line_is_skipped_and_the_rest_survives(self):
        # A half-written line during a crash must not cost the whole diary.
        with tempfile.TemporaryDirectory() as root:
            ledger, journal, out = self._laboratory(root, [_record("H-L001")])
            with ledger.open("a") as handle:
                handle.write('{"id": "H-L002", "brok\n')
            summary = diary.write(ledger, journal, out)
            self.assertEqual(summary["hypotheses"], 1)

    def test_a_missing_ledger_produces_an_empty_diary_not_a_crash(self):
        # The loop calls this every iteration. It may never be the thing that
        # stops the research.
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "diary"
            summary = diary.write(
                Path(root) / "nope.jsonl", Path(root) / "nojournal", out
            )
            self.assertEqual(summary["hypotheses"], 0)
            self.assertTrue((out / "INDEX.md").exists())


if __name__ == "__main__":
    unittest.main()
