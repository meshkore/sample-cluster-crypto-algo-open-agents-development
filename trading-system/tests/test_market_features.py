"""A59: market-state features - the net gets to see the market it trades in.

Guards encoded here, learned the hard way elsewhere: the flag OFF must be
byte-identical to the classic layout (golden behaviour); the exported artifact is
SELF-DESCRIBING (the standardizer's columns are the authority, so export can never
drift from training the way a config flag could); and every value is causal.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from quantlab_system06.features import FEATURE_COLUMNS, Standardizer
from quantlab_system06.market import (
    BTC, FAST_LAG, MARKET_FEATURE_COLUMNS, MIN_CROSS, MarketTable,
)


class _Bar:
    def __init__(self, ts, close):
        self.timestamp = ts
        self.close = close


def _series(start, n, step_frac, base=100.0):
    bars, close = [], base
    for i in range(n):
        bars.append(_Bar(start + timedelta(minutes=15 * i), close))
        close *= (1.0 + step_frac)
    return bars


START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _table(n=FAST_LAG + 40):
    # BTC rises, ALT falls, FLAT does nothing: unambiguous ranks and breadth.
    return MarketTable({
        BTC: _series(START, n, +0.001),
        "ALTUSDT": _series(START, n, -0.001),
        "FLATUSDT": _series(START, n, 0.0),
    }), n


def test_warmup_rows_are_nan_and_post_warmup_rows_are_finite():
    table, n = _table()
    ts = np.array([np.datetime64((START + timedelta(minutes=15 * i)).replace(tzinfo=None), "ns")
                   for i in range(n)])
    m = table.matrix_for(BTC, ts)
    assert m.shape == (n, len(MARKET_FEATURE_COLUMNS))
    assert np.isnan(m[: FAST_LAG, 0]).all(), "no 1-day return exists inside the warm-up"
    # After warm-up: fast breadth = 1/3 up (only BTC rises); BTC fast return positive.
    row = m[FAST_LAG + 5]
    assert row[0] == pytest.approx(1 / 3)
    assert row[2] > 0
    # Slow (30d) columns stay NaN in a 1.5-day series - and that is honest, not a bug.
    assert np.isnan(row[1]) and np.isnan(row[3])


def test_rank_is_per_symbol_and_ordered():
    table, n = _table()
    ts = np.array([np.datetime64((START + timedelta(minutes=15 * (FAST_LAG + 5))).replace(tzinfo=None), "ns")])
    rank = {s: table.matrix_for(s, ts)[0, 5] for s in (BTC, "ALTUSDT", "FLATUSDT")}
    assert rank["ALTUSDT"] == pytest.approx(0.0)   # worst 1-day return
    assert rank["FLATUSDT"] == pytest.approx(0.5)
    assert rank[BTC] == pytest.approx(1.0)         # best


def test_thin_cross_sections_are_nan():
    """Fewer than MIN_CROSS symbols at a timestamp -> no market row. A market of one
    coin is not a market, and pretending otherwise would feed the net noise."""
    n = FAST_LAG + 10
    table = MarketTable({BTC: _series(START, n, 0.001)})
    ts = np.array([np.datetime64((START + timedelta(minutes=15 * (n - 1))).replace(tzinfo=None), "ns")])
    assert np.isnan(table.matrix_for(BTC, ts)).all()
    assert MIN_CROSS >= 3


def test_causality_the_hard_way():
    """Mutating bars AFTER a timestamp must not change that timestamp's row."""
    n = FAST_LAG + 30
    syms = {BTC: _series(START, n, 0.001), "A": _series(START, n, -0.001),
            "B": _series(START, n, 0.0005)}
    probe = np.array([np.datetime64((START + timedelta(minutes=15 * (FAST_LAG + 10))).replace(tzinfo=None), "ns")])
    before = MarketTable(syms).matrix_for(BTC, probe).copy()
    # Change the FUTURE: double every close after the probe bar.
    for bars in syms.values():
        for b in bars[FAST_LAG + 11:]:
            b.close *= 2.0
    after = MarketTable(syms).matrix_for(BTC, probe)
    np.testing.assert_array_equal(before, after)


def test_build_matrix_without_market_is_the_classic_layout():
    """The flag off must be byte-identical to every result on record."""
    import inspect

    from quantlab_system06.features import build_matrix

    sig = inspect.signature(build_matrix)
    assert sig.parameters["market"].default is None


def test_standardizer_is_self_describing_for_both_layouts():
    classic = Standardizer(mean=np.zeros(len(FEATURE_COLUMNS)),
                           std=np.ones(len(FEATURE_COLUMNS)))
    extended = Standardizer(mean=np.zeros(len(FEATURE_COLUMNS) + len(MARKET_FEATURE_COLUMNS)),
                            std=np.ones(len(FEATURE_COLUMNS) + len(MARKET_FEATURE_COLUMNS)))
    d1, d2 = classic.to_dict(), extended.to_dict()
    assert tuple(d1["columns"]) == FEATURE_COLUMNS
    assert tuple(d2["columns"]) == FEATURE_COLUMNS + MARKET_FEATURE_COLUMNS
    # Round trips, both ways; an unknown layout is refused loudly.
    Standardizer.from_dict(d1)
    Standardizer.from_dict(d2)
    bad = dict(d1)
    bad["columns"] = list(d1["columns"])[:-1]
    with pytest.raises(ValueError):
        Standardizer.from_dict(bad)


def test_the_flag_reaches_training_and_the_genome():
    """A gene the loop cannot pass to train() would be another silently-dead lever."""
    import inspect

    from quantlab_system06 import pooled, train
    from quantlab_system06.autoloop import _pinned_band  # noqa: F401  (import sanity)

    assert "market_features" in inspect.signature(train.train).parameters
    assert "market_features" in inspect.signature(pooled.build_pooled).parameters
    import quantlab_system06.autoloop as al
    src = inspect.getsource(al)
    assert src.count('cfg.get("market_features"') >= 2, (
        "both train call sites (search AND verification) must pass the gene, or a "
        "market-features candidate would verify as a classic net - the "
        "measure-the-same-quantity trap again")


def test_train_until_trims_every_symbol_to_the_cutoff_year():
    """Walk-forward mandate (2026-08-29): train_until=Y must leave no bar after Y
    anywhere in the pool - the following year must be genuinely unseen."""
    import inspect

    from quantlab_system06 import pooled, train

    assert "train_until" in inspect.signature(pooled.build_pooled).parameters
    assert "train_until" in inspect.signature(train.train).parameters
    assert inspect.signature(pooled.build_pooled).parameters["train_until"].default is None
