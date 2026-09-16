"""The frozen instrument stayed frozen: the champion's sealed year still reproduces.

The backtester is shared by every system in this laboratory, and five systems' recorded
results only mean something if the engine that produced them still produces them. On
2026-09-08 that engine gained signed positions, funding accrual and a no-leverage
ceiling so it could carry shorts.

Every one of those additions is behind a default that reproduces the old behaviour, and
every one of them was argued to be safe. This test is what makes the argument
unnecessary: it replays the champion through the CURRENT code and compares the answer
to the number written in best.json, to the twelfth decimal and to the exact trade count.

If this fails, nothing else in the repository can be trusted until it is explained -
not the champion, not the three sealed readings, not any comparison ever made against
them. It is deliberately not a tolerance test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BEST = REPO / "research/system06/best.json"
SIGNALS = REPO / "research/system06/signals.npz"
DATA = REPO / "trading-system/backtester/data"


@pytest.mark.skipif(not (BEST.is_file() and SIGNALS.is_file()),
                    reason="champion artefacts absent on this machine")
def test_the_champion_sealed_year_reproduces_exactly():
    from system006_oracle_net_15m import launch, universe
    from system006_oracle_net_15m.dataset import Dataset

    best = json.loads(BEST.read_text(encoding="utf-8"))
    on_record = best.get("forward_2026") or {}
    if not on_record.get("return_pct"):
        pytest.skip("no sealed reading on record to compare against")

    band, risk = dict(best["band"]), dict(best["risk"])
    brain = {"enter": float(band["enter"]), "exit_": float(band["exit_"]),
             "min_hold": int(band["min_hold"]), **risk}
    dataset = Dataset(data_root=str(DATA), symbols=universe.load(), interval="15m")
    result = launch.forward(dataset, str(SIGNALS), brain_kwargs=brain)

    assert result["trades"] == on_record["trades"], (
        f"the champion now makes {result['trades']} trades in the sealed year against "
        f"{on_record['trades']} on record - the engine's behaviour has changed")
    assert result["return_pct"] == pytest.approx(on_record["return_pct"], abs=1e-12), (
        f"sealed 2026 is now {result['return_pct']:+.9%} against "
        f"{on_record['return_pct']:+.9%} on record")
    assert result["max_drawdown"] == pytest.approx(
        on_record["max_drawdown"], abs=1e-12)


def test_shorts_are_off_unless_a_session_asks_for_them():
    """The guarantee above holds only while the new path stays opt-in."""
    from quantlab_backtester.session import BacktestSession

    fields = BacktestSession.__dataclass_fields__
    assert fields["allow_shorts"].default is False
    assert fields["max_gross_exposure"].default == 1.0
