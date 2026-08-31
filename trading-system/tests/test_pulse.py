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


def test_only_one_pulse_daemon_can_hold_the_claim():
    """A manual start racing the watchdog produced two daemons on 2026-08-29; duplicate
    hourly lines would make the trace lie about its own cadence."""
    first = pulse._claim_singleton()
    assert first is not None, "the first claim must succeed"
    try:
        assert pulse._claim_singleton() is None, "a second daemon must refuse to run"
    finally:
        first.close()
    # and the claim must be reusable once released - a crash must not silence the pulse
    again = pulse._claim_singleton()
    assert again is not None
    again.close()


def test_the_singleton_port_avoids_the_reserved_ranges():
    assert pulse.SINGLETON_PORT != 8799            # mock_server, deliberately off
    assert not (5570 <= pulse.SINGLETON_PORT <= 5589)   # MeshKore daemon range


def test_a_half_written_heartbeat_is_retried_not_reported_as_death(lab, monkeypatch):
    """Observed 2026-08-31: the pulse reported 'no heartbeat file' for a runner that
    was demonstrably training - it had caught the file mid-rewrite. A transient read
    must never read as a dead daemon."""
    root, rnd = lab
    hb = root / "autotest_live.json"
    hb.write_text("{ half written", encoding="utf-8")
    calls = {"n": 0}
    real_read = type(hb).read_text

    def flaky(self, *a, **kw):
        if self == hb:
            calls["n"] += 1
            if calls["n"] < 2:
                return "{ truncated"
            return '{"state": "running", "detail": "training", "heartbeat": "2026-08-31T00:00:00+00:00"}'
        return real_read(self, *a, **kw)

    monkeypatch.setattr(type(hb), "read_text", flaky)
    got = pulse._load(hb)
    assert got is not None and got["state"] == "running"
    assert calls["n"] >= 2, "the reader must retry before giving up"


def test_a_genuinely_missing_file_still_returns_none(lab):
    root, rnd = lab
    assert pulse._load(root / "does-not-exist.json") is None
