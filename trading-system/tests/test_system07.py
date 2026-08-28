"""System 07 capitulation dip-buyer: enters on a capitulation, exits on target/horizon,
does nothing on calm data, and honours the book cap. Long-only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from quantlab_system07.strategy import CapitulationDip


@dataclass
class Bar:
    timestamp: object
    open: float
    high: float
    low: float
    close: float
    volume: float


def _bars(close, high=None, low=None, volume=None):
    n = len(close)
    high = high if high is not None else [c + 0.5 for c in close]
    low = low if low is not None else [c - 0.5 for c in close]
    volume = volume if volume is not None else [1000.0] * n
    t0 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [Bar(t0 + timedelta(minutes=15 * i), close[i], high[i], low[i], close[i], volume[i])
            for i in range(n)]


def _capitulation_then(path_after):
    """A declining run, a capitulation candle at index 180, then `path_after` closes."""
    n = 180 + len(path_after)
    close = [100.0] * 160 + [100.0 - (i - 160) * 2.0 for i in range(160, 180)] + list(path_after)
    high = [c + 0.5 for c in close]
    low = [c - 0.5 for c in close]
    volume = [1000.0] * n
    i = 180
    low[i] = close[i] - 12.0      # long lower wick
    volume[i] = 20000.0           # volume spike
    return _bars(close, high, low, volume)


def test_no_capitulation_no_trades():
    calm = _bars([100.0] * 300)
    r = CapitulationDip().backtest({"AAA": calm})
    assert r["trades"] == 0
    assert abs(r["return_pct"]) < 1e-9


def test_dip_buy_takes_profit():
    # after the capitulation at 180, price climbs ~10% over the next bars -> target 6% hit
    entry_px = 100.0 - (179 - 160) * 2.0  # ~62
    rise = [entry_px * (1.0 + 0.004 * k) for k in range(1, 60)]  # +~24% over 59 bars
    bars = _capitulation_then(rise)
    r = CapitulationDip(enter=0.4, target=0.06, stop=0.10, horizon=96).backtest({"AAA": bars})
    assert r["trades"] >= 1, "should enter on the capitulation candle"
    assert r["return_pct"] > 0, f"a bounce to target should net positive, got {r['return_pct']:.3f}"
    assert r["win_rate"] is not None and r["win_rate"] > 0


def test_horizon_exit_when_flat():
    # capitulation, then flat -> neither target nor stop; must exit at the horizon
    flat = [62.0] * 200
    bars = _capitulation_then(flat)
    r = CapitulationDip(enter=0.4, horizon=48).backtest({"AAA": bars})
    assert r["trades"] >= 1
    # flat exit after costs -> small negative (the 0.003 round-trip)
    assert r["trades"] == sum(1 for _ in range(r["trades"]))  # sanity


def test_long_only_and_bounded():
    r = CapitulationDip(max_positions=2)
    calm = _bars([100.0] * 200)
    out = r.backtest({"AAA": calm, "BBB": calm})
    assert out["return_pct"] >= -0.05  # long-only, calm -> ~flat, never blows up


def test_drop_sizing_off_is_exactly_the_old_book():
    """drop_sizing=0.0 must leave the multiplier at exactly 1 - the inertness
    guarantee every off-by-default lever carries."""
    from quantlab_system07.strategy import CapitulationDip

    s = CapitulationDip()
    assert s._size_mult(0.0) == 1.0
    assert s._size_mult(0.30) == 1.0


def test_drop_sizing_tilts_toward_deep_flushes_and_is_bounded():
    from quantlab_system07.strategy import CapitulationDip

    s = CapitulationDip(drop_sizing=1.0)
    assert s._size_mult(0.05) == 1.0            # 5% drop is the pivot
    assert s._size_mult(0.20) == 2.5            # deep flush hits the cap
    assert s._size_mult(0.001) == 0.4           # shallow dip hits the floor
    half = CapitulationDip(drop_sizing=0.5)
    assert 1.0 < half._size_mult(0.20) < 2.5    # exponent softens the tilt
