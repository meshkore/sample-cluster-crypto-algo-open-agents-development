"""System 10 book levers (2026-10-14): absent = today's book byte for byte; each one acts."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "research/system10/tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from system010_conditioned_rl import search as S  # noqa: E402
from test_system010_health import PINNED, _book, _digest  # noqa: E402

RELEASE_31 = {"regime_ma": 100, "b_up": 0.5, "b_down": 0.0, "selector": True, "horizon": 768,
              "size_down": 0.75, "exit": "learned", "features": "full", "slots": 5, "size_signal": 0.01,
              "dd_scale": 0.35, "scale_in": True, "stop": 0.12}
OFF = {"corr_cap": None, "eq_filter": None, "min_edge": None, "take_profit": None,
       "breakeven": None, "mom_rank": None}


def test_levers_off_are_byte_identical():
    assert _digest(_book(**OFF)) == PINNED
    # what the workers, the evaluator and the paper book pass for release 31: unchanged
    assert S.mm_kwargs(RELEASE_31) == {"book_stop": None, "stop": 0.12, "slots": 5, "dd_scale": 0.35,
                                       "size_signal": 0.01, "scale_in": True}


def test_release_id_and_signal_key_unchanged():
    assert S.cfg_id(RELEASE_31) == "6e9757e461"
    with_lever = {**RELEASE_31, "mom_rank": 5}
    strip = lambda c: S.cfg_id({k: v for k, v in c.items() if k not in S.MM_KEYS})  # noqa: E731
    assert strip(with_lever) == strip(RELEASE_31)   # book-only: the fitted signals are reused


def test_each_lever_changes_the_book():
    base = _book()
    tp = _book(take_profit=0.01)
    assert any(f["reason"] == "take profit" for f in tp["fills"])
    be = _book(breakeven=0.005)
    assert any(f["reason"] == "breakeven stop" for f in be["fills"])
    edge = _book(min_edge=0.01)
    assert edge["trades"] < base["trades"]
    eq = _book(eq_filter=5, eq_cut=0.5)
    assert _digest(eq) != _digest(base)
    mom = _book(mom_rank=1, mom_in=2.0, mom_out=1.0)
    assert _digest(mom) != _digest(base)


def test_corr_cap_one_holds_one_correlated_coin():
    r = _book(corr_cap=1, corr_rho=-2.0)          # every pair counts as correlated
    assert len(r["positions"]) <= 1
    held, most = set(), 0
    for f in r["fills"]:
        if f["reason"] == "entry":
            held.add(f["symbol"])
        elif f["side"] == "SELL" and f["reason"] != "trim: signal weakened":
            held.discard(f["symbol"])
        most = max(most, len(held))
    assert most <= 1


def test_momentum_filter_enters_only_top_coins():
    import conditions as C
    from test_system010_health import _book_world
    per = _book_world()[0]
    syms = list(per)
    grid = np.unique(np.concatenate([per[s]["ns"] for s in syms]))
    top = C._momentum_top(per, syms, grid, 1, 1)
    assert top.sum(axis=1).max() <= 1
    r = _book(mom_rank=1, mom_days=1, mom_out=0.0)
    t_of = {int(t): i for i, t in enumerate(grid)}
    for f in r["fills"]:
        if f["reason"] == "entry":
            assert top[t_of[f["t"]], syms.index(f["symbol"])]


def test_search_space_reaches_the_levers():
    nb = S.neighbours(RELEASE_31)
    assert {**RELEASE_31, "mom_rank": 3} in nb and {**RELEASE_31, "min_edge": 0.004} in nb
    on = {**RELEASE_31, "mom_rank": 3}
    assert RELEASE_31 in S.neighbours(on)               # switching it off is the release again
    rng = np.random.default_rng(0)
    draws = [S.random_config(rng) for _ in range(400)]
    share = np.mean([d.get("mom_rank") is not None for d in draws])
    assert 0.1 < share < 0.4


def test_ledger_drops_lever_rows_booked_by_old_workers(tmp_path, monkeypatch):
    import json
    row = lambda cfg, **k: {"id": S.cfg_id(cfg), "cfg": cfg, "eligible": True, "max_dd": 0.2, **k}  # noqa: E731
    rows = [row(RELEASE_31), row({**RELEASE_31, "mom_rank": 5}),
            row({**RELEASE_31, "mom_rank": 3}, book_v=S.BOOK_V)]
    p = tmp_path / "trials.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(S, "TRIALS", p)
    kept = S.ledger()
    assert [r["cfg"].get("mom_rank") for r in kept] == [None, 3]
