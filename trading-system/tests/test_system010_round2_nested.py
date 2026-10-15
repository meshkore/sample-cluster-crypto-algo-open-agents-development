"""System 10 review round 2, item 3 (R2): eligibility read on the nested curve, INERT without
ENABLE_NESTED_ELIGIBILITY."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "research/system10/tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from system010_conditioned_rl import search as S  # noqa: E402
from system010_conditioned_rl import overfit as O  # noqa: E402

CFG100 = {"regime_ma": 100, "b_up": 0.5, "b_down": 0.0, "selector": True, "horizon": 384}


def _ledger(n=30, seed=4, both=True):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        def ys():
            return {str(y): {"return": float(rng.normal(0.2, 0.3)), "max_dd": float(rng.uniform(0.05, 0.24)),
                             "q": float(rng.normal()), "trades": 100} for y in O.YEARS}
        av = {str(y): {"day_share": 0.9, "longest_gap_days": 5} for y in range(2019, 2026)}
        r = {"id": f"c{i}", "cfg": {**CFG100, "size_down": 1.0, "dd_scale": 0.35, "stop": 0.12, "i": i}, "eligible": True,
             "years": ys(), "availability": {"per_year": av}, "worst_q": 0.0, "worst_year": 0.0, "cagr": 0.1,
             "max_dd": 0.2}
        if both:
            r["confirm"] = {"years": ys(), "eligible": True}
        r["score"] = S.law(r["years"], max(v["max_dd"] for v in r["years"].values()))
        out.append(r)
    return out


def _overfit_doc(rows, path, age_h=1):
    doc = O.measure(rows, None, S.guarded, S.operates)
    doc["at"] = (datetime.now(timezone.utc) - timedelta(hours=age_h)).isoformat(timespec="seconds")
    path.write_text(json.dumps(doc))
    return doc


def test_nested_failures():
    ok = _ledger()
    assert O.nested_failures(O.measure(ok, None, S.guarded, S.operates), ok) == []
    assert O.nested_failures({}, ok)                                    # no picks: fails
    bad = _ledger()
    for r in bad:
        r["years"]["2024"]["trades"] = 10                               # read year too thin
    assert any("trades" in x for x in O.nested_failures(O.measure(bad, None), bad))


def test_champion_unchanged_without_the_flag(tmp_path, monkeypatch):
    rows = _ledger()
    monkeypatch.setattr(S, "NESTED_FLAG", tmp_path / "ENABLE_NESTED_ELIGIBILITY")
    monkeypatch.setattr(S, "OVERFIT", tmp_path / "overfit.json")      # missing: would refuse if read
    assert S.champion(rows) is S._champion_raw(rows) is not None


def test_champion_needs_a_passing_nested_reading_with_the_flag(tmp_path, monkeypatch):
    rows = _ledger()
    f = tmp_path / "overfit.json"
    monkeypatch.setattr(S, "NESTED_FLAG", tmp_path / "ENABLE_NESTED_ELIGIBILITY")
    monkeypatch.setattr(S, "OVERFIT", f)
    S.NESTED_FLAG.write_text("")
    assert S.champion(rows) is None                                   # no reading: refused
    _overfit_doc(rows, f)
    assert S.champion(rows) is S._champion_raw(rows)                  # passing reading
    _overfit_doc(rows, f, age_h=48)
    assert S.champion(rows) is None                                   # stale: refused
    doc = _overfit_doc(rows, f)
    doc["nested"]["picks"]["2024"]["max_dd"] = 0.301
    f.write_text(json.dumps(doc))
    assert "DD 30.1%" in S.nested_refusal(rows) and S.champion(rows) is None
    monkeypatch.setattr(S, "ledger", lambda: rows)
    monkeypatch.setattr(S, "overfit_refusal", lambda: None)
    assert S.current_release("t") is None                              # nothing advances
