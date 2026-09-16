"""A champion must be rebuildable from its own record, including zero-valued levers."""

from __future__ import annotations

import json

from system006_oracle_net_15m import autoloop


def _risk_record(brain_kwargs: dict) -> dict:
    """Mirror of the ledger's risk block, so the recording rule is pinned by a test."""
    record = {k: brain_kwargs.get(k, 0.0) for k in autoloop.POSITIONAL_LEVERS}
    for lever in ("vol_scale", "breadth_gate", "regime_deploy", *autoloop.MODULE_LEVERS):
        if lever in brain_kwargs:
            record[lever] = brain_kwargs[lever]
    return record


def test_zero_valued_lever_is_recorded():
    """`meta_margin: 0.0` is an ACTIVE filter; truthiness would silently drop it.

    This is the bug that made the iter-42 champion unreplayable: with the meta filter its
    per-year record scored +0.086 (worst +5.2%); the same net and risk WITHOUT it scored
    -0.076 (worst -11.2%), and the card recorded the second by accident.
    """
    kw = {"max_positions": 2, "position_fraction": 0.15, "stop_loss": 0.08,
          "trail_stop": 0.12, "breadth_gate": 0.30, "regime_deploy": 0.35,
          "meta_margin": 0.0}
    record = _risk_record(kw)
    assert "meta_margin" in record and record["meta_margin"] == 0.0


def test_absent_lever_is_not_invented():
    kw = {"max_positions": 2, "position_fraction": 0.15, "stop_loss": 0.08,
          "trail_stop": 0.12, "breadth_gate": 0.30, "regime_deploy": 0.35}
    record = _risk_record(kw)
    assert "meta_margin" not in record
    assert "hurst_gate" not in record


def test_stamp_card_keeps_zero_levers(tmp_path):
    scratch = tmp_path
    (scratch / "model_card.json").write_text(json.dumps({"family": "system06"}))
    autoloop._stamp_card(scratch, {"max_positions": 2, "position_fraction": 0.15,
                                   "stop_loss": 0.08, "trail_stop": 0.12,
                                   "meta_margin": 0.0, "money_kelly": 0.0},
                         {"score": 0.1, "min_year": 0.05, "cagr": 0.3, "all_positive": True},
                         {2025: {"return_pct": 0.1}})
    card = json.loads((scratch / "model_card.json").read_text())
    assert card["risk_layer"]["meta_margin"] == 0.0
    assert card["risk_layer"]["money_kelly"] == 0.0
