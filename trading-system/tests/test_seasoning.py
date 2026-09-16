"""Seasoning: a symbol must have its OWN history before the book may trade it."""
import pytest

from system006_oracle_net_15m.modules.base import MarketView
from system006_oracle_net_15m.modules.seasoning import NS_PER_DAY, Seasoning

DAY = NS_PER_DAY


class _Ch:
    """Minimal channels stand-in exposing the table the module reads."""
    def __init__(self, first_ns_by_symbol):
        self._table = {s: {"prob": {ns: 0.9}} for s, ns in first_ns_by_symbol.items()}


def _view(ns, symbols, channels):
    return MarketView(timestamp=None, ns=ns, candles={s: {"close": 1.0} for s in symbols},
                      account={"equity": 1.0, "cash": 1.0, "positions": {}},
                      channels=channels, held=set(), peaks={})


def test_off_by_default_vetoes_nothing():
    ch = _Ch({"NEWUSDT": 1000 * DAY})
    out = Seasoning().evaluate(_view(1001 * DAY, ["NEWUSDT"], ch))
    assert not out.votes


def test_a_freshly_listed_symbol_is_vetoed():
    ch = _Ch({"NEWUSDT": 1000 * DAY})
    m = Seasoning(min_age_days=365)
    out = m.evaluate(_view((1000 + 30) * DAY, ["NEWUSDT"], ch))   # 30 days old
    assert out.votes["NEWUSDT"].veto


def test_the_same_symbol_becomes_tradable_once_it_has_seasoned():
    ch = _Ch({"NEWUSDT": 1000 * DAY})
    m = Seasoning(min_age_days=365)
    young = m.evaluate(_view((1000 + 364) * DAY, ["NEWUSDT"], ch))
    ripe = m.evaluate(_view((1000 + 366) * DAY, ["NEWUSDT"], ch))
    assert young.votes["NEWUSDT"].veto
    assert not ripe.votes, "past the threshold the module must stop objecting"


def test_it_judges_each_symbol_by_its_own_clock():
    """The failure this fixes: a screen run TODAY says a coin has four years, but in
    2018 that same coin had four months - and the book traded it anyway."""
    ch = _Ch({"OLDUSDT": 0, "NEWUSDT": 900 * DAY})
    m = Seasoning(min_age_days=365)
    out = m.evaluate(_view(1000 * DAY, ["OLDUSDT", "NEWUSDT"], ch))
    assert "OLDUSDT" not in out.votes
    assert out.votes["NEWUSDT"].veto


def test_a_symbol_with_no_signal_history_is_left_to_the_other_modules():
    ch = _Ch({})
    out = Seasoning(min_age_days=365).evaluate(_view(1000 * DAY, ["GHOSTUSDT"], ch))
    assert not out.votes


def test_the_lever_is_known_to_the_loop_and_the_adapter():
    import inspect

    from system006_oracle_net_15m import autoloop, orchestrator, strategy
    assert "min_age_days" in autoloop.KNOWN_LEVERS
    assert "min_age_days" in inspect.signature(orchestrator.build_ensemble).parameters
    assert "min_age_days" in inspect.signature(strategy.OracleNetBrain.__init__).parameters
