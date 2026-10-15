"""System 10 review round 2, items 1-2 (R6 step 1, R3): the paper book freeze and the measured
swap band are INERT without their flag files."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "research/system10/tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from system010_conditioned_rl import search as S  # noqa: E402

from system010_conditioned_rl import overfit as O  # noqa: E402
from system010_conditioned_rl import paper as P  # noqa: E402

BAR = P.BAR_NS


def _swap_env(tmp_path, monkeypatch, inc_score, new_score, inc_eligible=True, rows_extra=()):
    monkeypatch.setattr(P, "CONFIG", tmp_path / "config.json")
    monkeypatch.setattr(P, "FREEZE_FLAG", tmp_path / "FREEZE_PAPER_SWAPS")
    monkeypatch.setattr(P, "BAND_FLAG", tmp_path / "ENABLE_MEASURED_BAND")
    monkeypatch.setattr(O, "SWAP_BAND", tmp_path / "swap_band.json")
    rows = [{"id": "inc", "score": inc_score, "eligible": inc_eligible},
            {"id": "new", "score": new_score, "eligible": True}] + list(rows_extra)
    monkeypatch.setattr(P.S, "ledger", lambda: rows)
    monkeypatch.setattr(P.S, "current_release", lambda w: {"n": 9, "id": "new", "label": "x", "cfg": {"slots": 5}})
    cfg = {"start_ns": 0, "release": 8, "release_id": "inc", "cfg": {"slots": 3}}
    fr = {"AAAUSDT": {"ns": np.array([5 * BAR], dtype=np.int64)}}
    return cfg, fr


def test_freeze_flag_stops_every_swap(tmp_path, monkeypatch):
    cfg, fr = _swap_env(tmp_path, monkeypatch, 0.300, 0.100, inc_eligible=False)
    P.FREEZE_FLAG.write_text("")
    out = P.adopt_champion(cfg, fr)
    assert out["release_id"] == "inc" and len(out["segments"]) == 1 and not P.CONFIG.exists()
    P.FREEZE_FLAG.unlink()
    assert P.adopt_champion(cfg, fr)["release_id"] == "new"           # without it: as before


def test_freeze_flag_stops_book_releases(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(P, "FREEZE_FLAG", tmp_path / "FREEZE_PAPER_SWAPS")
    monkeypatch.setattr(P, "BOOK_FLAG", tmp_path / "ENABLE_BOOK_RELEASES")
    monkeypatch.setattr(P, "BOOK_DIR", tmp_path)
    (tmp_path / "ENABLE_BOOK_RELEASES").write_text("")
    (tmp_path / "FREEZE_PAPER_SWAPS").write_text("")
    (tmp_path / "book_0001.json").write_text("{}")
    monkeypatch.setattr(P.S, "releases", lambda: called.append(1) or [])
    cfgx = {"segments": [{"release_id": "x"}]}
    assert P.adopt_book(cfgx, {}) is cfgx and not called


def _band_file(v, age_days=0):
    at = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat(timespec="seconds")
    O.SWAP_BAND.write_text(json.dumps({"at": at, "median": v, "rows": 615}))


def test_measured_band_is_ignored_without_its_flag(tmp_path, monkeypatch):
    cfg, fr = _swap_env(tmp_path, monkeypatch, 0.200, 0.250)
    _band_file(0.10)
    assert P.swap_band(P.S.ledger()) == P.SWAP_BAND == 0.02
    assert P.adopt_champion(cfg, fr)["release_id"] == "new"           # +0.05 > 0.02: swaps as today


def test_measured_band_with_its_flag(tmp_path, monkeypatch):
    cfg, fr = _swap_env(tmp_path, monkeypatch, 0.200, 0.250)
    P.BAND_FLAG.write_text("")
    _band_file(0.10)
    assert P.swap_band(P.S.ledger()) == 0.10
    assert P.adopt_champion(cfg, fr)["release_id"] == "inc"           # +0.05 < 0.10: no swap
    cfg, fr = _swap_env(tmp_path, monkeypatch, 0.200, 0.320)
    assert P.adopt_champion(cfg, fr)["release_id"] == "new"           # +0.12 > 0.10
    _band_file(0.005)
    assert P.swap_band([]) == 0.02                                     # never below the default


def _paired(n, diff, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        ys = {str(y): {"return": float(rng.normal(0.2, 0.1)), "max_dd": 0.1} for y in O.YEARS}
        cy = {k: {**v, "return": v["return"] + diff[i % len(diff)]} for k, v in ys.items()}
        out.append({"id": f"p{i}", "years": ys, "confirm": {"years": cy}})
    return out


def test_measured_band_falls_back_to_the_ledger_when_the_file_is_stale(tmp_path, monkeypatch):
    rows = _paired(40, [0.02])
    cfg, fr = _swap_env(tmp_path, monkeypatch, 0.200, 0.250, rows_extra=rows)
    P.BAND_FLAG.write_text("")
    _band_file(0.50, age_days=30)
    assert abs(P.swap_band(rows) - O.swap_band(rows)["median"]) < 1e-12
    assert 0.015 < O.swap_band(rows)["median"] < 0.025      # +2 pp every year moves the law by ~2 pp


def test_swap_band_measurement():
    rows = _paired(100, [0.0, 0.05, 0.1, 0.2])
    b = O.swap_band(rows + [{"id": "x", "years": rows[0]["years"]}])   # unconfirmed rows are skipped
    assert b["rows"] == 100 and b["median"] <= b["p75"] <= b["p90"]
    assert O.swap_band(rows[:10]) is None
    assert O.band_due(Path("does/not/exist.json"))


def test_overfit_writes_no_band_without_its_flag(tmp_path, monkeypatch):
    rows = _paired(40, [0.1])
    for r in rows:
        r.update({"cfg": {}, "eligible": False})
    monkeypatch.setattr(O, "BAND_FLAG", tmp_path / "ENABLE_MEASURED_BAND")
    monkeypatch.setattr(O, "SWAP_BAND", tmp_path / "swap_band.json")
    monkeypatch.setattr(S, "ledger", lambda: rows)
    monkeypatch.setattr(S, "releases", lambda: [])
    monkeypatch.setattr(sys, "argv", ["overfit", "--quiet", "--out", str(tmp_path / "of.json")])
    O.main()
    assert not O.SWAP_BAND.exists() and (tmp_path / "of.json").exists()
    O.BAND_FLAG.write_text("")
    O.main()
    assert json.loads(O.SWAP_BAND.read_text())["rows"] == 40
