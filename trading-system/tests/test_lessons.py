"""LESSONS.md is the document a new system reads first, so it must not be able to lie.

It is generated from every system's `docs/context.json`. The failure mode worth guarding
is not that it goes missing - that is loud - but that it drifts: someone edits a system's
record, the summary of the record still says the old thing, and the summary is the one
the next system actually reads. A stale digest is worse than no digest, because it is
trusted.

    python -m pytest trading-system/tests/test_lessons.py -q
"""

from __future__ import annotations

import pytest

import json
import sys
from pathlib import Path

TRADING = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRADING))

from quantlab_catalog import lessons  # noqa: E402


def test_the_document_is_current():
    """Regenerating must produce exactly what is on disk."""
    assert lessons.OUT.is_file(), f"{lessons.OUT} does not exist; run the generator"
    on_disk = lessons.OUT.read_text(encoding="utf-8")
    assert on_disk == lessons.build(), (
        "LESSONS.md has drifted from the systems' own records. Run "
        "`python -m quantlab_catalog.lessons`. Do not edit the document by hand - the "
        "per-system context.json is the source of truth.")


def test_every_system_with_rules_appears():
    """A system whose lessons are missing from the digest is a system the next
    hypothesis will silently re-run."""
    collected = {s["id"] for s in lessons.collect()}
    for ctx in TRADING.glob("systems/system*/docs/context.json"):
        doc = json.loads(ctx.read_text(encoding="utf-8"))
        if doc.get("rules"):
            assert doc["id"] in collected, (
                f"{doc['id']} records {len(doc['rules'])} rules and none of them reach "
                f"LESSONS.md")


def test_the_champion_is_read_first():
    """Rules paid for with sealed years outrank rules paid for with a refutation."""
    order = [s["status"] for s in lessons.collect()]
    assert order[0] == "champion", (
        f"the first system in the digest is '{order[0]}'; the champion's rules cost the "
        f"most and should be read first")


def test_no_rule_is_empty():
    for s in lessons.collect():
        for rule in s["rules"]:
            assert rule.strip(), f"{s['id']} carries a blank rule"


def test_the_blank_system_points_at_the_digest():
    """A new system's first instruction is to read what is already known.

    The property guarded here is CONDITIONAL, and it was not always written that way.
    Until 2026-09-11 this asserted that a blank system exists at all, which conflated two
    different things: whether the laboratory currently holds an open slot (a roadmap
    question, and the answer changes every time a system starts work) with whether a slot
    that IS open points at the lessons digest (the thing a test can usefully protect).
    System 08 left `blank` for `workshop` on the day it was implemented, and the old
    assertion failed for a reason that had nothing to do with the rule it was defending.
    """
    blanks = [p for p in TRADING.glob("systems/system*/docs/context.json")
              if json.loads(p.read_text(encoding="utf-8")).get("status") == "blank"]
    if not blanks:
        pytest.skip("no system is currently blank - nothing to check, which is not a "
                    "failure of this rule")
    for ctx in blanks:
        text = (ctx.parent / "SUMMARY.md").read_text(encoding="utf-8")
        assert "LESSONS.md" in text, (
            f"{ctx.parents[1].name}: opens without pointing at the 29 rules the "
            f"laboratory already paid for")
