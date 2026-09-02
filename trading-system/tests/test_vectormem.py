"""Vector memory (A74): it may only remember the past, and it must admit ignorance.

Nearest-neighbour retrieval is the easiest way in this codebase to read the future by
accident - a neighbour a few bars ahead, resolving a week later, would hand the model
tomorrow's answer through a lookup table and every backtest would look brilliant. So
the leakage rule is tested first and hardest.
"""

from __future__ import annotations

import numpy as np
import pytest

from quantlab_system06 import vectormem


def _rows(n=600, seed=0, f=6):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, f))
    # A learnable structure: the first coordinate decides the outcome.
    won = (X[:, 0] > 0).astype(float)
    resolved = np.arange(n, dtype=np.int64) * 10**9
    return X, won, resolved


def test_a_neighbour_that_resolved_after_the_query_is_never_used():
    """The whole ballgame. The store holds a perfectly predictive answer for every
    query, but ONLY in rows that resolve later - so a leaking implementation scores a
    perfect hit rate and an honest one abstains."""
    X, _won, resolved = _rows(n=400)
    # Every stored outcome is 1.0, and every one of them resolves AFTER all queries.
    store = vectormem.build_store(X, np.ones(len(X)), resolved + 10**15)
    out = vectormem.query_blocks(store, X, resolved, k=10, blocks=4)
    assert not out["answered"].any(), "answered a query from the future"
    assert np.isnan(out["hit_rate"]).all()


def test_it_finds_real_structure_when_the_past_actually_contains_it():
    """The other half: having refused the future, it must still be useful. With the
    structure present in genuinely earlier rows, queries in the second half of time
    should be answered, and answered better than chance."""
    X, won, resolved = _rows(n=800, seed=1)
    store = vectormem.build_store(X, won, resolved)
    half = len(X) // 2
    out = vectormem.query_blocks(store, X[half:], resolved[half:], k=15, blocks=4)
    assert out["answered"].any(), "nothing answered although the past was available"
    s = vectormem.summarise(out, won[half:])
    assert s["edge"] is not None and s["edge"] > 0.3, s


def test_an_unfamiliar_query_is_reported_as_far_away():
    """The distance IS the confidence. A query nowhere near anything seen before must
    come back with a large distance so a module can abstain instead of guessing."""
    X, won, resolved = _rows(n=500, seed=2)
    store = vectormem.build_store(X, won, resolved)
    near = X[:5]
    far = np.full((5, X.shape[1]), 50.0)
    out = vectormem.query_blocks(store, np.vstack([near, far]),
                                 np.full(10, resolved[-1] + 10**9), k=10, blocks=1)
    assert np.nanmean(out["distance"][5:]) > 5 * np.nanmean(out["distance"][:5])


def test_an_empty_memory_abstains_instead_of_guessing():
    """A memory with nothing to say must return NaN, not the base rate. A default that
    looks like an opinion is how a dead module reads as a working one."""
    X, won, resolved = _rows(n=50)
    store = vectormem.build_store(X, won, resolved)
    out = vectormem.query_blocks(store, X, resolved - 10**15, k=10, blocks=2,
                                 min_support=5)
    assert not out["answered"].any() and np.isnan(out["hit_rate"]).all()


def test_features_are_standardised_so_one_loud_feature_cannot_define_similarity():
    """The A32 set mixes candle bodies in [-1,1] with unbounded volume z-scores. On raw
    distances the loud feature would BE the metric."""
    rng = np.random.default_rng(3)
    X = np.column_stack([rng.normal(0, 0.01, 400), rng.normal(0, 1000.0, 400)])
    store = vectormem.build_store(X, (X[:, 0] > 0).astype(float),
                                  np.arange(400, dtype=np.int64) * 10**9)
    assert store.X.std(axis=0) == pytest.approx(np.ones(2), abs=0.05)


def test_summarise_refuses_to_report_an_edge_it_cannot_support():
    out = {"answered": np.zeros(10, bool), "hit_rate": np.full(10, np.nan),
           "distance": np.full(10, np.nan), "support": np.zeros(10, int)}
    s = vectormem.summarise(out, np.zeros(10))
    assert s["edge"] is None and "too few" in s["note"]
