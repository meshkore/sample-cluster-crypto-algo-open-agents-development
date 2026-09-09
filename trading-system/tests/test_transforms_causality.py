"""The shared transforms are causal, and the fast forms agree with the slow ones.

Two properties, and the second is the one that catches real bugs.

CAUSALITY is checked by truncation: recompute the series from `x[:i+1]` alone and
require the value at `i` to be unchanged. That is the definition, applied directly, and
it cannot be satisfied by an implementation that peeks - unlike a test that only checks
the shape of the output.

AGREEMENT is checked against a brute-force reference. Every function here has a fast
cumulative or strided form, and those are exactly where an off-by-one turns into a
look-ahead that no amount of reading catches. The slow version is obviously correct and
absurdly inefficient; that is the point of having it.

This laboratory has had one leak of this kind reach production reasoning already, so
the transforms get the treatment before anything is built on them rather than after.
"""

from __future__ import annotations

import numpy as np
import pytest

from quantlab_catalog import transforms as tf

FUNCS = [
    ("rolling_mean", tf.rolling_mean),
    ("rolling_std", tf.rolling_std),
    ("rolling_z", tf.rolling_z),
    ("robust_z", tf.robust_z),
    ("rolling_percentile", tf.rolling_percentile),
    ("relative_change", tf.relative_change),
    ("log_change", tf.log_change),
    ("efficiency", tf.efficiency),
]


@pytest.fixture
def series() -> np.ndarray:
    rng = np.random.default_rng(20260909)
    # A random walk in POSITIVE territory, so log_change is defined, with a couple of
    # violent jumps: the tails are where robust_z earns its place and where a naive
    # rolling std stops describing anything.
    x = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, 400)))
    x[150] *= 1.35
    x[151] *= 0.72
    return x


@pytest.mark.parametrize("name,fn", FUNCS, ids=[n for n, _ in FUNCS])
def test_no_value_changes_when_the_future_is_removed(name, fn, series):
    """The definition of causal, applied literally."""
    window = 20
    full = fn(series, window)
    for i in (60, 155, 300, len(series) - 1):
        truncated = fn(series[: i + 1], window)
        a, b = full[i], truncated[-1]
        if np.isnan(a) and np.isnan(b):
            continue
        assert a == pytest.approx(b, rel=1e-9, abs=1e-9), (
            f"{name}[{i}] changed when the future was removed: {a} -> {b}")


def test_signed_log1p_is_pointwise_and_therefore_trivially_causal(series):
    out = tf.signed_log1p(series)
    assert out[10] == pytest.approx(tf.signed_log1p(series[:11])[-1])
    assert tf.signed_log1p([-3.0, 0.0, 3.0]) == pytest.approx(
        [-np.log(4), 0.0, np.log(4)])


# --- the fast forms must equal the obvious ones ------------------------------------

def test_rolling_mean_matches_brute_force(series):
    w = 15
    fast = tf.rolling_mean(series, w)
    for i in range(w - 1, len(series)):
        assert fast[i] == pytest.approx(series[i - w + 1: i + 1].mean(), rel=1e-9)
    assert np.isnan(fast[: w - 1]).all(), "the warm-up must be NaN, never zero"


def test_rolling_std_matches_brute_force(series):
    w = 15
    fast = tf.rolling_std(series, w)
    for i in range(w - 1, len(series), 7):
        assert fast[i] == pytest.approx(series[i - w + 1: i + 1].std(), rel=1e-6)


def test_rolling_std_is_never_negative_under_float_error():
    """mean(x^2) - mean(x)^2 goes negative on a constant series. It is clipped."""
    flat = np.full(50, 12345.6789)
    out = tf.rolling_std(flat, 10)
    assert np.all(out[9:] >= 0.0) and np.all(out[9:] < 1e-6)


def test_rolling_percentile_matches_brute_force_and_is_bounded(series):
    w = 25
    fast = tf.rolling_percentile(series, w)
    for i in range(w - 1, len(series), 11):
        win = series[i - w + 1: i + 1]
        expected = ((win < series[i]).sum() + 0.5 * (win == series[i]).sum()) / w
        assert fast[i] == pytest.approx(expected)
    finite = fast[np.isfinite(fast)]
    assert finite.min() >= 0.0 and finite.max() <= 1.0


def test_a_constant_series_sits_in_the_middle_of_its_own_percentile():
    """Midrank convention. Scoring 1.0 would read as 'never higher than now'."""
    out = tf.rolling_percentile(np.full(40, 7.0), 10)
    assert out[20] == pytest.approx(0.5)


def test_robust_z_ignores_a_spike_that_rolling_z_cannot(series):
    """A crash inflates the std, so ordinary z-scores judge the bars AFTER it against a
    distribution the crash itself created. The median barely moves."""
    w = 30
    plain = tf.rolling_z(series, w)
    robust = tf.robust_z(series, w)
    after = slice(152, 175)
    assert np.nanmax(np.abs(robust[after])) > np.nanmax(np.abs(plain[after])), (
        "after a spike the robust score should still register movement while the "
        "plain one has been flattened by its own inflated denominator")


def test_robust_z_and_rolling_z_agree_on_clean_normal_data():
    """The 1.4826 factor exists for this. Without it the two are on different scales
    and a threshold tuned on one means something else on the other."""
    rng = np.random.default_rng(7)
    x = rng.normal(0, 1, 4000)
    w = 500
    a, b = tf.rolling_z(x, w), tf.robust_z(x, w)
    ratio = np.nanstd(b[w:]) / np.nanstd(a[w:])
    assert 0.9 < ratio < 1.1, f"scales disagree by {ratio:.2f}x"


def test_log_change_refuses_non_positive_bases():
    x = np.array([1.0, 2.0, 0.0, -1.0, 5.0, 6.0])
    out = tf.log_change(x, 2)
    assert np.isnan(out[4]), "log of a ratio with a zero base must not be invented"


def test_efficiency_is_one_on_a_straight_line_and_low_on_a_round_trip():
    straight = np.arange(1.0, 101.0)
    assert tf.efficiency(straight, 20)[50] == pytest.approx(1.0, rel=1e-6)
    zigzag = np.tile([100.0, 101.0], 60)
    assert tf.efficiency(zigzag, 20)[80] < 0.1


def test_an_empty_series_raises_instead_of_returning_nothing():
    with pytest.raises(ValueError, match="empty series"):
        tf.rolling_z([], 5)


def test_a_series_shorter_than_its_window_is_all_nan():
    out = tf.rolling_z(np.arange(5.0), 20)
    assert out.shape == (5,) and np.isnan(out).all()
