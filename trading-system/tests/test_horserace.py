"""Horse-race: upsize laggards only when the pack runs and the leader is up; else abstain."""

from __future__ import annotations

from datetime import datetime, timezone

from system006_oracle_net_15m.channels import Channels
from system006_oracle_net_15m.modules.base import MarketView
from system006_oracle_net_15m.modules.horserace import HorseRace


def _ch(moms: dict) -> Channels:
    return Channels({s: {"prob": {}, "trend": {}, "vol": {}, "mom": {10: m}, "hurst": {}, "feargreed": {}}
                    for s, m in moms.items()})


def _view(ch, symbols, ns=10):
    return MarketView(timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), ns=ns,
                      candles={s: {"close": 100.0} for s in symbols},
                      account={"positions": {}}, channels=ch, held=set(), peaks={})


def test_off_abstains():
    ch = _ch({"BTCUSDT": 0.5, "A": 0.4, "B": -0.1, "C": 0.3, "D": -0.2, "E": 0.6})
    out = HorseRace(horserace=0.0).evaluate(_view(ch, list("A"), ns=10))
    assert out.votes == {}


def test_pack_running_upsizes_laggards():
    # Pack is hot (most positive), BTC up. Laggards (below-median momentum) get upsized.
    moms = {"BTCUSDT": 0.5, "A": 0.6, "B": 0.4, "C": 0.05, "D": -0.05, "E": 0.45}
    ch = _ch(moms)
    syms = list(moms)
    out = HorseRace(horserace=1.0).evaluate(_view(ch, syms))
    # median of [.5,.6,.4,.05,-.05,.45] = 0.425; laggards: B(.4), C(.05), D(-.05)
    assert out.votes["C"].size_mult > 1.0
    assert out.votes["D"].size_mult > 1.0
    assert "A" not in out.votes and "E" not in out.votes   # leaders not boosted
    assert all(0.5 <= v.size_mult <= 1.3 for v in out.votes.values())


def test_pack_cold_abstains():
    # Most coins negative -> pack not running -> no boosts even at full strength.
    moms = {"BTCUSDT": -0.1, "A": -0.2, "B": -0.3, "C": 0.05, "D": -0.05, "E": -0.4}
    ch = _ch(moms)
    out = HorseRace(horserace=1.0).evaluate(_view(ch, list(moms)))
    assert out.votes == {}


def test_leader_down_abstains():
    # Pack positive but the leader (BTC) is down -> not a confirmed cascade -> abstain.
    moms = {"BTCUSDT": -0.05, "A": 0.6, "B": 0.4, "C": 0.5, "D": 0.45, "E": 0.55}
    ch = _ch(moms)
    out = HorseRace(horserace=1.0).evaluate(_view(ch, list(moms)))
    assert out.votes == {}


def test_too_few_names_abstains():
    ch = _ch({"BTCUSDT": 0.5, "A": 0.4})
    out = HorseRace(horserace=1.0).evaluate(_view(ch, ["BTCUSDT", "A"]))
    assert out.votes == {}
