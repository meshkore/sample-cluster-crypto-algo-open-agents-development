"""System 10 challengers: buy & hold books the price ratio minus both sides' costs; outputs bounded."""

from __future__ import annotations

import numpy as np

from system010_conditioned_rl import challengers as C

BAR = C.BAR_NS
START = int(np.datetime64("2019-01-01T00:00", "ns").astype("int64"))


def _market(days=2 * 365 + 60, coins=4, seed=3):
    rng = np.random.default_rng(seed)
    T = days * C.PER_DAY
    grid = START + np.arange(T, dtype=np.int64) * BAR
    close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.02, (T, coins)), axis=0))
    close[: 200 * C.PER_DAY, coins - 1] = np.nan            # one coin listed late
    return grid, close


def test_buy_and_hold_is_price_ratio_minus_costs():
    grid, close = _market()
    tgt, reb, eps, _ = C.strategies(grid, close)["btc_hold"]
    lo, hi = 400, 1700
    r = C.book(close, tgt, reb, lo, hi, eps)
    want = close[hi - 1, 0] / close[lo, 0] * (1 - C.HALF) / (1 + C.HALF) - 1
    assert abs(r["return"] - round(want, 4)) < 1e-4
    assert r["trades"] == 1


def test_every_strategy_is_bounded_and_long_only():
    grid, close = _market()
    for name, (tgt, reb, eps, _) in C.strategies(grid, close).items():
        assert np.all(tgt >= -1e-12) and np.all(tgt.sum(1) <= 1 + 1e-9), name
        r = C.book(close, tgt, reb, 2 * 365 * C.PER_DAY - 300, len(grid), eps)
        assert r["return"] > -1 and 0 <= r["max_dd"] <= 1, name
        assert np.isfinite(r["q"]), name


def test_cash_strategy_loses_nothing():
    grid, close = _market()
    tgt = np.zeros_like(close)
    reb = np.ones(len(grid), dtype=bool)
    r = C.book(close, tgt, reb, 10, 500)
    assert r == {"return": 0.0, "max_dd": 0.0, "q": 0.0, "trades": 0}
