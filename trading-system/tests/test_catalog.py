"""The shared catalogue is the door every new system walks through, so it gets guards.

Three of the four things checked here have already gone wrong once in this laboratory,
which is the only reason any of them is worth a test:

  * a degenerate universe was silently accepted and an afternoon of A/B results came
    back 24x too weak, reading as a refuted idea rather than a broken path;
  * data paths were written as bare strings at each point of use, so the same feeds
    ended up under three roots and one system's folder owned all of them;
  * `research()` returning a sealed bar is the one failure this project could not
    recover from, because it would not look like a failure - it would look like a win.

The fourth is new: an interval nobody downloaded must raise rather than return an empty
dict, because an empty dict is a backtest with no trades, and a backtest with no trades
reads as a configuration that stood aside rather than as data that was never there.
"""

from __future__ import annotations

import json

import pytest

import quantlab_catalog as cat
from quantlab_catalog import paths


def test_the_lock_is_the_same_instant_everywhere():
    from quantlab_system06.dataset import LOCK as SYSTEM06_LOCK
    assert cat.LOCK == SYSTEM06_LOCK, (
        "two definitions of the 2026 lock is one definition too many; the catalogue "
        "and the systems reading it must agree on the instant")


def test_research_cannot_return_a_sealed_bar():
    from datetime import datetime

    symbols = cat.load_universe()[:2]
    bars = cat.research(symbols)
    lock = datetime.fromisoformat(cat.LOCK)
    for symbol, series in bars.items():
        assert series, f"{symbol} returned no research bars at all"
        assert max(b.timestamp for b in series) < lock, \
            f"{symbol}: a bar at or after the lock reached research()"


def test_forward_returns_only_sealed_bars():
    from datetime import datetime

    symbols = cat.load_universe()[:2]
    bars = cat.forward(symbols)
    lock = datetime.fromisoformat(cat.LOCK)
    for symbol, series in bars.items():
        assert series, f"{symbol} returned no forward bars"
        assert min(b.timestamp for b in series) >= lock, \
            f"{symbol}: a pre-lock bar reached forward()"


def test_an_interval_we_never_downloaded_raises():
    with pytest.raises(ValueError, match="not in the catalogue"):
        cat.research(["BTCUSDT"], interval="1h")


def test_a_degenerate_universe_raises_instead_of_defaulting(tmp_path, monkeypatch):
    thin = tmp_path / "universe.json"
    thin.write_text(json.dumps({"symbols": ["BTCUSDT"]}), encoding="utf-8")
    monkeypatch.setattr(paths, "UNIVERSE_DIR", tmp_path)
    monkeypatch.setattr(cat.universe, "universe_file", lambda name="universe.json": thin)
    with pytest.raises(ValueError, match="degenerate universe"):
        cat.load_universe()


def test_the_universe_on_disk_is_usable():
    symbols = cat.load_universe()
    assert len(symbols) >= 5
    assert all(s.endswith("USDT") for s in symbols), \
        "the constraint is crypto-only USDT pairs, enforced at selection"


def test_every_external_family_is_present_and_in_the_catalogue():
    status = cat.series_status()
    for family, row in status.items():
        assert row["files"], f"{family}: no files found in the catalogue or the legacy path"
        assert row["in_catalogue"] is not False, (
            f"{family} is still only in a pre-catalogue location; run the migration "
            f"before relying on it from a new system")


def test_no_system_module_hard_codes_a_data_path():
    """A path written at the point of use is how the stores fragmented in the first place."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    stale = "research/system06/external"
    offenders = []
    for py in sorted(root.rglob("quantlab_system06/**/*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        # Docstrings are prose and may legitimately narrate where a store USED to be;
        # what must not survive is a live string literal that a loader would open. So
        # every docstring node is collected first and then excluded by identity.
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                        and isinstance(first.value.value, str):
                    docstrings.add(id(first.value))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and stale in node.value and id(node) not in docstrings:
                offenders.append(f"{py.name}:{node.lineno}")
    assert not offenders, (
        f"these still point at the pre-catalogue store: {offenders}. Use "
        f"quantlab_catalog.paths.external_file() instead.")
