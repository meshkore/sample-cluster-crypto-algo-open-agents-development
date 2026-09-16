"""System 08's gate must refuse what system 06's prose failed to refuse.

Every test here corresponds to a real loss. That is the only reason each one exists,
and it is why the gate is code instead of a paragraph in a context file.
"""

from __future__ import annotations

import pytest

from system008_residual_momentum_ls import INCUMBENT_SEALED_2026
from system008_residual_momentum_ls.gate import Candidate, price_the_edge, record_sealed


def _framed(name="c") -> Candidate:
    c = Candidate(name=name, hypothesis="h", kill_criterion="k")
    c.advance("frame", {})
    c.advance("measure", {})
    return c


def test_a_stage_cannot_be_skipped():
    c = _framed()
    with pytest.raises(RuntimeError, match="exam1"):
        c.advance("exam2", {})


def test_a_stage_cannot_be_re_run_until_it_passes():
    c = _framed()
    c.advance("exam1", {"result": "won"})
    with pytest.raises(RuntimeError, match="already recorded"):
        c.advance("exam1", {"result": "won again, honest"})


def test_framing_without_a_kill_criterion_is_refused():
    c = Candidate(name="c", hypothesis="it will work")
    with pytest.raises(ValueError, match="kill criterion"):
        c.advance("frame", {})


def test_one_exam_does_not_open_the_sealed_window():
    """Four system 06 candidates won exam 1 and lost exam 2."""
    c = _framed()
    c.advance("exam1", {"result": "won"})
    ok, why = c.may_open_sealed_window()
    assert not ok and "coin flip" in why


def test_two_exams_are_still_not_enough_without_pricing_the_edge():
    """A103, A120 and A124 all had out-of-sample evidence and all lost 2026."""
    c = _framed()
    c.advance("exam1", {"result": "won"})
    c.advance("exam2", {"result": "won"})
    ok, why = c.may_open_sealed_window()
    assert not ok and "priced" in why


def test_an_edge_whose_spread_straddles_one_is_not_decisive():
    # The real min_hold 32 numbers: median 1.02x, 71% of years won, and it lost 2026.
    verdict = price_the_edge([0.761, 0.961, 1.010, 1.019, 1.159, 1.403, 1.519])
    assert not verdict["decisive"]
    assert verdict["median"] > 1.0, "the median was positive - that was the trap"
    assert "straddles" in verdict["why"]


def test_an_edge_that_wins_every_measured_year_is_decisive():
    verdict = price_the_edge([1.06, 1.12, 1.19, 1.31, 1.44])
    assert verdict["decisive"] and verdict["min"] > 1.0


def test_three_observations_cannot_estimate_a_spread():
    verdict = price_the_edge([1.2, 1.3, 1.4])
    assert not verdict["decisive"] and "fewer than four" in verdict["why"]


def test_the_sealed_window_opens_only_after_all_three_gates():
    c = _framed()
    c.advance("exam1", {"result": "won"})
    c.advance("exam2", {"result": "won"})
    c.advance("power", price_the_edge([1.06, 1.12, 1.19, 1.31, 1.44]))
    ok, _why = c.may_open_sealed_window()
    assert ok


def test_recording_a_reading_the_gate_refused_raises(tmp_path):
    c = _framed()
    c.advance("exam1", {"result": "won"})
    with pytest.raises(RuntimeError, match="refusing to record"):
        record_sealed(c, 0.99, {}, ledger=tmp_path / "ledger.jsonl")


def test_a_losing_reading_is_written_with_the_same_keystrokes(tmp_path):
    import json

    c = _framed()
    c.advance("exam1", {"result": "won"})
    c.advance("exam2", {"result": "won"})
    c.advance("power", price_the_edge([1.06, 1.12, 1.19, 1.31, 1.44]))
    ledger = tmp_path / "ledger.jsonl"
    row = record_sealed(c, -0.30, {"trades": 12}, ledger=ledger)
    assert row["beat_incumbent"] is False
    written = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert written["sealed_2026"] == -0.30
    assert written["incumbent_sealed_2026"] == INCUMBENT_SEALED_2026


def test_the_bar_is_the_incumbents_real_sealed_number():
    import json
    import pathlib

    best = json.loads((pathlib.Path(__file__).resolve().parents[2]
                       / "research/system06/best.json").read_text(encoding="utf-8"))
    assert INCUMBENT_SEALED_2026 == best["forward_2026"]["return_pct"], (
        "system 08's bar must be the champion's actual sealed result, not a copy that "
        "drifted; winning means beating what is really on the table")
