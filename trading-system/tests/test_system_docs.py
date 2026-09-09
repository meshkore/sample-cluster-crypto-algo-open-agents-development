"""Every trading system documents itself, and the standard is enforced rather than hoped.

The whole value of the documentation standard is that a NEW system can read the old
ones and not repeat their work. That value evaporates the first time a system ships
without a summary, or with a summary whose "what hurt" section was quietly left empty
because failures are less pleasant to write down than successes.

So: a system package with a `docs/` folder must have all three files, `context.json`
must parse and carry the fields the dashboard's Log tab reads, and `SUMMARY.md` must
have all six headings even when the answer under one of them is "not yet written up".
An empty section that SAYS it is empty is documentation; a missing section is a claim
that nothing happened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

TRADING = Path(__file__).resolve().parents[1]
REQUIRED_FILES = ("SUMMARY.md", "RESULTS.md", "context.json")
REQUIRED_HEADINGS = ("## 1. Hypothesis", "## 2. What it is", "## 3. What helped",
                     "## 4. What hurt", "## 5. What is still open", "## 6. Rules learned")
REQUIRED_KEYS = ("id", "name", "status", "hypothesis", "period",
                 "helped", "hurt", "open", "rules", "results")
VALID_STATUS = {"champion", "frozen", "workshop", "blank"}


def _documented_systems() -> list[Path]:
    return sorted(p.parent for p in TRADING.glob("quantlab_*/docs")
                  if p.is_dir())


def test_there_are_documented_systems():
    assert _documented_systems(), (
        "no system carries a docs/ folder; the standard would be vacuous")


def test_every_trading_system_package_is_documented():
    """A package with a strategy is a system, and a system documents itself."""
    undocumented = []
    for pkg in sorted(TRADING.glob("quantlab_*")):
        if not pkg.is_dir() or pkg.name in ("quantlab_ml", "quantlab_catalog"):
            continue                      # libraries, not systems
        if not (pkg / "docs").is_dir():
            undocumented.append(pkg.name)
    assert not undocumented, (
        f"these systems have no docs/ folder: {undocumented}. See "
        f".meshkore/context/system-documentation-standard.md - a skeleton that says "
        f"'not yet written up' is acceptable; silence is not.")


@pytest.mark.parametrize("system", _documented_systems(), ids=lambda p: p.name)
def test_the_three_files_exist(system: Path):
    missing = [f for f in REQUIRED_FILES if not (system / "docs" / f).is_file()]
    assert not missing, f"{system.name}/docs is missing {missing}"


@pytest.mark.parametrize("system", _documented_systems(), ids=lambda p: p.name)
def test_the_summary_has_every_section(system: Path):
    text = (system / "docs" / "SUMMARY.md").read_text(encoding="utf-8")
    missing = [h for h in REQUIRED_HEADINGS if h not in text]
    assert not missing, (
        f"{system.name}/docs/SUMMARY.md is missing {missing}. A section left out is a "
        f"claim that nothing happened there; write the heading and say it is empty.")


@pytest.mark.parametrize("system", _documented_systems(), ids=lambda p: p.name)
def test_context_json_is_readable_by_the_dashboard(system: Path):
    doc = json.loads((system / "docs" / "context.json").read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_KEYS if k not in doc]
    assert not missing, f"{system.name}/docs/context.json is missing {missing}"
    assert doc["status"] in VALID_STATUS, (
        f"{system.name}: status {doc['status']!r} is not one of {sorted(VALID_STATUS)}")
    for field in ("helped", "hurt", "open", "rules"):
        assert isinstance(doc[field], list), f"{system.name}: {field} must be a list"
    for row in doc["helped"] + doc["hurt"]:
        assert {"what", "effect"} <= set(row), (
            f"{system.name}: every helped/hurt row states WHAT changed and its measured "
            f"EFFECT - a row without both is an opinion")


def test_exactly_one_system_is_the_champion():
    """The strategy list shows one box per system and one of them holds the bar."""
    champions = []
    for system in _documented_systems():
        doc = json.loads((system / "docs" / "context.json").read_text(encoding="utf-8"))
        if doc["status"] == "champion":
            champions.append(doc["id"])
    assert len(champions) == 1, (
        f"expected exactly one champion, found {champions}. Two champions means the bar "
        f"is ambiguous, and a bar that moves is not a bar.")


def test_the_open_system_points_at_the_champions_summary():
    """A blank system's first instruction is to read what was already refused."""
    for system in _documented_systems():
        doc = json.loads((system / "docs" / "context.json").read_text(encoding="utf-8"))
        if doc["status"] != "blank":
            continue
        text = (system / "docs" / "SUMMARY.md").read_text(encoding="utf-8")
        assert "quantlab_system06/docs/SUMMARY.md" in text, (
            f"{system.name}: a system opening without a pointer to the refusals that "
            f"came before it will re-run them")


# ---------------------------------------------------------------------------------------
# context.json and SUMMARY.md are maintained by hand and are rendered SIDE BY SIDE on the
# public page: the rail reads context.json, the Log tab reads SUMMARY.md. Nothing forced
# them to agree, so the page could show a system with eight recorded lessons in the rail
# and "not yet written up" in the tab. On 2026-09-09 six of seven systems were in exactly
# that state - the boxes existed and said nothing. These pin the two together.
# ---------------------------------------------------------------------------------------

NOT_WRITTEN = "not yet written up"


def _summary(system: Path) -> str:
    return (system / "docs" / "SUMMARY.md").read_text(encoding="utf-8").lower()


def test_a_written_up_record_does_not_claim_to_be_empty():
    """If context.json carries lessons, the summary may not say there are none."""
    for system in _documented_systems():
        doc = json.loads((system / "docs" / "context.json").read_text(encoding="utf-8"))
        if not (doc.get("helped") or doc.get("hurt")):
            continue
        assert NOT_WRITTEN not in _summary(system), (
            f"{system.name}: context.json records {len(doc.get('helped') or [])} things "
            f"that helped and {len(doc.get('hurt') or [])} that hurt, but SUMMARY.md "
            f"still says '{NOT_WRITTEN}'. The rail and the Log tab would show two "
            f"different systems.")


def test_an_empty_record_says_so_rather_than_implying_a_verdict():
    """The converse. A system with nothing recorded must SAY nothing was recorded, so
    silence reads as an admission and never as 'nothing was learned here'."""
    for system in _documented_systems():
        doc = json.loads((system / "docs" / "context.json").read_text(encoding="utf-8"))
        if doc.get("helped") or doc.get("hurt") or doc.get("status") == "blank":
            continue
        text = _summary(system)
        assert NOT_WRITTEN in text or "nothing recorded" in text, (
            f"{system.name}: no lessons recorded and the summary does not admit it")


def test_the_documented_flag_matches_the_document():
    """`documented: true` is read by tooling; it must not outrun the content."""
    for system in _documented_systems():
        doc = json.loads((system / "docs" / "context.json").read_text(encoding="utf-8"))
        if doc.get("status") == "blank":
            continue          # a blank system is documented precisely by being empty
        claimed = bool(doc.get("documented"))
        real = bool(doc.get("helped") and doc.get("rules"))
        assert claimed == real, (
            f"{system.name}: documented={claimed} but helped/rules are "
            f"{'present' if real else 'absent'}")
