"""A110: weight training toward recent bars, because the market is not stationary.

Operator, 2026-09-05: "the market evolves with time, depending on the volume of
capital we have, depending on what the algorithms learn... something that worked in
2020 did not work in 2025. So maybe you have to have the maximum number of data
possible" — the honest reading of which is: keep every bar, but let the model CARE
more about the recent regime. Exponential decay by age does exactly that, and unlike
truncating the history it costs no samples.

The two properties that make it a measurement rather than a knob:
  * age is wall-clock and universe-wide, not per-symbol row index,
  * the weights are normalised to mean 1, so the half-life cannot move results by
    quietly changing the effective learning rate.
"""

from __future__ import annotations

import numpy as np
import pytest

from quantlab_system06.train import _recency_weights


class _Pooled:
    """Two symbols on one clock: one with long history, one that listed late."""

    def __init__(self, stamps_ns):
        self.stamps_ns = np.asarray(stamps_ns, dtype=np.int64)
        self.labels = np.zeros(len(self.stamps_ns), dtype=np.int8)


YEAR_NS = int(365.25 * 24 * 3600 * 1e9)


def _pooled_years(offsets_years):
    base = np.datetime64("2026-01-01T00:00:00", "ns").astype(np.int64)
    return _Pooled([base - int(o * YEAR_NS) for o in offsets_years])


def test_a_bar_one_half_life_older_weighs_half_as_much():
    p = _pooled_years([0.0, 2.0, 4.0])          # now, 2y ago, 4y ago
    w = _recency_weights(p, half_life_years=2.0)
    assert w[0] / w[1] == pytest.approx(2.0, rel=1e-4)
    assert w[1] / w[2] == pytest.approx(2.0, rel=1e-4)


def test_the_weights_average_to_one():
    """Otherwise the half-life silently rescales every gradient and the A/B measures
    the effective learning rate instead of the hypothesis."""
    for hl in (0.5, 1.0, 2.0, 4.0):
        w = _recency_weights(_pooled_years([0, 1, 2, 3, 4, 5, 6, 7]), hl)
        assert float(w.mean()) == pytest.approx(1.0, rel=1e-5)


def test_age_is_wall_clock_not_row_index():
    """The trap this avoids: two symbols pooled back to back, one listed in 2018 and
    one in 2024. By row index, the late coin's first row looks as 'old' as the early
    coin's first row — the weighting would then encode HOW MUCH HISTORY A COIN HAS
    rather than how recent a bar is, which is a different (and useless) quantity."""
    base = np.datetime64("2026-01-01T00:00:00", "ns").astype(np.int64)
    old_coin = [base - int(o * YEAR_NS) for o in (8.0, 7.0)]     # rows 0,1: ancient
    new_coin = [base - int(o * YEAR_NS) for o in (1.0, 0.0)]     # rows 2,3: recent
    w = _recency_weights(_Pooled(old_coin + new_coin), half_life_years=2.0)
    assert w[0] < w[1] < w[2] < w[3], "weights must follow the calendar, not the index"
    # the new coin's FIRST row must outweigh the old coin's LAST row
    assert w[2] > w[1]


def test_off_by_default_and_degenerate_inputs_are_safe():
    p = _pooled_years([0.0, 3.0])
    np.testing.assert_array_equal(_recency_weights(p, 0.0), np.ones(2, dtype=np.float32))
    empty = _Pooled([])
    assert len(_recency_weights(empty, 2.0)) == 0


def test_train_takes_the_lever_and_composes_it_with_uniqueness():
    """Uniqueness answers 'is this sample redundant', recency answers 'is it still
    relevant'. Different questions, so they multiply rather than replace."""
    import inspect

    from quantlab_system06 import train as trainmod

    sig = inspect.signature(trainmod.train)
    assert "recency_half_life" in sig.parameters
    assert sig.parameters["recency_half_life"].default == 0.0, "must be off by default"
    src = inspect.getsource(trainmod.train)
    assert "uniq_w = rw if uniq_w is None else uniq_w * rw" in src


def test_the_pooled_table_carries_the_clock():
    """_recency_weights is only honest if pooled.stamps_ns is aligned with Xz rows."""
    import inspect

    from quantlab_system06 import pooled as pooledmod

    assert "stamps_ns" in inspect.getsource(pooledmod.Pooled)
    src = inspect.getsource(pooledmod.build_pooled)
    assert "stamp_blocks.append" in src and "stamps_ns=stamps_all" in src
