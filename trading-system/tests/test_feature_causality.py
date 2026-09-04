"""AUD-1: prove the 44 features cannot see the future, by truncation, not by reading.

The claim in features.py is that every column is causal because it is a subset of the
instrument's panel, which is computed causally. That is a claim about ~91 columns of
indicator code written at another time for another system, and the model consumes it
at every bar of every decision. Nothing in the suite tested it directly.

The definition being enforced: a feature at bar `i` computed from `bars[:i+1]` must be
IDENTICAL to the same feature at bar `i` computed from the full series. If shortening
the future changes the past, the past was reading the future - through a centred
window, a full-series normalisation, a look-ahead smoother, whatever. Truncation
catches every one of those at once, which code reading does not.

The probe uses a synthetic random walk, so it runs in milliseconds without market
data, and asserts bit-for-bit equality (not approx): causal arithmetic on identical
inputs has no legitimate source of difference.
"""

from __future__ import annotations

import numpy as np
import pytest

from quantlab_backtester.models import Bar
from quantlab_system06.features import FEATURE_COLUMNS, Standardizer, build_matrix

N_BARS = 700          # > 252-bar return window + slack, so every column leaves warm-up
CUT = 520             # where the truncated series ends; leaves a long comparable prefix


def _synthetic_bars(n: int, seed: int = 7) -> list[Bar]:
    """A plausible OHLCV random walk - trending, gappy, with volume spikes."""
    rng = np.random.default_rng(seed)
    log_close = np.cumsum(rng.normal(0.0002, 0.01, n)) + np.log(100.0)
    close = np.exp(log_close)
    spread = np.abs(rng.normal(0, 0.004, n)) + 1e-4
    open_ = close * np.exp(rng.normal(0, 0.003, n))
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    volume = np.exp(rng.normal(10, 0.8, n))
    from datetime import timezone

    ts = np.datetime64("2024-01-01T00:00") + np.arange(n) * np.timedelta64(15, "m")
    return [
        Bar(timestamp=t.astype("datetime64[us]").item().replace(tzinfo=timezone.utc),
            open=float(o), high=float(h),
            low=float(lo), close=float(c), volume=float(v))
        for t, o, h, lo, c, v in zip(ts, open_, high, low, close, volume)
    ]


@pytest.fixture(scope="module")
def full_and_truncated():
    bars = _synthetic_bars(N_BARS)
    full, _ = build_matrix(bars)
    trunc, _ = build_matrix(bars[:CUT])
    return full, trunc


def test_no_feature_changes_when_the_future_is_removed(full_and_truncated):
    full, trunc = full_and_truncated
    bad = []
    for j, name in enumerate(FEATURE_COLUMNS):
        a, b = full[:CUT, j], trunc[:, j]
        both_nan = np.isnan(a) & np.isnan(b)
        equal = (a == b) | both_nan
        if not equal.all():
            first = int(np.flatnonzero(~equal)[0])
            bad.append(f"{name}: first divergence at bar {first} "
                       f"({a[first]!r} vs {b[first]!r})")
    assert not bad, (
        "these features change when FUTURE bars are removed, so they were reading "
        "the future:\n  " + "\n  ".join(bad))


def test_warmup_nans_are_identical_too(full_and_truncated):
    """Where a column is NaN must also be causal: a warm-up front that shifts with
    series length would silently change which rows finite_rows() admits to training."""
    full, trunc = full_and_truncated
    mismatch = np.isnan(full[:CUT]) != np.isnan(trunc)
    assert not mismatch.any(), (
        f"NaN pattern depends on the future in columns "
        f"{[FEATURE_COLUMNS[j] for j in sorted(set(np.where(mismatch)[1].tolist()))]}")


def test_the_standardizer_cannot_smuggle_the_future_back_in(full_and_truncated):
    """Standardisation is the one step after the panel where full-series statistics
    could re-enter. Fitted on a prefix (as training does), applied to bar i, the
    output must again be identical whether or not the future existed."""
    full, trunc = full_and_truncated
    train_rows = np.arange(300, 500)          # a prefix slice, as build_pooled uses
    scaler_full = Standardizer.fit(full, train_rows)
    scaler_trunc = Standardizer.fit(trunc, train_rows)
    np.testing.assert_array_equal(scaler_full.mean, scaler_trunc.mean)
    np.testing.assert_array_equal(scaler_full.std, scaler_trunc.std)
    np.testing.assert_array_equal(
        scaler_full.transform(full[:CUT]), scaler_trunc.transform(trunc))
