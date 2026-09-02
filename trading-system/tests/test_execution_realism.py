"""Execution realism: min notional and participation cap on every BUY.

Born from the 2021 audit (2026-09-02): the compounded account was buying $45M of
NEARUSDT inside single 15-minute candles while paying the same 15 bps it pays on a
$100 order. The engine was internally consistent to the cent - the LIE was the cost
model's silent assumption of infinite liquidity, and these two levers are where that
assumption gets bounded. Off by default: a configuration that does not name them is
byte-identical to before.
"""

import pytest

from quantlab_system06.orchestrator import EnsembleBrain


class _Ch:
    def prob(self, *a): return 0.0
    def uptrend(self, *a): return True
    def vol(self, *a): return None
    def mom(self, *a): return None
    def hurst(self, *a): return None
    def feargreed(self, *a): return None
    def sweep(self, *a): return None
    def meta(self, *a): return None
    def micro(self, *a): return None
    def tree(self, *a): return None
    def size(self, *a): return None
    def has(self, *a): return False


class _AlwaysWants:
    name = "test-primary"
    weight = 1.0
    def reset(self): pass
    def evaluate(self, view):
        from quantlab_system06.modules.base import ModuleOutput
        out = ModuleOutput()
        for s in view.candles:
            out.vote(s, conviction=0.9)
        return out


def _brain(**kw):
    return EnsembleBrain(channels=_Ch(), modules=[_AlwaysWants()], position_fraction=1.0,
                         max_positions=1, enter=0.5, exit_=0.1, min_hold=0, **kw)


def _tick(price, volume, cash=100_000.0, equity=100_000.0):
    return {"timestamp": "2024-01-02T00:00:00+00:00",
            "candles": {"BTCUSDT": {"close": price, "volume": volume}},
            "account": {"cash": cash, "equity": equity, "initial_capital": 100_000.0,
                        "positions": {}}}


def test_off_by_default_is_byte_identical():
    """The allow_adds guarantee, renewed: an unnamed lever changes NOTHING."""
    plain = _brain().decide(_tick(100.0, volume=0.001))       # a nearly dead bar
    assert plain.orders and plain.orders[0]["notional"] == pytest.approx(100_000.0)


def test_participation_caps_a_buy_at_the_bars_traded_value():
    """$100k wished, but the bar only traded $10k: at 25% participation the order
    must shrink to $2.5k - the market cannot absorb what was not traded."""
    b = _brain(max_participation=0.25)
    d = b.decide(_tick(100.0, volume=100.0))        # $10,000 traded in the bar
    assert d.orders and d.orders[0]["notional"] == pytest.approx(2_500.0)
    assert b.cap_stats.get("participation_capped") == 1


def test_participation_leaves_small_orders_alone():
    b = _brain(max_participation=0.25)
    d = b.decide(_tick(100.0, volume=1_000_000.0))  # $100M traded; $100k is 0.1%
    assert d.orders and d.orders[0]["notional"] == pytest.approx(100_000.0)
    assert not b.cap_stats


def test_min_notional_refuses_dust_and_counts_the_refusal():
    """A capped order below the floor is SKIPPED, not sent tiny - and the refusal is
    counted, because an invisible refusal reads as INERT (the scale_stats lesson)."""
    b = _brain(max_participation=0.25, min_notional=100.0)
    d = b.decide(_tick(100.0, volume=3.0))          # $300 traded -> capped to $75 < $100
    assert not d.orders
    assert b.cap_stats.get("below_min_notional") == 1


def test_adds_pass_through_the_same_funnel():
    """Pyramid tranches obey the same market - a $45M add is as unreal as a $45M entry."""
    b = _brain(scale_in=2, scale_step=0.0, max_participation=0.25)
    b.decide(_tick(100.0, volume=1_000_000.0))
    held = {"BTCUSDT": {"qty": 10, "entry_time": "2024-01-01T00:00:00+00:00"}}
    tick = {"timestamp": "2024-01-02T01:00:00+00:00",
            "candles": {"BTCUSDT": {"close": 110.0, "volume": 10.0}},   # $1,100 traded
            "account": {"cash": 100_000.0, "equity": 101_000.0,
                        "initial_capital": 100_000.0, "positions": held}}
    d = b.decide(tick)
    adds = [o for o in d.orders if o["reason"] == "ADD"]
    assert adds and adds[0]["notional"] <= 1_100.0 * 0.25 + 1e-9


def test_missing_volume_disables_the_cap_rather_than_blocking_trade():
    """A feed without volume must not silently veto the whole book - the cap needs a
    number to cap against, and its absence falls back to the old behaviour."""
    b = _brain(max_participation=0.25)
    tick = _tick(100.0, volume=0.0)
    del tick["candles"]["BTCUSDT"]["volume"]
    d = b.decide(tick)
    assert d.orders and d.orders[0]["notional"] == pytest.approx(100_000.0)
