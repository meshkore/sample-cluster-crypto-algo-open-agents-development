"""The network-activity gate: the second non-price input, and it must stay causal."""
import json

import pytest

from quantlab_system06.modules.base import MarketView
from quantlab_system06.modules.onchain import CONVENTIONAL, OnChain

DAY = 86_400
NS = 1_000_000_000


@pytest.fixture
def feed(tmp_path):
    # 30 flat points to seed the trailing window, then a normal one and a collapse
    rows = [{"t_s": 1_600_000_000 + i * DAY, "value": 1000.0 + (i % 2)} for i in range(30)]
    rows.append({"t_s": 1_600_000_000 + 30 * DAY, "value": 1000.0})   # normal
    rows.append({"t_s": 1_600_000_000 + 31 * DAY, "value": 100.0})    # collapse
    p = tmp_path / "chain.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


def _view(ns, channels=None):
    return MarketView(timestamp=None, ns=ns, candles={"BTCUSDT": {"close": 1.0}},
                      account={"equity": 1.0, "cash": 1.0, "positions": {}},
                      channels=channels, held=set(), peaks={})


def test_off_by_default(feed):
    m = OnChain(data_path=feed)
    assert m.activity_min is None
    assert not m.evaluate(_view((1_600_000_000 + 31 * DAY + 3600) * NS)).votes


def test_a_collapse_in_activity_vetoes_new_entries(feed):
    m = OnChain(activity_min=CONVENTIONAL, data_path=feed)
    out = m.evaluate(_view((1_600_000_000 + 31 * DAY + 3600) * NS))
    assert out.votes["BTCUSDT"].veto
    assert "below normal" in (out.note or "")


def test_normal_activity_is_left_alone(feed):
    m = OnChain(activity_min=CONVENTIONAL, data_path=feed)
    assert not m.evaluate(_view((1_600_000_000 + 30 * DAY + 3600) * NS)).votes


def test_it_reads_only_values_published_strictly_before_the_bar(feed):
    m = OnChain(activity_min=CONVENTIONAL, data_path=feed)
    t = 1_600_000_000 + 31 * DAY
    assert m.z_at(t * NS) != m.z_at((t + 3600) * NS), (
        "a bar exactly at publication time must not see that publication")


def test_a_bar_before_any_history_abstains(feed):
    m = OnChain(activity_min=CONVENTIONAL, data_path=feed)
    assert m.z_at(1_500_000_000 * NS) is None


def test_a_missing_feed_abstains_instead_of_crashing(tmp_path):
    m = OnChain(activity_min=CONVENTIONAL, data_path=tmp_path / "nope.json")
    assert m.z_at(1_600_000_000 * NS) is None
    assert not m.evaluate(_view(1_600_000_000 * NS)).votes


def test_the_threshold_is_a_convention_not_a_fitted_value():
    assert CONVENTIONAL == -1.0


def test_the_lever_is_known_to_the_loop_and_the_adapter():
    import inspect

    from quantlab_system06 import autoloop, orchestrator, strategy
    assert "activity_min" in autoloop.KNOWN_LEVERS
    assert "activity_min" in inspect.signature(orchestrator.build_ensemble).parameters
    assert "activity_min" in inspect.signature(strategy.OracleNetBrain.__init__).parameters
