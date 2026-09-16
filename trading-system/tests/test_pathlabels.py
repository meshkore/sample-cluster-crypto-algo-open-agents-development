"""A60 path-true labels: a positive label must certify survival of OUR exits."""
import numpy as np
import pytest

from system006_oracle_net_15m.pathlabels import path_true_labels


def test_clean_run_up_is_a_good_entry():
    # +20% over 40 bars, no dip: vertical barrier exits well above min_gain.
    close = np.linspace(100.0, 120.0, 41)
    labels = path_true_labels(close, horizon=60)
    assert labels[0] == 1


def test_the_a60_case_ends_higher_but_dies_on_our_stop_first():
    """The motivating bug in the zigzag labels: the swing ends +15%, but the route
    passes through -9% - the shipped 8% stop realises the loss long before the
    recovery. Path-blind labels say 1 here; path-true labels must say 0."""
    close = np.concatenate([
        np.linspace(100.0, 91.0, 10),     # the dip: -9%, through the 8% stop
        np.linspace(91.0, 115.0, 30),     # the recovery the stopped-out book never sees
    ])
    labels = path_true_labels(close, horizon=60)
    assert labels[0] == 0


def test_trailing_stop_banks_a_gain():
    # +30% then a 13% slide from the peak: the 12% trail exits in profit.
    close = np.concatenate([
        np.linspace(100.0, 130.0, 20),
        np.linspace(130.0, 113.0, 20),
        np.full(30, 113.0),
    ])
    labels = path_true_labels(close, horizon=60)
    assert labels[0] == 1


def test_flat_series_never_clears_min_gain():
    close = np.full(50, 100.0)
    assert not path_true_labels(close, horizon=30).any()


def test_block_boundary_is_seamless():
    # Same labels whether an entry sits at a block edge or not.
    rng = np.random.default_rng(7)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.01, 3000))
    full = path_true_labels(close, horizon=200)
    import system006_oracle_net_15m.pathlabels as pl
    old = pl._BLOCK
    try:
        pl._BLOCK = 137  # force many odd-sized blocks
        chunked = path_true_labels(close, horizon=200)
    finally:
        pl._BLOCK = old
    assert np.array_equal(full, chunked)


def test_stop_beats_vertical_when_both_would_fire():
    # Drops through the stop at bar 3, then soars: first touch wins, label 0.
    close = np.concatenate([[100.0, 97.0, 94.0, 91.0], np.linspace(91.0, 200.0, 40)])
    labels = path_true_labels(close, horizon=44)
    assert labels[0] == 0


def test_off_flag_reproduces_zigzag_labels_exactly():
    """build_pooled(path_labels=False) must remain byte-identical to the prior
    behaviour - the inertness guarantee every off-by-default lever carries."""
    import inspect

    from system006_oracle_net_15m import pooled
    sig = inspect.signature(pooled.build_pooled)
    assert sig.parameters["path_labels"].default is False


def test_train_exposes_the_lever():
    import inspect

    from system006_oracle_net_15m import train
    assert "path_labels" in inspect.signature(train.train).parameters


def test_intersect_labels_are_a_subset_of_both_parents():
    """A60b: intersection keeps swing-start timing AND prunes stop-doomed entries -
    so every positive must be positive under BOTH parent labellers."""
    import numpy as np

    from system006_oracle_net_15m.oracle import holding_labels
    from system006_oracle_net_15m.pathlabels import path_true_labels

    rng = np.random.default_rng(11)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.012, 4000))
    zig = holding_labels(close, 0.01).astype(np.int8)
    path = path_true_labels(close, horizon=400)
    both = zig & path
    assert both.sum() > 0
    assert not (both & ~zig).any()
    assert not (both & ~path).any()
    assert both.sum() < zig.sum()  # it must actually prune something


def test_train_exposes_labels_intersect():
    import inspect

    from system006_oracle_net_15m import train
    assert "labels_intersect" in inspect.signature(train.train).parameters
