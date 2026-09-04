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


# --- neglect: the difference between "nothing is broken" and "nothing is happening" ---
# Every case below is an hour that actually happened on 2026-09-04 and read as healthy.

def _ago(hours):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def test_an_idle_runner_with_a_free_gpu_is_reported_as_not_moving(lab):
    row = pulse.snapshot(None)
    assert any("NOTHING to run" in n for n in row["neglected"])
    assert "NOT MOVING" in row["summary"]


def test_a_row_left_in_failed_is_never_quietly_forgotten(lab):
    """P47 crashed on a runner bug and sat in `failed` while the pulse said the
    agenda was empty. Empty and broken are not the same word."""
    root, rnd = lab
    (rnd / "program.jsonl").write_text(json.dumps(
        {"id": "P47", "status": "failed", "error": "KeyError: 'arms'"}) + "\n",
        encoding="utf-8")
    row = pulse.snapshot(None)
    assert any("P47 FAILED" in n and "KeyError" in n for n in row["neglected"])


def test_a_finished_experiment_nobody_read_is_flagged_once_it_goes_cold(lab):
    root, rnd = lab
    (rnd / "program.jsonl").write_text("\n".join([
        json.dumps({"id": "P46", "status": "done", "finished_at": _ago(5), "result": ""}),
        json.dumps({"id": "P45", "status": "done", "finished_at": _ago(5),
                    "result": "WIN, 4/4 seeds"}),
        json.dumps({"id": "P48", "status": "running"}),
    ]) + "\n", encoding="utf-8")
    row = pulse.snapshot(None)
    flagged = " ".join(row["neglected"])
    assert "P46" in flagged, "measured but never interpreted"
    assert "P45" not in flagged, "a written reading closes the obligation"


def test_a_freshly_finished_experiment_is_given_time_to_be_judged(lab):
    """The agent is not expected to be awake the instant a run lands. Crying wolf at
    minute one is how a warning gets ignored when it is real."""
    root, rnd = lab
    (rnd / "program.jsonl").write_text("\n".join([
        json.dumps({"id": "P46", "status": "done", "finished_at": _ago(0.2), "result": ""}),
        json.dumps({"id": "P48", "status": "running"}),
    ]) + "\n", encoding="utf-8")
    assert pulse.snapshot(None)["neglected"] == []


def test_a_manual_row_nobody_launched_is_chased(lab):
    """A kind:"manual" row is invisible to the runner by design, so nothing but this
    will ever notice that it has been waiting."""
    root, rnd = lab
    (rnd / "program.jsonl").write_text("\n".join([
        json.dumps({"id": "P47", "kind": "manual", "status": "queued",
                    "created_at": _ago(4)}),
        json.dumps({"id": "P48", "status": "running"}),
    ]) + "\n", encoding="utf-8")
    assert any("P47" in n and "by hand" in n for n in pulse.snapshot(None)["neglected"])


def test_a_busy_well_kept_lab_is_reported_as_silent(lab):
    """The flag has to be able to say nothing, or it says nothing."""
    root, rnd = lab
    (rnd / "program.jsonl").write_text("\n".join([
        json.dumps({"id": "P48", "status": "running"}),
        json.dumps({"id": "P49", "status": "queued", "kind": "train_ab"}),
        json.dumps({"id": "P45", "status": "done", "finished_at": _ago(9),
                    "result": "REFUTED, both seeds"}),
    ]) + "\n", encoding="utf-8")
    row = pulse.snapshot(None)
    assert row["neglected"] == []
    assert "NOT MOVING" not in row["summary"]


def test_the_landing_line_counts_the_arms_that_were_actually_measured(lab):
    """P46 measured five arms and the pulse announced "(0 arms)": it was counting the
    experiment's key on the result's row. A trace that undercounts its own work is
    how three hours of finished research read as an empty afternoon."""
    root, rnd = lab
    (rnd / "program_results.jsonl").write_text(json.dumps(
        {"id": "P46", "at": "2026-09-04T09:17:47+00:00",
         "summary": {"baseline": {}, "bar 0.80": {}, "bar 0.85": {},
                     "uncompensated": {}, "control": {}}}) + "\n", encoding="utf-8")
    assert "P46 (5 arms)" in pulse.snapshot("2026-09-04T00:00:00+00:00")["summary"]


def test_a_deliberate_brake_is_reported_until_it_is_released(lab):
    """STOP_AUTOTEST hands the GPU to one job - a correct thing to do, and a landmine.
    Nothing but a person deleting the file brings the runner back, and a stopped runner
    looks exactly like a finished one. Set on 2026-09-04 to give P47 the card."""
    root, rnd = lab
    (rnd / "program.jsonl").write_text(
        json.dumps({"id": "P48", "status": "running"}) + "\n", encoding="utf-8")
    assert pulse.snapshot(None)["neglected"] == [], "no brake, nothing to say"
    (root / "STOP_AUTOTEST").write_text("P47 holds the GPU", encoding="utf-8")
    flagged = pulse.snapshot(None)["neglected"]
    assert any("STOP_AUTOTEST" in n and "deleted" in n for n in flagged)
