"""A120 adopts min_hold for being ORDERED, not for winning at one setting.

Four candidates in this project have won a single exam and then failed the second.
The defence that has worked is refusing to believe a lone point: a lever the book
responds to smoothly across its range is a mechanism, and a lever that wins at exactly
one value is a draw. This pins that rule so it cannot be relaxed after the numbers
arrive - which is the only moment anyone would ever want to relax it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "research/system06/tools/a120_minhold_and_lean.py"


@pytest.fixture(scope="module")
def a120():
    spec = importlib.util.spec_from_file_location("a120", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_clean_monotone_response_is_ordered(a120):
    # Score falls as min_hold rises: the shape A119's single point predicts.
    curve = [(1, 0.31), (2, 0.30), (4, 0.29), (8, 0.28), (16, 0.276), (48, 0.24)]
    assert a120.ordered(curve) == (True, 0)


def test_one_wobble_is_tolerated(a120):
    curve = [(1, 0.31), (2, 0.29), (4, 0.30), (8, 0.28), (16, 0.276), (48, 0.24)]
    ok, inversions = a120.ordered(curve)
    assert ok and inversions == 1


def test_a_lone_spike_is_not_ordered(a120):
    # Exactly the failure mode the rule exists for: min_hold=1 wins and nothing else
    # near it does. Two inversions, so the curve says "draw", not "mechanism".
    curve = [(1, 0.31), (2, 0.25), (4, 0.26), (8, 0.25), (16, 0.276), (48, 0.24)]
    ok, inversions = a120.ordered(curve)
    assert not ok and inversions >= 2


def test_the_champion_sits_on_the_curve(a120):
    assert a120.CHAMPION_MIN_HOLD in a120.CURVE, (
        "the curve must contain the champion's own setting or every delta is measured "
        "against a point that was never run")


def test_the_curve_is_ascending(a120):
    # ordered() reads adjacency, so an unsorted CURVE would count inversions that are
    # only the table's own disorder.
    assert list(a120.CURVE) == sorted(a120.CURVE)


def test_the_repaired_arms_use_a_drawdown_brake_that_is_actually_off(a120):
    from quantlab_system06.orchestrator import EnsembleBrain

    tick = {"account": {"equity": 10_000.0, "positions": {}},
            "timestamp": "2020-01-01T00:00:00+00:00", "candles": {}}
    off = EnsembleBrain(channels=None, modules=[], max_drawdown=a120._MDD_OFF)
    assert off.decide(dict(tick)).stop is None, (
        "A119 measured two arms with max_drawdown=0.0, which halts the book at bar one "
        "and read as the two most load-bearing modules in the system")
    for name, (_what, arm) in a120.ARMS.items():
        if a120._MDD in arm:
            assert arm[a120._MDD] == a120._MDD_OFF, f"{name} repeats the A119 mistake"


def test_every_lean_arm_only_touches_levers_a119_cleared(a120):
    # The lean arms exist to drop what A119 measured as carrying nothing. Adding a
    # lever here that A119 never ablated would smuggle an untested change into a
    # candidate that is one step from a sealed reading.
    cleared = {"trail_stop", "breadth_gate", "fng_min", "min_hold"}
    for name in ("lean_three", "lean_all"):
        assert set(a120.ARMS[name][1]) <= cleared, (
            f"{name} changes a lever A119 did not measure alone")
