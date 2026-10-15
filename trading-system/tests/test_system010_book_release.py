"""Book releases (book audit 2026-10-15, phase 4) are inert unless their flag files exist."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "research/system10/tools"))

from system010_conditioned_rl import book_worker as W  # noqa: E402
from system010_conditioned_rl import paper as P  # noqa: E402
from system010_conditioned_rl import review as RV  # noqa: E402
from system010_conditioned_rl import search as S  # noqa: E402

REL = {"regime_ma": 100, "b_up": 0.5, "b_down": 0.0, "selector": True, "horizon": 768, "size_down": 0.75,
       "exit": "learned", "features": "full", "slots": 5, "size_signal": 0.01, "dd_scale": 0.35,
       "scale_in": True, "stop": 0.12, "mom_days": 90, "mom_rank": 7}
START = 1_791_921_600_000_000_000


def _setup(tmp_path, monkeypatch, flag: bool, book: dict | None = None, **extra):
    bdir = tmp_path / "book_releases"
    bdir.mkdir()
    row = {"n": 1, "signal_release": 34, "signal_release_id": "d2874abbc2", "signal_id": "x",
           "book": book or {"slots": 8, "stop": 0.12, "dd_scale": 0.25, "size_signal": 0.01, "scale_in": True,
                            "port_vol": 0.3},
           "gain": 0.05, **extra}
    (bdir / "book_0001.json").write_text(json.dumps(row), encoding="utf-8")
    monkeypatch.setattr(P, "BOOK_DIR", bdir)
    monkeypatch.setattr(P, "BOOK_FLAG", tmp_path / "ENABLE_BOOK_RELEASES")
    monkeypatch.setattr(P, "CONFIG", tmp_path / "config.json")
    monkeypatch.setattr(S, "releases", lambda: [{"n": 34, "id": "d2874abbc2", "cfg": REL}])
    if flag:
        (tmp_path / "ENABLE_BOOK_RELEASES").write_text("", encoding="utf-8")
    cfgx = {"start_ns": START, "release": 34, "release_id": "d2874abbc2", "cfg": dict(REL),
            "segments": [{"from_ns": START, "release": 34, "release_id": "d2874abbc2", "cfg": dict(REL)}]}
    fr = {"BTCUSDT": {"ns": np.array([START, START + P.BAR_NS], dtype=np.int64)}}
    return cfgx, fr


def test_paper_ignores_book_releases_without_the_flag(tmp_path, monkeypatch):
    cfgx, fr = _setup(tmp_path, monkeypatch, flag=False)
    before = json.dumps(cfgx, sort_keys=True)
    out = P.adopt_book(cfgx, fr)
    assert json.dumps(out, sort_keys=True) == before
    assert not (tmp_path / "config.json").exists()


def test_paper_applies_book_release_with_the_flag_as_a_new_segment(tmp_path, monkeypatch):
    cfgx, fr = _setup(tmp_path, monkeypatch, flag=True)
    out = P.adopt_book(cfgx, fr)
    seg = out["segments"][-1]
    assert len(out["segments"]) == 2 and seg["book"] == 1
    assert seg["from_ns"] == START + 2 * P.BAR_NS            # first bar not yet decided
    sig = {k: v for k, v in REL.items() if k not in S.MM_KEYS}
    assert {k: v for k, v in seg["cfg"].items() if k not in S.MM_KEYS} == sig   # signals untouched
    assert "mom_rank" not in seg["cfg"] and seg["cfg"]["port_vol"] == 0.3 and seg["cfg"]["slots"] == 8
    assert S.mm_kwargs(seg["cfg"])["port_vol"] == 0.3
    assert out["release_id"] == "d2874abbc2" and (tmp_path / "config.json").exists()
    again = P.adopt_book(out, fr)
    assert len(again["segments"]) == 2                        # idempotent


def test_paper_refuses_meta_small_gain_other_signals_and_lost_forecast(tmp_path, monkeypatch):
    for kw in ({"book": {"slots": 5, "size_signal": 0.01, "meta": [0.5, 1.5]}}, {"gain": 0.01},
               {"signal_release_id": "ea1f94dba8"}, {"book": {"slots": 5}}):
        sub = tmp_path / str(abs(hash(json.dumps(kw))))
        sub.mkdir()
        cfgx, fr = _setup(sub, monkeypatch, flag=True, **kw)
        assert len(P.adopt_book(cfgx, fr)["segments"]) == 1, kw


def test_review_book_pbo_is_off_without_its_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(RV, "BOOK_PBO_FLAG", tmp_path / "ENABLE_BOOK_PBO")

    def boom(*a, **k):
        raise AssertionError("subprocess must not run")
    monkeypatch.setattr(RV.subprocess, "run", boom)
    assert RV.book_overfit() is None


def test_book_pbo_on_a_synthetic_ledger(tmp_path, monkeypatch):
    L = W._lab_mod()
    led = tmp_path / "book_trials.jsonl"
    rng = np.random.default_rng(0)
    with led.open("w", encoding="utf-8") as fh:
        for i in range(30):
            ys = {str(y): {"return": 0.1, "max_dd": 0.1, "trades": 100,
                           "monthly": [round(float(x), 5) for x in rng.normal(0.01, 0.05, 12)]} for y in L.YEARS}
            fh.write(json.dumps({"signal_id": "s", "id": f"b{i}", "book": {"slots": i}, "years": ys}) + "\n")
    monkeypatch.setattr(L, "LEDGER", led)
    monkeypatch.setattr(W, "BOOK_OVERFIT", tmp_path / "book_overfit.json")
    doc = W.book_pbo("s")
    assert doc["books"] == 30 and 0.0 <= doc["pbo"] <= 1.0
    assert doc["refuses"] == (doc["pbo"] > 0.5)      # pure noise: PBO near 0.5
    assert json.loads((tmp_path / "book_overfit.json").read_text())["pbo"] == doc["pbo"]


def test_worker_never_proposes_the_meta_sizer():
    L = W._lab_mod()
    props = W.proposals(L, {"slots": 5, "size_signal": 0.01})
    assert props and not any("meta" in b for b in props)
    assert any("port_vol" in b for b in props) and any("atr_trail" in b for b in props)
