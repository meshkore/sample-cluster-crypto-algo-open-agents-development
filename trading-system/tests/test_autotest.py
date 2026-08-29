"""The autonomous experiment runner must encode the guards, not merely remember them."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "autotest", REPO / "research" / "system06" / "autotest.py")
autotest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(autotest)


def test_deep_drawdown_is_flagged_not_rejected():
    """The operator removed the hard cap on 2026-08-28: minimise drawdown, do not bound it.

    So a deep arm must still be REPORTED - never silently discarded - and the flag line
    must stay fixed before the scores are visible, because a line that moves afterwards
    reports nothing. It sits below the old 25% mandate so the warning arrives early.
    """
    assert autotest.DD_REJECT is None, "no arm may be discarded on drawdown any more"
    assert 0.20 <= autotest.DD_FLAG < 0.25


def test_control_tolerance_cannot_swallow_the_effect_it_checks():
    """A control tolerance wider than the effect would validate a broken harness.

    Judged against the LIVE control - the one expecting a real, non-zero effect.
    After the 2026-08-29 adoption the money arm expects ~0 (its lever is inside the
    shipping config), so measuring the tolerance against it would compare against
    nothing at all.
    """
    live = [v for v in autotest.CONTROL_EXPECT.values() if abs(v) > 1e-9]
    assert live, ("no live positive control: every control arm expects zero, so a "
                  "broken harness would pass unnoticed")
    assert autotest.CONTROL_TOL < 2 * min(live), (
        "tolerance must be tight enough that a dead lever fails the check")


def test_program_round_trips_without_losing_rows(tmp_path, monkeypatch):
    """The program file is the queue; a lossy rewrite would silently drop experiments."""
    prog = tmp_path / "program.jsonl"
    monkeypatch.setattr(autotest, "PROGRAM", prog)
    rows = [{"id": f"P{i:02d}", "status": "queued", "priority": i} for i in range(1, 6)]
    autotest._write_program(rows)
    assert autotest._read_program() == rows

    autotest._set_status("P03", "done", verdict="null result")
    back = {r["id"]: r for r in autotest._read_program()}
    assert len(back) == 5, "no experiment may vanish when one is updated"
    assert back["P03"]["status"] == "done" and back["P03"]["verdict"] == "null result"
    assert back["P01"]["status"] == "queued", "other rows must be untouched"


def test_a_corrupt_line_does_not_destroy_the_queue(tmp_path, monkeypatch):
    """One bad row must not take the runner down - it runs unattended for days."""
    prog = tmp_path / "program.jsonl"
    prog.write_text('{"id": "P01", "status": "queued"}\n{not json\n'
                    '{"id": "P02", "status": "queued"}\n', encoding="utf-8")
    monkeypatch.setattr(autotest, "PROGRAM", prog)
    got = autotest._read_program()
    assert [r["id"] for r in got] == ["P01", "P02"]


def test_the_queue_is_ordered_by_priority(tmp_path, monkeypatch):
    prog = tmp_path / "program.jsonl"
    monkeypatch.setattr(autotest, "PROGRAM", prog)
    autotest._write_program([
        {"id": "late", "status": "queued", "priority": 9},
        {"id": "first", "status": "queued", "priority": 1},
        {"id": "done", "status": "done", "priority": 0},
    ])
    queued = [r for r in autotest._read_program() if r["status"] == "queued"]
    queued.sort(key=lambda r: r.get("priority", 99))
    assert [r["id"] for r in queued] == ["first", "late"]


def test_shipped_program_is_valid_and_starts_with_the_structural_diagnosis():
    """The real queue must parse, and lead with the idea the evidence points at."""
    rows = [json.loads(l) for l in
            (REPO / "research/system06/rnd/program.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    assert rows, "the program must not be empty - the runner would idle forever"
    for r in rows:
        variants = r.get("arms") or r.get("train_variants")
        assert variants, f"{r['id']} has neither arms nor train_variants to compare"
        assert r.get("seeds"), f"{r['id']} names no seeds"
        assert r.get("why"), f"{r['id']} must say why it is worth a GPU hour"
    top = min(rows, key=lambda r: r.get("priority", 99))
    assert top["agenda"].startswith("A49"), (
        "the first experiment should attack the flat-year ceiling, the measured constraint")
    # Every experiment needs a baseline first, or pairing is meaningless.
    for r in rows:
        variants = r.get("arms") or r.get("train_variants")
        assert next(iter(variants)) == "baseline", f"{r['id']} must open with a baseline"


def test_unknown_levers_are_caught_before_gpu_is_spent():
    """The brain ends in **_ignored, so an unrecognised lever is SWALLOWED, not rejected.

    That produced a full wasted experiment: P05 tested `trend_soft` three ways and all
    three read INERT, because the lever had been built 55 minutes AFTER the runner
    started and Python imports a module once per process. Read carelessly it would have
    refuted the operator's idea on the strength of a stale import.
    """
    assert autotest.unknown_levers({"money_model": 0.5, "max_positions": 3}) == []
    assert autotest.unknown_levers({"nonexistent_lever": 1.0}) == ["nonexistent_lever"]
    # Mixed: report only the ones that would vanish.
    assert autotest.unknown_levers(
        {"money_model": 0.5, "typo_lever": 1, "also_wrong": 2}) == ["also_wrong", "typo_lever"]


def test_every_lever_in_the_shipped_program_is_real():
    """A queued experiment naming a lever the brain does not accept is dead on arrival."""
    import json as _json

    rows = [_json.loads(l) for l in
            (REPO / "research/system06/rnd/program.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    # Only rows that will actually RUN. Finished rows are historical record - P01 really
    # did name a lever that did not exist, and that fact must stay in the ledger rather
    # than be tidied away; blocked rows legitimately name levers not yet built.
    import inspect

    from quantlab_system06 import train as _train
    train_params = set(inspect.signature(_train.train).parameters)

    for r in rows:
        if r.get("status") not in ("queued", "running"):
            continue
        # kind "ab": arms are BRAIN kwargs — the **_ignored trap applies.
        for label, kw in (r.get("arms") or {}).items():
            bad = autotest.unknown_levers(kw)
            assert not bad, f"{r['id']} arm {label!r} names levers the brain ignores: {bad}"
        # kind "train_ab": variants are train() kwargs — a typo would raise only after
        # hours of data loading, so the runner (and this test) check the signature first.
        for label, kw in (r.get("train_variants") or {}).items():
            bad = sorted(set(kw) - train_params)
            assert not bad, f"{r['id']} variant {label!r} names train() params that do not exist: {bad}"


def test_a_restart_does_not_strand_the_experiment_it_interrupted(tmp_path, monkeypatch):
    """A row left `running` by a killed process would be skipped forever.

    The runner only picks up `queued` rows, and restarting is routine - Python holds
    imports for the life of a process, so building any lever requires one.
    """
    prog = tmp_path / "program.jsonl"
    monkeypatch.setattr(autotest, "PROGRAM", prog)
    autotest._write_program([
        {"id": "interrupted", "status": "running", "priority": 0},
        {"id": "waiting", "status": "queued", "priority": 1},
        {"id": "finished", "status": "done", "priority": 2},
        {"id": "dropped", "status": "cancelled", "priority": 3},
    ])
    assert autotest.recover_orphans() == ["interrupted"]
    back = {r["id"]: r for r in autotest._read_program()}
    assert back["interrupted"]["status"] == "queued"
    assert back["interrupted"].get("recovered_at"), "the recovery must be visible in the record"
    # Nothing else may be disturbed - a finished verdict must never be re-opened.
    assert back["waiting"]["status"] == "queued"
    assert back["finished"]["status"] == "done"
    assert back["dropped"]["status"] == "cancelled"
    # Idempotent: a second start with nothing in flight frees nothing.
    assert autotest.recover_orphans() == []


def test_progress_callback_matches_the_convention_train_actually_uses(tmp_path, monkeypatch):
    """train._emit calls `on_progress(ev)` with ONE POSITIONAL DICT, inside `except: pass`.

    So a callback with the wrong signature fails silently on every call. The first version
    of this heartbeat was declared `(**ev)`, raised TypeError each time, and left the
    heartbeat frozen through a 25-minute training run - indistinguishable from a hang.
    Telemetry that cannot break training also cannot report that it is broken.
    """
    import inspect

    from quantlab_system06 import train

    # The real caller's shape, read from the source rather than assumed.
    assert "on_progress(ev)" in inspect.getsource(train.train), (
        "train's calling convention changed; this heartbeat must follow it")

    monkeypatch.setattr(autotest, "HEARTBEAT", tmp_path / "beat.json")
    last = [0.0]
    # Called exactly as train calls it: one positional dict.
    assert autotest.progress_beat({"stage": "training", "epoch": 7, "epochs": 50},
                                  "P99", 1234, last) is True
    written = json.loads((tmp_path / "beat.json").read_text(encoding="utf-8"))
    assert "epoch 7/50" in written["detail"] and written["experiment"] == "P99"

    # Throttled: an immediate second call must not rewrite.
    assert autotest.progress_beat({"stage": "training", "epoch": 8, "epochs": 50},
                                  "P99", 1234, last) is False
    # ...and after the window it writes again.
    last[0] = 0.0
    assert autotest.progress_beat({"stage": "evaluating"}, "P99", 1234, last) is True
    assert "evaluating" in json.loads(
        (tmp_path / "beat.json").read_text(encoding="utf-8"))["detail"]


def test_train_ab_refuses_kwargs_train_does_not_accept(tmp_path, monkeypatch):
    """A training variant naming a kwarg train() cannot see is the stale-import trap in
    a new coat - it must fail loudly BEFORE any GPU is spent, exactly like unknown_levers.
    """
    import json as _json

    best = tmp_path / "best.json"
    best.write_text(_json.dumps({
        "config": {"threshold": 0.03, "window": 96, "epochs": 1, "lr": 1e-3, "dropout": 0.1},
        "band": {"enter": 0.75, "exit_": 0.25, "min_hold": 16},
        "risk": {"max_positions": 2, "position_fraction": 0.15},
    }), encoding="utf-8")
    monkeypatch.setattr(autotest, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="does not accept"):
        autotest.run_train_ab({
            "id": "T-test", "seeds": [1],
            "train_variants": {"baseline": {}, "broken": {"no_such_train_flag": 1}},
        })


def test_the_positive_control_matches_the_shipping_config():
    """A control arm measures a delta FROM the shipping config, so its expected value
    must be re-derived whenever that config changes.

    The failure this pins: after the 2026-08-29 adoption folded money_model 0.5 into
    the shipping config, the money control became a no-op against itself (P20 measured
    -0.0034) while the table still expected +0.0228. A control that cannot fail is not
    a control - so any lever already present in best.json must expect ~0.
    """
    import json

    best = json.loads((REPO / "research/system06/best.json").read_text(encoding="utf-8"))
    risk = best.get("risk") or {}
    for label, expected in autotest.CONTROL_EXPECT.items():
        lever = label.split()[0]                      # "money" / "ceiling"
        in_shipping = (lever == "money" and float(risk.get("money_model") or 0) > 0)
        if in_shipping:
            assert abs(expected) < 1e-9, (
                f"control {label!r} expects {expected} but its lever is already in the "
                "shipping config, so it can only measure ~0")
