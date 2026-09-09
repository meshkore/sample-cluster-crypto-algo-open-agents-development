"""The public page publishes what we MEASURED, never what a renderer guessed.

Operator, 2026-09-09, looking at the live site: *"sigo viendo mucha basura en la lista
de estrategias"*. The cause was worse than clutter, and it is the reason this file
exists rather than a one-line fix.

`knowledge/ideas.jsonl` held 166 rows. 145 of them carried no `status` at all - they are
notes harvested from the literature that nobody has triaged. The dashboard rendered

    const st = i.status || "proposed";

so all 145 displayed a confident PROPOSED badge. That badge existed nowhere in the data.
The site was publishing a research position on 145 ideas we had never taken one on, and
it looked completely healthy while doing it - which is the shape of bug that survives,
because nothing anywhere reports an error.

The lesson generalises past this one field: a default in a RENDERER is a claim about the
world. `||` is fine for a label, and a lie for a verdict. So the tests below are not
about payload size. They are about the site never asserting more than the data supports.

Payload size is checked too, but as a symptom: 606 KB of the old push was two internal
notebooks (the 132-row agenda, the 166-row idea harvest) shipped whole to fill panels
that render eight rows and twenty-one cards.

    python -m pytest research/system06/preview/test_public_payload.py -q
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

PREVIEW = Path(__file__).resolve().parent
S6 = PREVIEW.parent
REPO = S6.parents[1]
DASH = PREVIEW / "dashboard.html"

sys.path.insert(0, str(PREVIEW))


@pytest.fixture(scope="module")
def ms():
    """mock_server is imported as a LIBRARY here; it is never run as a server."""
    sys.path.insert(0, str(REPO / "trading-system"))
    import mock_server  # noqa: PLC0415
    return mock_server


# --------------------------------------------------------------------------------------
# the actual rule: no invented verdicts
# --------------------------------------------------------------------------------------

def test_every_published_idea_carries_a_real_status(ms):
    """An idea reaches the public surface only once a human took a position on it."""
    know = ms._knowledge()
    bare = [i.get("id") for i in know["ideas"] if not (i.get("status") or "").strip()]
    assert not bare, (
        "these ideas are published with no status, so the page will have to invent "
        f"one for them: {bare[:10]}")


def test_untriaged_ideas_are_counted_not_hidden(ms):
    """Withholding the backlog is honest only if the page says the backlog exists."""
    know = ms._knowledge()
    assert "untriaged" in know and "harvested_total" in know, (
        "the payload drops untriaged ideas without saying how many - that is not "
        "curation, it is concealment")
    assert know["harvested_total"] == len(know["ideas"]) + know["untriaged"], (
        "published + untriaged must account for every harvested row; a row that is "
        "neither has gone missing silently")


# A status a system or an idea can genuinely hold. Defaulting to any of these turns a
# missing measurement into a published verdict. Defaulting to a word that means "we do
# not know" is the opposite - it is the page admitting the gap - so it is allowed, and
# the distinction is the whole point of the rule.
REAL_STATUSES = {"champion", "frozen", "workshop", "blank",
                 "proposed", "applied", "testing", "rejected", "promising",
                 "overfit-warning", "running", "queued", "win", "loss", "shelved"}
ABSENCE_MARKERS = {"unknown", "undeclared", "untriaged", "unmeasured", ""}


def test_the_renderer_never_defaults_to_a_real_status():
    """The second lock, in the page itself.

    The server now sends only triaged ideas, but a future payload change could leak an
    untriaged row back in. The renderer must then say "undeclared", not pick a verdict.
    """
    src = DASH.read_text(encoding="utf-8")
    defaulted = re.findall(r"""status\s*\|\|\s*["']([a-z-]*)["']""", src)
    invented = sorted({d for d in defaulted if d in REAL_STATUSES})
    assert not invented, (
        "dashboard.html defaults a status to a real verdict, which publishes a "
        f"position the data never took: {invented}")
    unclassified = sorted({d for d in defaulted
                           if d not in REAL_STATUSES and d not in ABSENCE_MARKERS})
    assert not unclassified, (
        "a status is defaulted to a word this test cannot classify as an admission of "
        f"absence; if it is one, add it to ABSENCE_MARKERS: {unclassified}")


def test_status_labels_are_only_ever_looked_up_never_fabricated():
    """`STATUS_EN[st]||st` is fine - it falls back to the REAL status string. What is
    forbidden is falling back to a status the data never carried."""
    src = DASH.read_text(encoding="utf-8")
    assert 'const st = (i.status||"").trim();' in src, (
        "the ideas renderer no longer reads the status defensively; if it was "
        "refactored, keep the property that an absent status renders nothing")
    assert "if(!st){ return \"\"; }" in src, (
        "an idea with no status must render as nothing, not as a card with a guessed "
        "badge")


# --------------------------------------------------------------------------------------
# the symptom: internal notebooks shipped whole
# --------------------------------------------------------------------------------------

def test_the_agenda_is_summarised_not_dumped(ms):
    """The panel renders eight open items; the push carried all 132."""
    rnd = ms._state()["rnd"]
    assert len(rnd["agenda"]) <= 8, (
        f"{len(rnd['agenda'])} agenda rows are being published to fill a panel that "
        "shows eight")
    assert rnd.get("agenda_total", 0) >= len(rnd["agenda"]), (
        "the payload must still say how big the real backlog is")


def test_history_is_not_duplicated_into_the_state(ms):
    """Every iteration already ships once via /api/iterations. The strategy list is a
    reading list; consecutive samples of one parameter search are not strategies."""
    state = ms._state()
    assert len(state["history"]) <= 3, (
        f"{len(state['history'])} iteration cards in the state payload duplicate the "
        "search log, which has its own page and its own endpoint")


def test_the_strategy_rail_lists_systems_not_iterations():
    """One box per SYSTEM - the thing that has a folder, a hypothesis and a verdict."""
    src = DASH.read_text(encoding="utf-8")
    assert 'id="sysbox"' in src, "the systems rail is gone"
    assert 'hist.map(c=>resultCard(c))' not in src, (
        "the rail is rendering a wall of iteration cards again; that is the clutter "
        "this file exists to prevent")


def test_public_payload_stays_lean(ms):
    """A ceiling with a reason, not a round number: the two payloads the page polls
    were 606 KB, of which 465 KB was the two notebooks above."""
    state = len(json.dumps(ms._state(), default=str))
    know = len(json.dumps(ms._knowledge(), default=str))
    total = state + know
    assert total < 250_000, (
        f"the polled payload is back up to {total:,} bytes (state {state:,}, knowledge "
        f"{know:,}); something internal is being shipped whole again")
