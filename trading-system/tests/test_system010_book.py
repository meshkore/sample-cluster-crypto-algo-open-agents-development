"""Book audit 2026-10-15: the phase-2 book levers are inert by default and act when set;
the book lab's nested choice cannot read the year it is judged on."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "research/system10/tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from system010_conditioned_rl import search as S  # noqa: E402
from test_system010_health import PINNED, _book, _book_world, _digest  # noqa: E402
from test_system010_levers import RELEASE_31  # noqa: E402

NEW_OFF = {"port_vol": None, "size_kelly": None, "atr_trail": None, "meta_scale": None}
KEYS = ("side", "symbol", "quantity", "price", "reason")


def test_new_levers_off_are_byte_identical():
    assert _digest(_book()) == PINNED
    assert _digest(_book(**NEW_OFF)) == PINNED


def test_mm_kwargs_unchanged_for_releases_and_passes_new_keys_only_when_set():
    assert S.mm_kwargs(RELEASE_31) == {"book_stop": None, "stop": 0.12, "slots": 5, "dd_scale": 0.35,
                                       "size_signal": 0.01, "scale_in": True}
    kw = S.mm_kwargs({**RELEASE_31, "port_vol": 0.3, "atr_trail": 3.0, "add_above": 0.01})
    assert kw["port_vol"] == 0.3 and kw["atr_trail"] == 3.0 and kw["add_above"] == 0.01
    strip = lambda c: S.cfg_id({k: v for k, v in c.items() if k not in S.MM_KEYS})  # noqa: E731
    assert strip({**RELEASE_31, "port_vol": 0.3, "size_kelly": 0.5}) == strip(RELEASE_31)


def test_each_new_lever_changes_the_book():
    base = _digest(_book())
    assert _digest(_book(port_vol=0.05)) != base
    assert _digest(_book(size_kelly=0.25)) != base
    tight = _book(atr_trail=0.5)
    assert any(f["reason"] == "trailing stop" for f in tight["fills"])
    per, *_ = _book_world()
    half = {s: np.full(len(d["ns"]), 0.5) for s, d in per.items()}
    r = _book(meta_scale=half)
    first = lambda rr: next(f for f in rr["fills"] if f["reason"] == "entry")  # noqa: E731
    assert abs(first(r)["notional"] - 0.5 * first(_book())["notional"]) < 1e-6 * first(_book())["notional"]


def test_meta_scale_of_ones_and_kelly_at_reference_are_neutral_where_expected():
    per, *_ = _book_world()
    ones = {s: np.ones(len(d["ns"])) for s, d in per.items()}
    assert [tuple(f[k] for k in KEYS) for f in _book(meta_scale=ones)["fills"]] == \
           [tuple(f[k] for k in KEYS) for f in _book()["fills"]]


def test_port_vol_split_book_equals_one_run():
    per, *_ = _book_world()
    ns = sorted({int(x) for d in per.values() for x in d["ns"] if d["year"][0] == 2022})
    whole = _book(port_vol=0.05)
    for cut in (ns[len(ns) // 3], ns[2 * len(ns) // 3]):
        a = _book(port_vol=0.05, end_ns=cut)
        b = _book(port_vol=0.05, start_ns=cut, init=a["state"])
        assert [tuple(f[k] for k in KEYS) for f in a["fills"] + b["fills"]] == \
               [tuple(f[k] for k in KEYS) for f in whole["fills"]]
        assert abs(b["equity"] - whole["equity"]) < 1e-6


def test_atr_is_causal():
    import conditions as C
    ns = np.datetime64("2022-01-01", "ns").astype(np.int64) + np.arange(96 * 30, dtype=np.int64) * 900 * 10**9
    close = 100 + np.sin(np.arange(len(ns)) / 50.0)
    a = C._atr14(ns, close)
    b = close.copy()
    b[96 * 20:] *= 3          # change the future from day 20 on
    assert np.allclose(a[:96 * 21], C._atr14(ns, b)[:96 * 21], equal_nan=True)
    assert np.isnan(a[:96 * 14]).all() and np.isfinite(a[96 * 14:]).all()


def test_nested_choice_never_reads_the_judged_year():
    import book_lab as L
    rng = np.random.default_rng(0)
    rows = lambda: {y: {"return": float(rng.normal(0.2, 0.2)), "max_dd": float(rng.uniform(0.05, 0.3)),  # noqa: E731
                        "trades": 100} for y in L.YEARS}
    cands = {f"b{i}": rows() for i in range(30)}
    for N in L.READ_YEARS:
        k, _ = L.choose(cands, N)
        spoilt = {i: {**v, **{y: {**v[y], "return": -0.9 if i == k else 5.0} for y in L.YEARS if y >= N}}
                  for i, v in cands.items()}
        assert L.choose(spoilt, N)[0] == k


def test_paired_bootstrap_identical_books_never_win():
    import book_lab as L
    d = np.random.default_rng(1).normal(0.001, 0.02, 365)
    p = L.paired(d, d)
    assert p["p_better"] == 0.0 and p["median"] == 0.0
    assert L.paired(d, d + 0.002)["p_better"] > 0.99


def test_book_of_is_canonical():
    import book_lab as L
    assert L.book_of({**RELEASE_31, "scale_in": False, "mom_rank": None}) == \
           {"slots": 5, "stop": 0.12, "dd_scale": 0.35, "size_signal": 0.01}
    assert L.book_id({"slots": 5, "stop": 0.12}) == L.book_id({"stop": 0.12, "slots": 5, "take_profit": None})
