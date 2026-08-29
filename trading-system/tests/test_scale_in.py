"""Progressive entries: pyramid into strength, never average down."""
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
    """A stand-in primary that is certain about BTC on every bar."""
    name = "test-primary"
    weight = 1.0
    def __init__(self, conviction=0.9): self.conviction = conviction
    def reset(self): pass
    def evaluate(self, view):
        from quantlab_system06.modules.base import ModuleOutput
        out = ModuleOutput()
        for s in view.candles:
            out.vote(s, conviction=self.conviction)
        return out


def _brain(**kw):
    b = EnsembleBrain(channels=_Ch(), modules=[_AlwaysWants()], position_fraction=1.0,
                      max_positions=1, enter=0.5, exit_=0.1, min_hold=0, **kw)
    return b


def _tick(price, positions, cash=100_000.0, equity=100_000.0, t="2024-01-02T00:00:00+00:00"):
    return {"timestamp": t, "candles": {"BTCUSDT": {"close": price}},
            "account": {"cash": cash, "equity": equity, "initial_capital": 100_000.0,
                        "positions": positions}}


def test_off_by_default_never_adds():
    b = _brain()
    b.decide(_tick(100.0, {}))                       # opens
    d = b.decide(_tick(200.0, {"BTCUSDT": {"qty": 10, "entry_time": "2024-01-01T00:00:00+00:00"}}))
    assert not [o for o in d.orders if o["reason"] == "ADD"]


def test_it_adds_only_after_the_position_proves_itself():
    b = _brain(scale_in=2, scale_step=0.03)
    b.decide(_tick(100.0, {}))
    held = {"BTCUSDT": {"qty": 10, "entry_time": "2024-01-01T00:00:00+00:00"}}
    flat = b.decide(_tick(101.0, held))              # +1%: not enough
    assert not [o for o in flat.orders if o["reason"] == "ADD"]
    up = b.decide(_tick(104.0, held))                # +4%: clears the step
    assert [o for o in up.orders if o["reason"] == "ADD"]


def test_it_never_averages_down():
    """The rule that separates pyramiding from ruin."""
    b = _brain(scale_in=3)
    b.decide(_tick(100.0, {}))
    held = {"BTCUSDT": {"qty": 10, "entry_time": "2024-01-01T00:00:00+00:00"}}
    for px in (95.0, 80.0, 50.0):
        d = b.decide(_tick(px, held))
        assert not [o for o in d.orders if o["reason"] == "ADD"], f"added at {px} - averaging down"


def test_tranches_are_capped_and_shrink_geometrically():
    b = _brain(scale_in=2, scale_step=0.0, scale_decay=0.5)
    b.decide(_tick(100.0, {}))
    held = {"BTCUSDT": {"qty": 10, "entry_time": "2024-01-01T00:00:00+00:00"}}
    sizes = []
    for px in (110.0, 120.0, 130.0, 140.0):
        d = b.decide(_tick(px, held))
        sizes += [o["notional"] for o in d.orders if o["reason"] == "ADD"]
    assert len(sizes) == 2, "no more tranches than scale_in allows"
    assert sizes[1] < sizes[0], "each tranche must be smaller than the last"


def test_a_weakening_signal_is_not_topped_up():
    b = EnsembleBrain(channels=_Ch(), modules=[_AlwaysWants(conviction=0.2)],
                      position_fraction=1.0, max_positions=1, enter=0.5, exit_=0.0,
                      min_hold=999, scale_in=2, scale_step=0.0)
    held = {"BTCUSDT": {"qty": 10, "entry_time": "2024-01-01T00:00:00+00:00"}}
    b._last_fill["BTCUSDT"] = 100.0
    b._tranches["BTCUSDT"] = 0
    d = b.decide(_tick(150.0, held))
    assert not [o for o in d.orders if o["reason"] == "ADD"], (
        "a position may only be topped up while the signal is still entry-grade")


def test_an_add_cannot_spend_cash_the_book_does_not_have():
    b = _brain(scale_in=1, scale_step=0.0)
    b.decide(_tick(100.0, {}))
    held = {"BTCUSDT": {"qty": 10, "entry_time": "2024-01-01T00:00:00+00:00"}}
    d = b.decide(_tick(150.0, held, cash=25.0))
    adds = [o for o in d.orders if o["reason"] == "ADD"]
    assert not adds or adds[0]["notional"] <= 25.0


def test_the_lever_is_known_to_the_loop_and_the_adapter():
    import inspect

    from quantlab_system06 import autoloop, strategy
    assert "scale_in" in autoloop.KNOWN_LEVERS
    assert "scale_in" in inspect.signature(strategy.OracleNetBrain.__init__).parameters
