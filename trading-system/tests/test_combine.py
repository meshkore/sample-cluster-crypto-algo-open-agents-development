"""The two-book combine: the arithmetic the A64 measurement rests on."""
import numpy as np
import pytest

from quantlab_system07.combine import combine_curves

T0 = np.datetime64("2022-01-01T00:00")


def _points(equities, cash_frac=0.8, start=T0, step_h=6):
    ts = start + np.arange(len(equities)) * np.timedelta64(step_h, "h")
    return [{"timestamp": str(t), "equity": float(e), "cash": float(e * cash_frac)}
            for t, e in zip(ts, equities)]


def _capit(equities, start=T0, step_h=6):
    ts = start + np.arange(len(equities)) * np.timedelta64(step_h, "h")
    return [{"timestamp": str(t), "equity": float(e)} for t, e in zip(ts, equities)]


def test_flat_capitulation_book_changes_nothing():
    trend = _points(np.linspace(100, 120, 50))
    capit = _capit(np.full(50, 1000.0))
    r = combine_curves(trend, capit)
    assert r["return_pct"] == pytest.approx(0.20, abs=1e-9)


def test_zero_sleeve_is_the_trend_book():
    trend = _points(100 * np.cumprod(1 + np.random.default_rng(1).normal(0, 0.01, 80)))
    capit = _capit(np.linspace(1000, 1500, 80))
    r = combine_curves(trend, capit, sleeve=0.0)
    t = np.array([p["equity"] for p in trend])
    assert r["return_pct"] == pytest.approx(t[-1] / t[0] - 1.0, abs=1e-12)


def test_single_month_additive_contribution():
    # Trend flat, capit +10% inside one month, ample cash: combined = sleeve x 10%.
    trend = _points(np.full(60, 100.0), cash_frac=0.9)
    capit = _capit(np.linspace(1000, 1100, 60))
    r = combine_curves(trend, capit, sleeve=0.30, margin=0.02)
    assert r["return_pct"] == pytest.approx(0.03, abs=1e-9)
    assert r["avg_sleeve_ratio"] == pytest.approx(1.0)


def test_cash_cap_scales_the_contribution():
    # Worst cash fraction 0.17, margin 0.02 -> r_m = 0.15/0.30 = 0.5: half the lift.
    trend = _points(np.full(60, 100.0), cash_frac=0.17)
    capit = _capit(np.linspace(1000, 1100, 60))
    r = combine_curves(trend, capit, sleeve=0.30, margin=0.02)
    assert r["return_pct"] == pytest.approx(0.015, abs=1e-9)
    assert r["avg_sleeve_ratio"] == pytest.approx(0.5)


def test_monthly_rebalance_compounds_the_sleeve():
    # Two months, trend flat, capit +10% each month, full cash: the second month's
    # sleeve is sized on the grown combined equity -> strictly more than 2 x 3%.
    n = 121  # ~30.25 days at 6h steps spills into a second month
    trend = _points(np.full(2 * n, 100.0), cash_frac=0.9, step_h=6)
    capit_m1 = np.linspace(1000, 1100, n)
    capit_m2 = np.linspace(1100, 1210, n)
    capit = _capit(np.concatenate([capit_m1, capit_m2]), step_h=6)
    r = combine_curves(trend, capit, sleeve=0.30, margin=0.02)
    simple_twice = (1.03 ** 2) - 1  # what per-month sleeves WITHOUT compounding give
    assert r["return_pct"] > 0.06
    assert r["return_pct"] == pytest.approx(simple_twice, rel=0.05)


def test_no_dilution_of_a_trend_rally():
    # Trend +50%, capit flat: the combine returns exactly the trend's +50%.
    trend = _points(np.linspace(100, 150, 90), cash_frac=0.6)
    capit = _capit(np.full(90, 500.0))
    r = combine_curves(trend, capit)
    assert r["return_pct"] == pytest.approx(0.50, abs=1e-9)


def test_missing_cash_column_is_refused():
    trend = [{"timestamp": str(T0), "equity": 100.0},
             {"timestamp": str(T0 + np.timedelta64(6, "h")), "equity": 101.0}]
    capit = _capit(np.full(2, 100.0))
    with pytest.raises(ValueError, match="cash"):
        combine_curves(trend, capit)


def test_drawdown_of_the_combined_curve_is_reported():
    # Trend dips 10% then recovers; capit earns steadily -> combined dd < trend dd.
    dip = np.concatenate([np.linspace(100, 90, 30), np.linspace(90, 105, 30)])
    trend = _points(dip, cash_frac=0.8)
    capit = _capit(np.linspace(1000, 1080, 60))
    r = combine_curves(trend, capit)
    t_dd = 1 - 90 / 100
    assert 0 < r["max_drawdown"] < t_dd
