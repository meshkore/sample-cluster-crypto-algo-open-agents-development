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


def test_the_page_renders_the_board_first():
    html = (PREVIEW / "dashboard.html").read_text(encoding="utf-8")
    assert "function missionPanel(" in html
    assert "missionPanel(STATE && STATE.mission) + body" in html, (
        "the board must lead the live body, not trail whichever panel is running")
    for cls in (".mission", ".mnow", ".mstep", ".mbar-fill"):
        assert cls in html, f"missing CSS for {cls}"
