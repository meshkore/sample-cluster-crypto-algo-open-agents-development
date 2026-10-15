"""Paper book live rules (2026-10-15): bars wait for their breadth channel; champion swaps need a margin."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "research/system10/tools"))

from system010_conditioned_rl import paper as P  # noqa: E402

BAR = P.BAR_NS


def _world(n=6, t0=10 * BAR):
    ns = t0 + np.arange(n, dtype=np.int64) * BAR
    return SimpleNamespace(per={"AAAUSDT": {"ns": ns}, "BBBUSDT": {"ns": ns}})


def _fresh(world, v):
    n = len(world.per["AAAUSDT"]["ns"])
    return {"enter": {s: np.full(n, v) for s in world.per}, "keep": {s: np.full(n, not v) for s in world.per},
            "strength": {s: np.full(n, 0.01) for s in world.per}, "size": {s: np.ones(n) for s in world.per}}


def test_a_bar_without_its_channel_is_not_decided_nor_frozen():
    w = _world()
    ns = w.per["AAAUSDT"]["ns"]
    ready = {s: int(ns[3]) for s in w.per}                 # channel covers bars 0..3
    fr = {}
    x, added = P.stitch(w, int(ns[0]), _fresh(w, True), fr, ready)
    assert added == 2 * 4                                   # only the four complete bars per coin
    assert list(fr["AAAUSDT"]["ns"]) == list(ns[:4])
    assert not x["enter"]["AAAUSDT"][4:].any()             # late bars: no entry ...
    assert x["keep"]["AAAUSDT"][4:].all()                  # ... and held positions are kept


def test_late_bars_are_decided_once_the_channel_arrives():
    w = _world()
    ns = w.per["AAAUSDT"]["ns"]
    fr = {}
    P.stitch(w, int(ns[0]), _fresh(w, False), fr, {s: int(ns[3]) for s in w.per})
    x, added = P.stitch(w, int(ns[0]), _fresh(w, True), fr, {s: int(ns[5]) for s in w.per})
    assert added == 2 * 2
    assert not x["enter"]["AAAUSDT"][:4].any()             # frozen bars never change
    assert x["enter"]["AAAUSDT"][4:].all()                 # the newly complete ones are decided now


def _swap_env(tmp_path, monkeypatch, inc_score, new_score, inc_eligible=True):
    monkeypatch.setattr(P, "CONFIG", tmp_path / "config.json")
    rows = [{"id": "inc", "score": inc_score, "eligible": inc_eligible},
            {"id": "new", "score": new_score, "eligible": True}]
    monkeypatch.setattr(P.S, "ledger", lambda: rows)
    monkeypatch.setattr(P.S, "current_release", lambda w: {"n": 9, "id": "new", "label": "x", "cfg": {"slots": 5}})
    cfg = {"start_ns": 0, "release": 8, "release_id": "inc", "cfg": {"slots": 3}}
    fr = {"AAAUSDT": {"ns": np.array([5 * BAR], dtype=np.int64)}}
    return cfg, fr


def test_no_swap_inside_the_noise_band(tmp_path, monkeypatch):
    cfg, fr = _swap_env(tmp_path, monkeypatch, 0.200, 0.200 + P.SWAP_BAND / 2)
    out = P.adopt_champion(cfg, fr)
    assert out["release_id"] == "inc" and len(out["segments"]) == 1


def test_swap_beyond_the_band_starts_at_the_next_undecided_bar(tmp_path, monkeypatch):
    cfg, fr = _swap_env(tmp_path, monkeypatch, 0.200, 0.200 + 2 * P.SWAP_BAND)
    out = P.adopt_champion(cfg, fr)
    assert out["release_id"] == "new" and out["segments"][-1]["from_ns"] == 6 * BAR
    assert json.loads(P.CONFIG.read_text())["release"] == 9


def test_an_ineligible_incumbent_is_replaced_at_once(tmp_path, monkeypatch):
    cfg, fr = _swap_env(tmp_path, monkeypatch, 0.300, 0.100, inc_eligible=False)
    assert P.adopt_champion(cfg, fr)["release_id"] == "new"
