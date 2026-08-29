"""The hourly pulse must survive the states that matter and never lie about silence."""
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "pulse", REPO / "research/system06/pulse.py")
pulse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pulse)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    rnd = tmp_path / "rnd"
    rnd.mkdir()
    monkeypatch.setattr(pulse, "S6", tmp_path)
    monkeypatch.setattr(pulse, "RND", rnd)
    monkeypatch.setattr(pulse, "PULSE", rnd / "pulse.jsonl")
    return tmp_path, rnd


def test_a_dead_daemon_reads_as_stale_not_as_silence(lab):
    """The failure this guards: a stopped runner producing a calm-looking pulse."""
    root, rnd = lab
    (root / "autotest_live.json").write_text(json.dumps(
        {"state": "running", "detail": "P99 seed 1: training",
         "heartbeat": "2020-01-01T00:00:00+00:00"}), encoding="utf-8")
    row = pulse.snapshot(None)
    assert "autotest" in row["stale_daemons"]
    assert "STALE" in row["summary"]


def test_a_fresh_heartbeat_reads_as_running(lab):
    from datetime import datetime, timezone
    root, rnd = lab
    (root / "autotest_live.json").write_text(json.dumps(
        {"state": "running", "detail": "P99 seed 1: training epoch 3/50",
         "heartbeat": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
    row = pulse.snapshot(None)
    assert "autotest" not in row["stale_daemons"]   # the flag, not the prose
    assert "epoch 3/50" in row["summary"]


def test_an_empty_agenda_is_announced_loudly(lab):
    root, rnd = lab
    (rnd / "program.jsonl").write_text(
        json.dumps({"id": "old", "status": "done"}) + "\n", encoding="utf-8")
    row = pulse.snapshot(None)
    assert "AGENDA EMPTY" in row["summary"]
    assert row["queued"] == []


def test_it_reports_what_landed_since_the_previous_pulse(lab):
    root, rnd = lab
    (rnd / "program_results.jsonl").write_text(
        json.dumps({"id": "P-old", "at": "2026-08-29T10:00:00+00:00", "arms": {}}) + "\n" +
        json.dumps({"id": "P-new", "at": "2026-08-29T12:00:00+00:00",
                    "arms": {"a": {}, "b": {}}}) + "\n", encoding="utf-8")
    row = pulse.snapshot("2026-08-29T11:00:00+00:00")
    assert row["results_this_hour"] == ["P-new"]
    assert "P-new" in row["summary"]


def test_a_corrupt_file_does_not_kill_the_pulse(lab):
    root, rnd = lab
    (root / "best.json").write_text("{ this is not json", encoding="utf-8")
    (rnd / "program.jsonl").write_text("not json\n{\"id\":\"ok\",\"status\":\"queued\"}\n",
                                       encoding="utf-8")
    row = pulse.snapshot(None)
    assert row["queued"] == ["ok"]
    assert row["champion_score"] is None


def test_the_watchdog_keeps_the_pulse_alive():
    """Guards are code, not memory: the watchdog must relaunch pulse.py."""
    wd = (REPO / "research/system06/watchdog.ps1").read_text(encoding="utf-8", errors="ignore")
    assert "pulse.py" in wd


def test_the_dashboard_publishes_the_pulse():
    ms = (REPO / "research/system06/preview/mock_server.py").read_text(
        encoding="utf-8", errors="ignore")
    assert "pulse.jsonl" in ms and '"pulse"' in ms
