"""The mission board: one screen that answers "what are we doing, in what order,
where is it going" - so the operator does not have to ask (his request, 2026-09-05,
after a day when the GPU training, the day's three verdicts and the ordered plan
were all invisible on a page whose live panel was faithfully showing something else).

Two halves with different clocks, and the tests pin the seam between them:
mission.json is CURATED (moves only at verdicts, versioned in git); the GPU
member/epoch/loss is TELEMETRY parsed from the training log on every push.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PREVIEW = REPO / "research/system06/preview"

spec = importlib.util.spec_from_file_location("ms", PREVIEW / "mock_server.py")
ms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ms)


def test_the_state_carries_the_mission():
    assert "mission" in ms._state(), "the pusher ships _state(); no key, no board"


def test_mission_json_is_valid_and_ordered():
    m = json.loads((REPO / "research/system06/mission.json").read_text(encoding="utf-8"))
    assert m["headline"] and m["target"]
    allowed = {"done", "running", "queued", "blocked", "killed"}
    statuses = [s["status"] for s in m["steps"]]
    assert set(statuses) <= allowed
    assert "running" in statuses or "queued" in statuses, (
        "a plan with nothing running and nothing queued is a finished project, "
        "and this one is not finished")


def test_gpu_telemetry_is_parsed_and_stale_guarded(tmp_path, monkeypatch):
    """A dead training must not keep animating a progress bar - the same failure the
    optimizer heartbeat already guards against, re-guarded here for the new lane."""
    log = tmp_path / "fake_training.log"
    log.write_text("[net 2/5] epoch 30/50  loss 0.4242\n", encoding="utf-8")
    mission = tmp_path / "mission.json"
    mission.write_text(json.dumps({
        "headline": "h", "target": "t", "steps": [],
        "gpu_job": {"title": "x", "log": "fake_training.log"}}), encoding="utf-8")
    monkeypatch.setattr(ms, "MISSION", mission)
    monkeypatch.setattr(ms, "S6", tmp_path)

    g = ms._mission()["gpu"]
    assert (g["member"], g["of"], g["epoch"], g["epochs"]) == (2, 5, 30, 50)
    assert g["loss"] == pytest.approx(0.4242)
    assert 0.0 < g["progress"] < 1.0
    assert g["alive"] is True   # file just written

    import os
    old = os.stat(log).st_mtime - 3600
    os.utime(log, (old, old))   # an hour of silence is not a running training
    assert ms._mission()["gpu"]["alive"] is False


def test_the_page_renders_the_board_on_its_own_tab():
    """The board used to LEAD the live body. It does not any more, and that is the
    point of this test rather than a relaxation of it.

    Operator, 2026-09-16: "on the opening dashboard I want numbers" - the board is a
    plan written in sentences, and four paragraphs of it sat above the only figures on
    the page. So it moved to its own tab, where it is still rendered in full and is one
    click away. What must not happen is for it to be quietly dropped, which is what a
    test that simply deleted the old assertion would have allowed."""
    html = (PREVIEW / "dashboard.html").read_text(encoding="utf-8")
    assert "function missionPanel(" in html
    assert 'id="lt-plan"' in html, "the board lost its tab"
    assert "missionPanel(STATE && STATE.mission) + rationaleBlock(r)" in html, (
        "the Plan tab must still render the board and the attempt's reasoning")
    assert "missionPanel(STATE && STATE.mission) + body" not in html, (
        "the board is back in front of the numbers on the dashboard tab")
    for cls in (".mission", ".mnow", ".mstep", ".mbar-fill"):
        assert cls in html, f"missing CSS for {cls}"


def test_the_dashboard_tab_opens_with_figures():
    """The replacement contract: tiles, a flag for what is being improved, a bar per
    year, and the net's own numbers - before anything that is written in sentences."""
    html = (PREVIEW / "dashboard.html").read_text(encoding="utf-8")
    for fn in ("function kpiRow(", "function experimentFlag(",
               "function annualBars(", "function modelStrip("):
        assert fn in html, f"missing {fn}"
    assert "const numbers = kpiRow(STATE && STATE.best)" in html, (
        "the dashboard body must be built from the figures first")
    for cls in (".kpi", ".kt-v", ".flagx", ".ybars", ".mchip"):
        assert cls in html, f"missing CSS for {cls}"


def test_every_css_variable_used_is_actually_defined():
    """The empty-progress-bar bug, generalised away. The mission bars rendered at the
    correct width and at rgba(0,0,0,0): the fill said background:var(--acc) and the
    page defines --accent. An undefined custom property is not an error anywhere -
    not in the console, not in a test, not visually except as a missing colour the
    author does not notice on a dark theme. The operator noticed (2026-09-05: "the
    progress bars are empty"). Three earlier occurrences of var(--acc) in the
    optimizer panel's CSS had been invisible in the same way for a day.

    So: every var(--x) consumed anywhere in the page must name a property defined in
    the page. Checked textually, which catches the whole class at commit time instead
    of one bar at screenshot time.
    """
    import re

    html = (PREVIEW / "dashboard.html").read_text(encoding="utf-8")
    defined = set(re.findall(r"(--[a-zA-Z][\w-]*)\s*:", html))
    used = set(re.findall(r"var\((--[a-zA-Z][\w-]*)[),]", html))
    missing = used - defined
    assert not missing, f"CSS variables used but never defined: {sorted(missing)}"
