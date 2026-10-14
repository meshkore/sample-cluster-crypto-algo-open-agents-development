"""System 10 market health: bounded, falls in a crash, and the book is unchanged without it."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "research/system10/tools"))

from system010_conditioned_rl import health as H  # noqa: E402

BAR = 900 * 10**9
START = int(np.datetime64("2022-01-01T00:00", "ns").astype("int64"))


def _series(n=130 * 96, coins=6, crash_at=None, seed=1):
    rng = np.random.default_rng(seed)
    common = rng.normal(0, 0.002, n)
    out = {}
    for k in range(coins):
        r = 0.7 * common + rng.normal(0, 0.003, n)
        if crash_at is not None:
            m = len(r[crash_at:crash_at + 16])
            r[crash_at:crash_at + 16] = -0.02 + rng.normal(0, 0.001, m)     # ~-28% in 4 h, all coins
        name = "BTCUSDT" if k == 0 else f"C{k}USDT"
        out[name] = (START + np.arange(n, dtype=np.int64) * BAR, 100 * np.exp(np.cumsum(r)))
    return out


def test_score_is_bounded():
    h = H.history(_series())
    assert np.isfinite(h["score"]).all()
    assert (h["score"] >= 0).all() and (h["score"] <= 100).all()
    for k in ("crash", "trend", "vol", "breadth", "corr"):
        assert (h[k][1] >= 0).all() and (h[k][1] <= 100).all()


def test_score_falls_in_a_synthetic_crash():
    n, at = 130 * 96, 120 * 96
    h = H.history(_series(n=n, crash_at=at))
    before = h["score"][at - 96:at]
    during = h["score"][at + 8:at + 17]
    assert np.median(before) >= 60
    assert during.min() < 15 and H.level_of(float(during.min())) == "danger"
    doc = H.current(_series(n=at + 12, crash_at=at), trades=[], was_halted=False)   # newest bar inside the crash
    assert doc["score"] < 25 and doc["level"] == "danger" and doc["recommendation"] == "trade"
    streak = H.current(_series(), trades=[-0.02] * 12, was_halted=False)
    assert streak["guard"]["halted"] and streak["level"] == "halt" and streak["recommendation"] == "halt"
    assert {c["name"] for c in doc["components"]} == {"crash", "trend", "vol", "breadth", "corr", "book"}


def _book_world(seed=3):
    rng = np.random.default_rng(seed)
    per = {}
    for k, s in enumerate(("AAAUSDT", "BBBUSDT", "CCCUSDT")):
        n = 6000 - 500 * k
        ns = START + (np.arange(n) + 500 * k).astype(np.int64) * BAR
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
        year = ns.astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970
        per[s] = {"ns": ns, "close": close, "prob": rng.random(n), "year": year}
    masks = {s: rng.random(len(d["ns"])) < 0.05 for s, d in per.items()}
    keep = {s: rng.random(len(d["ns"])) < 0.97 for s, d in per.items()}
    strength = {s: rng.normal(0.004, 0.006, len(d["ns"])) for s, d in per.items()}
    size = {s: np.where(rng.random(len(d["ns"])) < 0.5, 1.0, 0.75) for s, d in per.items()}
    return per, masks, keep, strength, size


def _book(**extra):
    import conditions as C
    per, masks, keep, strength, size = _book_world()
    old = C.HORIZON
    C.HORIZON = 768
    try:
        return C.book_year(per, masks, 2022, {"enter": 0.5}, {"trail_stop": 0.1, "stop_loss": 0.163},
                           keep=keep, size=size, keep_min_hold=16, slots=2, stop=0.12, dd_scale=0.35,
                           strength=strength, size_signal=0.01, scale_in=True, detail=True, **extra)
    finally:
        C.HORIZON = old


def _digest(r):
    return hashlib.sha256(json.dumps(r, sort_keys=True, default=str).encode()).hexdigest()


# book_year's output on _book_world, computed with conditions.py BEFORE the guard hook existed
PINNED = "1b6c9164492849de5f9749ed27a7f71758640fe831865511bbcabaecbbd0f47b"


def test_book_without_guard_is_byte_identical():
    assert _digest(_book()) == PINNED
    assert _digest(_book(guard=None)) == PINNED
    assert _digest(_book(guard=lambda t, tr: "trade")) == PINNED


def test_guard_blocks_and_flattens():
    blocked = _book(guard=lambda t, tr: "block")
    assert blocked["trades"] == 0 and blocked["return"] == 0
    base = _book()
    cut = START + 2000 * BAR
    flat = _book(guard=lambda t, tr: "flatten" if t >= cut else "trade")
    assert not flat["positions"]
    assert any(f["reason"] == "health halt" for f in flat["fills"]) or not base["positions"]
    assert all(f["t"] < cut or f["side"] == "SELL" for f in flat["fills"])
