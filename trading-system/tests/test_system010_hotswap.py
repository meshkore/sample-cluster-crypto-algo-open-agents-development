"""Hot swap (2026-10-15): a book cut in two and continued from its state equals the book in one run."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "research/system10/tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_system010_health import PINNED, _book, _book_world, _digest  # noqa: E402

KEYS = ("side", "symbol", "quantity", "price", "reason")


def test_default_book_still_pinned():
    assert _digest(_book()) == PINNED


def test_split_book_equals_one_run():
    per, *_ = _book_world()
    ns = sorted({int(x) for d in per.values() for x in d["ns"] if d["year"][0] == 2022})
    whole = _book()
    for cut in (ns[len(ns) // 3], ns[len(ns) // 2], ns[2 * len(ns) // 3]):
        a = _book(end_ns=cut)
        b = _book(start_ns=cut, init=a["state"])
        fills = [tuple(f[k] for k in KEYS) for f in a["fills"] + b["fills"]]
        assert fills == [tuple(f[k] for k in KEYS) for f in whole["fills"]], f"cut at {cut}"
        assert abs(b["equity"] - whole["equity"]) < 1e-6
        assert [p["symbol"] for p in b["positions"]] == [p["symbol"] for p in whole["positions"]]
        assert [p["entry_ns"] for p in b["positions"]] == [p["entry_ns"] for p in whole["positions"]]
