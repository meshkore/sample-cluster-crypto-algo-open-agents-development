"""Sizing by certainty: redistribute capital across accepted trades, never add exposure."""
import pytest

from quantlab_system06.modules.conviction import CAP, FLOOR, Conviction


def test_off_by_default():
    assert Conviction().strength == 0.0
    assert Conviction().multiplier(0.99) == 1.0 or Conviction().strength == 0.0


def test_a_barely_passing_trade_is_funded_less_and_a_certain_one_more():
    c = Conviction(conviction_sizing=0.3, enter=0.75)
    assert c.multiplier(0.75) == pytest.approx(0.7), "at the bar: minimum size"
    assert c.multiplier(1.00) == pytest.approx(1.3), "at certainty: maximum size"
    assert c.multiplier(0.875) == pytest.approx(1.0), "midway: unchanged"


def test_it_redistributes_rather_than_inflates():
    """The average over the conviction range must stay at 1.0 - every lever that ADDED
    exposure by admitting worse trades has been refuted in this project."""
    c = Conviction(conviction_sizing=0.5, enter=0.75)
    grid = [0.75 + i * 0.25 / 20 for i in range(21)]
    mults = [c.multiplier(x) for x in grid]
    assert sum(mults) / len(mults) == pytest.approx(1.0, abs=1e-9)


def test_the_multiplier_is_bounded_both_ways():
    c = Conviction(conviction_sizing=5.0, enter=0.75)
    assert c.multiplier(1.0) == CAP
    assert c.multiplier(0.75) == FLOOR


def test_a_conviction_below_the_bar_is_left_alone():
    """Refusing an entry is another module's job; this one only sizes what is accepted."""
    class _Ch:
        def prob(self, *a): return 0.6
    class _V:
        ns = 0
        candles = {"BTCUSDT": {}}
        held = set()
        channels = _Ch()
    assert not Conviction(conviction_sizing=0.3, enter=0.75).evaluate(_V()).votes


def test_a_held_name_is_never_resized():
    """P25 measured that adding to a matured trade buys the late part of the move; this
    lever acts once, when the evidence is freshest."""
    class _Ch:
        def prob(self, *a): return 0.95
    class _V:
        ns = 0
        candles = {"BTCUSDT": {}}
        held = {"BTCUSDT"}
        channels = _Ch()
    assert not Conviction(conviction_sizing=0.3, enter=0.75).evaluate(_V()).votes


def test_the_lever_is_known_to_the_loop_and_the_adapter():
    import inspect

    from quantlab_system06 import autoloop, orchestrator, strategy
    assert "conviction_sizing" in autoloop.KNOWN_LEVERS
    assert "conviction_sizing" in inspect.signature(orchestrator.build_ensemble).parameters
    assert "conviction_sizing" in inspect.signature(strategy.OracleNetBrain.__init__).parameters
