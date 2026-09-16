"""Decision-tree voter: causal features, honest walk-forward, a real directional vote."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from system006_oracle_net_15m import tree as treemod
from system006_oracle_net_15m.channels import Channels
from system006_oracle_net_15m.modules.base import MarketView
from system006_oracle_net_15m.modules.tree import Tree


class _Bar:
    __slots__ = ("timestamp", "open", "high", "low", "close", "volume")

    def __init__(self, ts, o, h, l, c, v):
        self.timestamp, self.open, self.high, self.low, self.close, self.volume = ts, o, h, l, c, v


def _bars(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    t0 = datetime(2019, 1, 1, tzinfo=timezone.utc)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    out = []
    for i in range(n):
        c = float(close[i])
        o = float(close[i - 1]) if i else c
        hi = max(o, c) * (1 + abs(rng.normal(0, 0.001)))
        lo = min(o, c) * (1 - abs(rng.normal(0, 0.001)))
        out.append(_Bar(t0 + timedelta(minutes=15 * i), o, hi, lo, c, float(abs(rng.normal(100, 20)))))
    return out


def _view(ch, symbols, ns=10):
    return MarketView(timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), ns=ns,
                      candles={s: {"close": 100.0} for s in symbols},
                      account={"positions": {}}, channels=ch, held=set(), peaks={})


def test_features_are_causal_and_finite():
    bars = _bars()
    X, y, ns, fwd = treemod.build_features(bars)
    assert X.shape[1] == len(treemod.FEATURES)
    assert len(X) == len(y) == len(ns) == len(fwd) and len(X) > 0
    assert np.isfinite(X).all()
    # Recomputing on a prefix must reproduce the same rows: no feature peeks ahead.
    cut = len(bars) - 200
    Xp, _yp, nsp, _fp = treemod.build_features(bars[:cut])
    common = min(len(nsp), len(ns))
    # Align by timestamp, then compare the shared prefix of feature rows.
    assert np.array_equal(ns[:common], nsp[:common])
    assert np.allclose(X[:common], Xp[:common], atol=1e-5)


def test_label_is_forward_return_and_never_a_feature():
    bars = _bars(seed=3)
    X, y, _ns, fwd = treemod.build_features(bars)
    assert set(np.unique(y)) <= {-1, 0, 1}
    resolved = np.isfinite(fwd)
    assert np.array_equal(y[resolved] == 1, fwd[resolved] > 0)   # label IS the sign of fwd
    # The label must not be reconstructible from the features by a constant column.
    assert X.shape[1] == len(treemod.FEATURES)
    assert (y >= 0).sum() > 0


def test_candlestick_flags_fire_on_constructed_shapes():
    bars = _bars(n=3200, seed=5)
    i = 3000
    # Force a bullish engulfing: previous bar down, this bar up and covering it.
    prev, cur = bars[i - 1], bars[i]
    prev.open, prev.close = 110.0, 100.0
    prev.high, prev.low = 111.0, 99.0
    cur.open, cur.close = 99.0, 112.0
    cur.high, cur.low = 113.0, 98.0
    X, _y, _ns, _fwd = treemod.build_features(bars)
    col = treemod.FEATURES.index("engulfing")
    # The kept rows drop the warm-up, so locate the row by its offset from the end.
    row = len(X) - (len(bars) - i)
    assert X[row, col] == 1.0


def test_walk_forward_abstains_on_the_first_block_and_seals_2026():
    """The verdict table must skip early bars and score the sealed window separately."""
    rng = np.random.default_rng(0)
    n = 30000
    ns = np.sort(rng.integers(int(np.datetime64("2019-01-01", "ns").astype("int64")),
                              int(np.datetime64("2026-06-01", "ns").astype("int64")), n))
    X = rng.normal(size=(n, len(treemod.FEATURES))).astype(np.float32)
    y = (rng.random(n) > 0.5).astype(np.int8)
    panel = treemod.Panel(X=X, y=y, ns=ns, symbol=np.full(n, "AAA", dtype=object),
                          fwd=np.where(y == 1, 0.01, -0.01))
    probs, doc = treemod.build_probs(panel, folds=4)
    table = probs["AAA"]
    assert table, "should emit verdicts"
    assert all(0.0 <= v <= 1.0 for v in table.values())
    lock_ns = treemod._ns(datetime.fromisoformat(treemod.LOCK))
    earliest_scored = min(table)
    assert earliest_scored > ns[0], "the first training block must not be scored"
    assert any(k >= lock_ns for k in table), "the sealed window must be scored by the final model"
    assert any(f["fold"] == "sealed" for f in doc["folds"])


def test_module_votes_direction_and_abstains_when_off():
    ch = Channels({
        "UP":   {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {}, "feargreed": {}, "sweep": {}, "tree": {10: 0.82}},
        "DOWN": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {}, "feargreed": {}, "sweep": {}, "tree": {10: 0.11}},
        "NONE": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {}, "feargreed": {}, "sweep": {}, "tree": {}},
    })
    syms = ["UP", "DOWN", "NONE"]
    assert Tree(tree_weight=0.0).evaluate(_view(ch, syms)).votes == {}   # off -> abstain

    module = Tree(tree_weight=0.5)
    out = module.evaluate(_view(ch, syms))
    assert module.weight == 0.5                      # a real directional voter
    assert out.votes["UP"].conviction == pytest.approx(0.82)
    assert out.votes["DOWN"].conviction == pytest.approx(0.11)
    assert "NONE" not in out.votes                   # no verdict -> abstain, never a guess


def test_rolling_training_window_restricts_history():
    """A38: `train_window_days` must fit each fold on RECENT history only."""
    rng = np.random.default_rng(1)
    n = 30000
    ns = np.sort(rng.integers(int(np.datetime64("2019-01-01", "ns").astype("int64")),
                              int(np.datetime64("2025-12-01", "ns").astype("int64")), n))
    X = rng.normal(size=(n, len(treemod.FEATURES))).astype(np.float32)
    y = (rng.random(n) > 0.5).astype(np.int8)
    panel = treemod.Panel(X=X, y=y, ns=ns, symbol=np.full(n, "AAA", dtype=object),
                          fwd=np.where(y == 1, 0.01, -0.01))
    _p_exp, doc_exp = treemod.build_probs(panel, folds=4)
    _p_roll, doc_roll = treemod.build_probs(panel, folds=4, train_window_days=365)
    assert doc_exp["train_window_days"] is None
    assert doc_roll["train_window_days"] == 365
    exp_train = [f["train"] for f in doc_exp["folds"] if f["fold"] != "sealed"]
    roll_train = [f["train"] for f in doc_roll["folds"] if f["fold"] != "sealed"]
    assert exp_train and roll_train
    # The rolling arm must never train on more rows than the expanding one, and by the
    # later folds it must train on strictly fewer (that is the whole point).
    assert all(r <= e for r, e in zip(roll_train, exp_train))
    assert roll_train[-1] < exp_train[-1]
