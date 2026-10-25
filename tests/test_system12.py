"""System 12 tests: causality, accounting, overlays, the frozen selection and the docs. No network."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from system12 import strategy as S

ROOT = Path(__file__).resolve().parent.parent
H4, D1 = 4 * 3600 * 10**9, 24 * 3600 * 10**9


def synthetic_world(days: int = 900, seed: int = 0, shock_from: int | None = None) -> SimpleNamespace:
    """A BTC/ETH world on the real grids' conventions (close-stamped bars from 2018-01-01)."""
    rng = np.random.default_rng(seed)
    t0 = np.datetime64("2018-01-01", "ns").astype(np.int64)
    T = days * 6
    r = rng.normal(0.0004, 0.02, (T, 2))
    if shock_from is not None:
        r[shock_from:] = rng.normal(-0.01, 0.05, (T - shock_from, 2))
    c4 = 10_000 * np.exp(np.cumsum(r, axis=0))
    g4 = t0 + H4 * np.arange(1, T + 1)
    g1 = t0 + D1 * np.arange(1, days + 1)
    c1 = c4[5::6]
    w = SimpleNamespace(coins=["BTC", "ETH"])
    w.p4 = {"grid": g4, "year": S.year_of(g4), "close": c4, "usd": np.full_like(c4, 1e8)}
    w.p1 = {"grid": g1, "year": S.year_of(g1), "close": c1, "usd": np.full_like(c1, 6e8)}
    w.fund4 = np.full_like(c4, 0.0001 / 2)
    w.perp4 = np.ones_like(c4, dtype=bool)
    prev = np.r_[g4[0], g4[:-1]]
    w.dk = np.searchsorted(g1, prev, side="right") - 1
    w.imp = S.impact(w.p4)
    return w


def test_selection_is_the_frozen_champion():
    sel = S.SELECTION
    assert len(sel["members"]) == 20
    assert {m[1] for m in sel["members"]} == {"BTC+ETH"}
    assert sel["overlays"] == [["trail_short", 0.1], ["trend_convex", 0.4]]
    assert sel["paper"]["start"] == "2026-10-22T16"
    sig = S.signals(synthetic_world(300))
    for r, *_ in sel["members"]:
        assert S.regime(sig, r).shape == (300,)


def test_weights_are_causal():
    """Changing the future must not change any earlier decision."""
    a, b = synthetic_world(seed=1), synthetic_world(seed=1, shock_from=4000)
    Wa, Wb = S.weights(a), S.weights(b)
    assert np.allclose(Wa[:4000], Wb[:4000])
    assert not np.allclose(Wa, Wb)


def test_weights_are_bounded():
    W = S.weights(synthetic_world(seed=2))
    assert np.abs(W).sum(axis=1).max() <= 1.0 + 1e-9
    assert (W[:, 0] < 0).any() or (W[:, 0] > 0).any()


def test_bar_returns_charge_cost_and_funding():
    w = synthetic_world(30)
    W = np.zeros_like(w.p4["close"])
    W[10:, 0] = 0.5
    r = S.bar_returns(w, W)
    c = w.p4["close"][:, 0]
    cost = 0.5 * (S.HALF_COST + w.imp[0, 0])
    assert r[10] == pytest.approx(0.5 * (c[11] / c[10] - 1) - cost - 0.5 * w.fund4[10, 0])
    assert r[11] == pytest.approx(0.5 * (c[12] / c[11] - 1) - 0.5 * w.fund4[11, 0])
    assert r[-1] == 0.0


def test_trail_short_covers_after_a_rise_from_the_low():
    btc = np.array([100, 95, 90, 92, 100, 101, 102.0])
    W = np.tile([-0.5, 0.0], (7, 1))
    out = S.trail_short(btc, W, 0.10)
    # 100 > 90 x 1.1 at bar 4, so the multiplier is 0 from bar 4 and the position is covered from bar 5 (one bar later)
    assert np.allclose(out[:5, 0], -0.5)
    assert np.allclose(out[5:, 0], 0.0)


def test_trend_convex_scales_longs_only_and_caps_gross():
    btc = np.r_[np.full(180, 100.0), np.full(20, 200.0)]  # +100% over 30 days -> multiplier 2 (clipped)
    W = np.tile([0.4, 0.4], (200, 1))
    out = S.trend_convex(btc, W, 0.4)
    assert np.abs(out).sum(axis=1).max() <= 1.0 + 1e-9
    assert out[-1, 0] == pytest.approx(0.5)
    shorts = S.trend_convex(btc, -W, 0.4)
    assert np.allclose(shorts, -W)


def test_architecture_record_matches_record_json():
    rec = json.loads((ROOT / "system12" / "record.json").read_text(encoding="utf-8"))["years"]
    md = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    row = next(ln for ln in md.splitlines() if ln.startswith("| System 12 (champion v6)"))
    cells = [c.strip() for c in row.strip("|").split("|")[1:]]
    assert cells == [f"{rec[y]['ret'] * 100:+.0f}%" for y in ("2021", "2022", "2023", "2024", "2025")]


def test_docs_link_only_to_files_that_exist():
    for doc in ("README.md", "docs/ARCHITECTURE.md", "docs/RESULTS.md"):
        for path in re.findall(r"`((?:system12|docs|tests|scripts)/[\w./-]+)`", (ROOT / doc).read_text(encoding="utf-8")):
            assert (ROOT / path).exists(), f"{doc} names {path}"
