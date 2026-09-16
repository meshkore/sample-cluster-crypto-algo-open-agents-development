"""The architecture registry: a new ID for a new STRUCTURE, never for a new value."""
import json

import pytest

from system006_oracle_net_15m import registry


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ROOT", tmp_path / "registry")
    monkeypatch.setattr(registry, "INDEX", tmp_path / "registry" / "architectures.jsonl")


def _spec(**over):
    base = {"title": "narrow trend book", "modules": ["oracle-nn", "meta", "stops", "regime"],
            "labeller": "zigzag-1pct", "features": ["price", "trend", "vol"],
            "universe_id": "universe.json:14", "timeframe": "15m",
            "pipeline": "generate>filter>size>survive", "levers": {"regime_deploy": 0.35}}
    base.update(over)
    return base


def test_a_changed_lever_value_does_not_mint_a_new_id():
    """The distinction the operator asked for: values are configurations OF an
    architecture, not architectures."""
    a = registry.register(_spec(), explanation="first")
    b = registry.register(_spec(levers={"regime_deploy": 0.50}), explanation="tuned")
    assert a["id"] == b["id"]
    assert len(registry.read_index()) == 1


def test_adding_a_module_mints_a_new_id():
    a = registry.register(_spec(), explanation="first")
    b = registry.register(_spec(modules=["oracle-nn", "meta", "stops", "regime", "seasoning"]),
                          explanation="seasoning gate added", parent=a["id"])
    assert b["id"] != a["id"]
    assert b["parent"] == a["id"]


def test_changing_the_labeller_or_the_universe_mints_a_new_id():
    a = registry.register(_spec(), explanation="first")
    lab = registry.register(_spec(labeller="triple-barrier"), explanation="labels")
    uni = registry.register(_spec(universe_id="universe_deep.json:24"), explanation="wide")
    assert len({a["id"], lab["id"], uni["id"]}) == 3


def test_every_architecture_gets_code_diagram_and_explanation():
    a = registry.register(_spec(), explanation="the shipping book")
    folder = registry.ROOT / a["id"]
    assert (folder / "code.json").is_file()
    assert (folder / "explain.md").is_file()
    diagram = (folder / "diagram.mmd").read_text(encoding="utf-8")
    assert diagram.startswith("flowchart TD")
    assert "meta" in diagram and "regime" in diagram, "the diagram must show the real modules"


def test_backtests_attach_and_accumulate():
    a = registry.register(_spec(), explanation="x")
    registry.attach_backtest(a["id"], {"kind": "walk-forward", "median": 0.02})
    registry.attach_backtest(a["id"], {"kind": "sealed", "sealed_2026": 0.351})
    rows = registry.backtests(a["id"])
    assert len(rows) == 2 and all("at" in r for r in rows)
    assert registry.summary()[0]["backtest_count"] == 2
    assert registry.summary()[0]["best_sealed_2026"] == 0.351


def test_attaching_to_an_unknown_architecture_is_refused():
    with pytest.raises(ValueError):
        registry.attach_backtest("ARCH-9999", {"kind": "x"})


def test_status_changes_keep_their_reason():
    a = registry.register(_spec(), explanation="x")
    registry.set_status(a["id"], "rejected", "median sealed 2026 -21.1% across three seeds")
    row = registry.read_index()[0]
    assert row["status"] == "rejected" and "-21.1%" in row["status_reason"]
