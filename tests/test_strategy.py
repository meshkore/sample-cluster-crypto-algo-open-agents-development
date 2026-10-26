import numpy as np
import pytest
from conftest import make_market

from system12 import strategy
from system12.config import SELECTION


def test_selection_is_the_frozen_champion():
    assert len(SELECTION["members"]) == 20
    assert {basket for _, basket, _, _ in SELECTION["members"]} == {"BTC+ETH"}
    assert SELECTION["overlays"] == [["trail_short", 0.1], ["trend_convex", 0.4]]
    assert SELECTION["paper"]["start"] == "2026-10-22T16"


def test_every_member_regime_resolves(market):
    sig = strategy.signals(market)
    for reg, *_ in SELECTION["members"]:
        assert strategy.regime(sig, reg).shape == (len(market.grid1),)


def test_weights_never_use_the_future():
    calm, crash = make_market(seed=1), make_market(seed=1, crash_from=4000)
    a, b = strategy.target_weights(calm), strategy.target_weights(crash)
    assert np.allclose(a[:4000], b[:4000])
    assert not np.allclose(a, b)


def test_weights_stay_within_gross_100(market):
    W = strategy.target_weights(market)
    assert np.abs(W).sum(axis=1).max() <= 1.0 + 1e-9
    assert (W > 0).any() and (W < 0).any()


def test_trail_short_covers_after_a_rise_from_the_low():
    btc = np.array([100, 95, 90, 92, 100, 101, 102.0])
    W = np.tile([-0.5, 0.0], (7, 1))
    out = strategy.trail_short(btc, W, 0.10)
    # 100 > 90 x 1.1 at bar 4: covered from bar 5, one bar after the signal
    assert np.allclose(out[:5, 0], -0.5)
    assert np.allclose(out[5:, 0], 0.0)


def test_trail_short_resets_on_a_new_short_episode():
    btc = np.array([100, 120, 120, 100, 100.0])
    W = np.array([[-0.5, 0], [-0.5, 0], [0, 0], [-0.5, 0], [-0.5, 0]], dtype=float)
    out = strategy.trail_short(btc, W, 0.10)
    assert out[3, 0] == -0.5 and out[4, 0] == -0.5


def test_trend_convex_scales_longs_only_and_caps_gross():
    btc = np.r_[np.full(180, 100.0), np.full(20, 200.0)]  # +100% over 30 days: multiplier clipped at 2
    W = np.tile([0.4, 0.4], (200, 1))
    out = strategy.trend_convex(btc, W, 0.4)
    assert np.abs(out).sum(axis=1).max() <= 1.0 + 1e-9
    assert out[-1, 0] == pytest.approx(0.5)
    assert np.allclose(strategy.trend_convex(btc, -W, 0.4), -W)
