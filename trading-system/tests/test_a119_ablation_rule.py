"""A119's decision rule must be the one written in its docstring, before the numbers.

The rule is the whole value of an ablation study: without it, fourteen arms produce
fourteen numbers and a human picks the story afterwards. So the thresholds are
constants in the tool and this pins their MEANING - that a module which changes
nothing is called decoration, that one whose removal costs the worst year is called
load-bearing, and that the ambiguous middle is left alone rather than argued into
one camp or the other.

It also exercises the report path on synthetic arms. The recency tools crashed in
exactly that block, hours after launch, with every backtest already paid for.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "research/system06/tools/a119_module_ablation.py"


@pytest.fixture(scope="module")
def a119():
    spec = importlib.util.spec_from_file_location("a119", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _row(fit=0.20, holdout=0.10, worst=-0.03, dd=0.22):
    return {"fit": fit, "holdout": holdout,
            "fit_min_year": worst, "fit_worst_drawdown": dd}


def test_a_module_that_changes_nothing_is_decoration(a119):
    assert a119._verdict(_row(), _row()) == "DECORATION"


def test_a_module_whose_removal_costs_the_score_is_load_bearing(a119):
    off = _row(fit=0.20 - 2 * a119.EPS_SCORE)
    assert a119._verdict(_row(), off) == "LOAD-BEARING"


def test_a_module_whose_removal_costs_the_worst_year_is_load_bearing(a119):
    # The score barely moves but the worst calendar year drops two points: that is
    # precisely the trade the mandate exists to refuse.
    off = _row(worst=-0.03 - 2 * a119.BIG_YEAR)
    assert a119._verdict(_row(), off) == "LOAD-BEARING"


def test_a_module_whose_removal_deepens_the_drawdown_is_load_bearing(a119):
    off = _row(dd=0.22 + 2 * a119.BIG_DD)
    assert a119._verdict(_row(), off) == "LOAD-BEARING"


def test_a_module_the_book_is_better_without_is_a_cost(a119):
    off = _row(fit=0.20 + 2 * a119.EPS_SCORE)
    assert a119._verdict(_row(), off) == "COST"


def test_an_improvement_that_the_held_out_half_contradicts_is_not_a_cost(a119):
    # Better on the fit half, worse on the years the champion's levers never saw. The
    # rule refuses to call that a saving - it is the shape of every overfit this
    # project has been burned by.
    off = _row(fit=0.20 + 2 * a119.EPS_SCORE, holdout=0.10 - 2 * a119.EPS_SCORE)
    assert a119._verdict(_row(), off) != "COST"


def test_the_ambiguous_middle_is_left_alone(a119):
    # Half a threshold of movement in a direction that is neither clearly free nor
    # clearly costly: the burden of proof is on removal, so this stays put.
    off = _row(worst=-0.03 - 1.5 * a119.EPS_YEAR)
    assert a119._verdict(_row(), off) == "UNCLEAR"


def test_the_baseline_arm_exists_and_removes_nothing(a119):
    assert a119.ARMS["baseline"][1] == {}, (
        "the baseline must be the champion verbatim or every delta is measured "
        "against a configuration that is not the champion")


def test_max_drawdown_off_value_really_switches_the_brake_off(a119):
    """The first run of A119 used 0.0 for "no drawdown brake" and measured nothing.

    The orchestrator halts on `equity <= peak * (1 - max_drawdown)`, so 0.0 halts the
    book the instant equity touches its own peak - bar one. Both arms using it traded
    zero times across eight years, scored INERT, and were then reported as the two most
    load-bearing modules in the system. An "off" value assumed instead of checked is how
    P46 measured a lever that did not exist; this checks it against the brain itself.
    """
    from system006_oracle_net_15m.orchestrator import EnsembleBrain

    tick = {"account": {"equity": 10_000.0, "positions": {}},
            "timestamp": "2020-01-01T00:00:00+00:00", "candles": {}}

    halts = EnsembleBrain(channels=None, modules=[], max_drawdown=0.0)
    assert halts.decide(dict(tick)).stop, \
        "0.0 is expected to be the TIGHTEST possible brake, not the absent one"

    off = EnsembleBrain(channels=None, modules=[], max_drawdown=a119._MDD_OFF)
    assert off.decide(dict(tick)).stop is None, \
        f"A119 uses {a119._MDD_OFF} as 'brake off' and the brain still halts on it"

    for _name, (_what, arm) in a119.ARMS.items():
        if a119._MDD in arm:
            assert arm[a119._MDD] == a119._MDD_OFF, \
                "an arm sets the drawdown brake to something that is not its off value"


def test_every_ablation_names_a_lever_the_champion_actually_sets(a119):
    # An arm that turns off a lever already at zero measures nothing and would be
    # reported as a module carrying nothing - a false DECORATION verdict, which is the
    # P46 failure (a lever that did not exist, read as a refutation).
    import json
    # From __file__, not from the tool's relative ROOT: the tool is run from the repo
    # root but pytest is not, and a relative path here would fail for the wrong reason.
    best_path = Path(__file__).resolve().parents[2] / "research/system06/best.json"
    best = json.loads(best_path.read_text(encoding="utf-8"))
    live = {**best["risk"], **best["band"]}
    # trend_soft is the ablation OF the trend filter, which lives in the signals rather
    # than in the risk block; max_drawdown rides in from risk under its private key.
    exempt = {"trend_soft", a119._MDD}
    for name, (_what, off) in a119.ARMS.items():
        for lever in off:
            if lever in exempt:
                continue
            assert float(live.get(lever) or 0.0) != 0.0, \
                f"{name}: the champion does not set `{lever}`, so turning it off " \
                f"measures nothing and would read as a module carrying nothing"
