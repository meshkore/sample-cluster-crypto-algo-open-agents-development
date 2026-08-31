"""Sizing by certainty: redistribute capital across accepted trades, never add exposure."""
import pytest

from quantlab_system06.modules.conviction import CAP, FLOOR, Conviction


def test_off_by_default():
    assert Conviction().strength == 0.0
    assert Conviction().multiplier(0.99) == 1.0 or Conviction().strength == 0.0


def test_the_tilt_is_centred_on_what_the_book_actually_trades():
    """P29's lesson: unbiased over the RANGE is not unbiased over the POPULATION.
    Accepted entries cluster just above the bar, so centring on the midpoint shrank
    nearly every trade - a de-facto exposure cut in a redistribution's clothes."""
    c = Conviction(conviction_sizing=0.3, enter=0.75, warmup=5)
    for v in (0.78, 0.79, 0.80, 0.81, 0.82):      # a realistic, bar-hugging population
        c.observe(v)
    assert c.multiplier(0.80) == pytest.approx(1.0), "the median trade is funded normally"
    assert c.multiplier(0.90) > 1.0, "an unusually certain trade gets more"
    assert c.multiplier(0.76) < 1.0, "a marginal one gets less"


def test_before_the_window_fills_it_does_nothing():
    c = Conviction(conviction_sizing=0.5, enter=0.75, warmup=30)
    c.observe(0.9)
    assert c.multiplier(0.99) == 1.0, "no history, no opinion"


def test_it_redistributes_over_the_realised_population():
    """The average multiplier over the trades the book actually takes must be ~1.0,
    which is the property the first version lacked."""
    import random

    rng = random.Random(7)
    pop = [0.75 + abs(rng.gauss(0, 0.04)) for _ in range(400)]   # clustered at the bar
    c = Conviction(conviction_sizing=0.3, enter=0.75, warmup=30, window=400)
    for v in pop:
        c.observe(v)
    mults = [c.multiplier(v) for v in pop]
    assert 0.93 < sum(mults) / len(mults) < 1.07, (
        "the tilt must not systematically shrink or inflate the book")


def test_the_multiplier_is_bounded_both_ways():
    c = Conviction(conviction_sizing=5.0, enter=0.75, warmup=1)
    c.observe(0.85)
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
