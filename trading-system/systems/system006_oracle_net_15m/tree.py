"""A decision-tree directional voter: candlestick shapes + probabilistic statistics.

Operator idea A32 (2026-08-25): grow the decision-tree idea with two kinds of branch —
**probabilistic statistics** (what has price done, in which volatility/momentum bucket)
and **candlestick shapes** of the prior bars (engulfing, pin, inside bar, wick
asymmetry). This is deliberately a DIFFERENT DISCIPLINE from the oracle-clone TCN:
different features, a different label, and a different inductive bias (axis-aligned
splits on hand-built structure, not learned convolutions over a 96-bar window).

Why that matters. The champion's sealed-2026 readout is ~+0.4% on 87 trades at normal
exposure — the trades are break-even, so the gap is EDGE, not sizing. A second opinion
built on different information is the only thing that can add edge where the first one
has none; it is also the second directional voter that `consensus_k >= 2` has needed
since A12, and the first member of the A33 multi-discipline committee.

Honesty rules, identical to `meta.py`:
  - Every feature is causal (bar `i` uses bars `<= i` only).
  - The label is the forward return over `HORIZON` bars — used for FITTING only.
  - Research verdicts come from an expanding, time-purged walk-forward: a bar's
    probability is issued by a model trained only on bars whose labels had already
    RESOLVED before that fold began, with an embargo band dropped around the split.
  - The sealed 2026 window is scored by the final research-only model, which never saw
    it. 2026 never influences fitting or selection.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

from . import universe
from .dataset import LOCK, Dataset
from quantlab_catalog.paths import DATA_ROOT
from quantlab_catalog.paths import workspace as _workspace

HORIZON = 32          # bars ahead the label looks (8h at 15m) — a swing, not a scalp
BAR_SECONDS = 900
FEATURES = [
    # -- candlestick shape of the current and prior bars (the operator's "formas de velas")
    "body", "upper_wick", "lower_wick", "wick_asymmetry", "direction",
    "body_prev", "upper_prev", "lower_prev", "direction_prev",
    "engulfing", "inside_bar", "pin_bar",
    # -- probabilistic statistics (the operator's "estadísticas probabilísticas")
    "ret_4", "ret_16", "ret_96", "range_pos_96", "range_pos_480",
    "vol_ratio", "volume_z", "trend_dist",
]


def _ns(ts: datetime) -> int:
    return int(np.datetime64(ts.replace(tzinfo=None), "ns").astype("int64"))


def _trailing(x: np.ndarray, span: int) -> tuple[np.ndarray, np.ndarray]:
    """Causal trailing (mean, std) over `span` bars via cumsums — bars <= i only."""
    n = len(x)
    idx = np.arange(n)
    lo = np.maximum(0, idx - span + 1)
    cnt = (idx - lo + 1).astype(float)
    c1 = np.concatenate([[0.0], np.cumsum(x)])
    c2 = np.concatenate([[0.0], np.cumsum(x * x)])
    s1 = c1[idx + 1] - c1[lo]
    s2 = c2[idx + 1] - c2[lo]
    mean = s1 / cnt
    return mean, np.sqrt(np.maximum(0.0, s2 / cnt - mean * mean))


def _trailing_extreme(x: np.ndarray, span: int, kind: str) -> np.ndarray:
    """Causal trailing max/min over `span` bars (inclusive of bar i)."""
    n = len(x)
    out = np.empty(n)
    fn = np.maximum.accumulate if kind == "max" else np.minimum.accumulate
    # Simple O(n * span/step) is too slow; use a strided approach via pandas-free trick:
    # for our spans (96/480) a sliding window over a cumulative structure is fine.
    pad = np.full(span - 1, x[0])
    padded = np.concatenate([pad, x])
    strides = np.lib.stride_tricks.sliding_window_view(padded, span)
    out = strides.max(axis=1) if kind == "max" else strides.min(axis=1)
    return out


def build_features(bars) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Causal feature matrix, label, epoch-ns index and forward return for one symbol.

    Returns `(X, y, ns, fwd)` where `y` is 1 when the forward `HORIZON`-bar return is
    positive and `fwd` is that return itself (NaN where unresolved), kept so an
    experiment can measure the SIZE of an edge and not merely its direction. The last
    `HORIZON` rows have no resolved label and are marked -1.
    """
    o = np.array([b.open for b in bars], dtype=float)
    h = np.array([b.high for b in bars], dtype=float)
    lo_ = np.array([b.low for b in bars], dtype=float)
    c = np.array([b.close for b in bars], dtype=float)
    v = np.array([b.volume for b in bars], dtype=float)
    n = len(c)
    if n < 600:
        return (np.zeros((0, len(FEATURES))), np.zeros(0, dtype=np.int8),
                np.zeros(0, dtype=np.int64), np.zeros(0))

    rng = np.maximum(h - lo_, 1e-12)
    body = (c - o) / rng
    body_hi = np.maximum(o, c)
    body_lo = np.minimum(o, c)
    upper = (h - body_hi) / rng
    lower = (body_lo - lo_) / rng
    asym = upper - lower
    direction = np.sign(c - o)

    def prev(x):
        return np.concatenate([[x[0]], x[:-1]])

    body_p, upper_p, lower_p, dir_p = prev(body), prev(upper), prev(lower), prev(direction)
    # Bullish engulfing: this body covers the previous body and flips it up.
    engulf = ((direction > 0) & (dir_p < 0)
              & (c >= prev(o)) & (o <= prev(c))).astype(float)
    inside = ((h <= prev(h)) & (lo_ >= prev(lo_))).astype(float)
    # Pin / hammer: one wick dominates a small body.
    pin = ((np.abs(body) < 0.35) & (np.maximum(upper, lower) > 0.5)).astype(float)

    def ret(k):
        r = np.zeros(n)
        if n > k:
            r[k:] = c[k:] / np.maximum(c[:-k], 1e-12) - 1.0
        return r

    hi96, lo96 = _trailing_extreme(h, 96, "max"), _trailing_extreme(lo_, 96, "min")
    hi480, lo480 = _trailing_extreme(h, 480, "max"), _trailing_extreme(lo_, 480, "min")
    pos96 = (c - lo96) / np.maximum(hi96 - lo96, 1e-12)
    pos480 = (c - lo480) / np.maximum(hi480 - lo480, 1e-12)

    logret = np.zeros(n)
    logret[1:] = np.diff(np.log(np.maximum(c, 1e-12)))
    _, sd_s = _trailing(logret, 96)
    _, sd_l = _trailing(logret, 2880)
    vol_ratio = np.where(sd_l > 1e-12, sd_s / np.maximum(sd_l, 1e-12), 1.0)
    v_mean, v_std = _trailing(v, 96)
    volume_z = (v - v_mean) / np.maximum(v_std, 1e-12)
    tm, _ = _trailing(c, 2880)
    trend_dist = c / np.maximum(tm, 1e-12) - 1.0

    X = np.column_stack([
        body, upper, lower, asym, direction,
        body_p, upper_p, lower_p, dir_p,
        engulf, inside, pin,
        ret(4), ret(16), ret(96), pos96, pos480,
        vol_ratio, volume_z, trend_dist,
    ]).astype(np.float32)

    y = np.full(n, -1, dtype=np.int8)
    fwd = np.full(n, np.nan)
    if n > HORIZON:
        fwd[:-HORIZON] = c[HORIZON:] / np.maximum(c[:-HORIZON], 1e-12) - 1.0
        y[:-HORIZON] = (fwd[:-HORIZON] > 0).astype(np.int8)
    ns = np.array([_ns(b.timestamp) for b in bars], dtype=np.int64)

    warm = 2880  # trailing statistics need history before they mean anything
    keep = np.zeros(n, dtype=bool)
    keep[warm:] = True
    keep &= np.isfinite(X).all(axis=1)
    return X[keep], y[keep], ns[keep], fwd[keep]


@dataclass
class Panel:
    X: np.ndarray
    y: np.ndarray
    ns: np.ndarray
    symbol: np.ndarray
    fwd: np.ndarray


def gather(data_root: str = str(DATA_ROOT), symbols: list[str] | None = None,
           interval: str = "15m") -> Panel:
    """Pooled, time-ordered feature panel across the universe (research + sealed)."""
    symbols = symbols or universe.load()
    dataset = Dataset(data_root, symbols=symbols, interval=interval)
    combined = dataset.combined()
    Xs, ys, nss, syms, fwds = [], [], [], [], []
    for symbol in symbols:
        bars = combined.get(symbol)
        if not bars:
            continue
        X, y, ns, fwd = build_features(bars)
        if len(ns) == 0:
            continue
        Xs.append(X); ys.append(y); nss.append(ns); fwds.append(fwd)
        syms.append(np.full(len(ns), symbol, dtype=object))
    if not Xs:
        raise ValueError("no symbol produced tree features")
    X = np.concatenate(Xs); y = np.concatenate(ys)
    ns = np.concatenate(nss); symbol = np.concatenate(syms); fwd = np.concatenate(fwds)
    order = np.argsort(ns, kind="mergesort")
    return Panel(X=X[order], y=y[order], ns=ns[order], symbol=symbol[order], fwd=fwd[order])


def _model(seed: int = 42):
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(
        max_depth=4, max_iter=150, learning_rate=0.06,
        l2_regularization=1.0, min_samples_leaf=200, random_state=seed,
    )


def build_probs(panel: Panel, *, folds: int = 6, embargo_bars: int = 96,
                min_train_frac: float = 0.25, seed: int = 42,
                train_window_days: int | None = None
                ) -> tuple[dict[str, dict[int, float]], dict[str, Any]]:
    """Expanding, time-purged P(up) per bar; the sealed window uses the final model.

    A fold's training set keeps only bars whose label had RESOLVED before the fold
    starts (entry + HORIZON < fold start) and drops an `embargo_bars` band adjacent to
    the split, so no label straddles the boundary. Bars in the first (train-only) block
    receive no probability at all — the module abstains on them rather than guessing.

    `train_window_days` (idea A38, adaptive training) limits each fold to the most
    RECENT window of history instead of every past bar. Markets are non-stationary: an
    edge measured over eight years can invert in the ninth, so a model fitted on the
    last year may track the current market better than one fitted on the average of all
    of it. None = the expanding window (every resolved past bar), the original behaviour.
    """
    lock_ns = _ns(datetime.fromisoformat(LOCK))
    horizon_ns = HORIZON * BAR_SECONDS * 1_000_000_000
    embargo_ns = embargo_bars * BAR_SECONDS * 1_000_000_000

    research = np.flatnonzero((panel.ns < lock_ns) & (panel.y >= 0))
    sealed = np.flatnonzero(panel.ns >= lock_ns)
    out: dict[str, dict[int, float]] = {}
    docs: list[dict] = []

    def emit(rows, values):
        for row, value in zip(rows, values):
            out.setdefault(str(panel.symbol[row]), {})[int(panel.ns[row])] = float(value)

    n = len(research)
    if n < 5000:
        raise ValueError(f"only {n} research rows; too few to fit a tree voter")
    min_train = int(n * min_train_frac)
    span = max(1, (n - min_train) // folds)
    for k in range(folds):
        a = min_train + k * span
        b = n if k == folds - 1 else a + span
        test_rows = research[a:b]
        if len(test_rows) == 0:
            continue
        t0 = panel.ns[test_rows[0]]
        past = research[:a]
        resolved = panel.ns[past] + horizon_ns < t0 - embargo_ns
        if train_window_days is not None:
            window_ns = int(train_window_days) * 86_400 * 1_000_000_000
            resolved &= panel.ns[past] >= t0 - window_ns
        train_rows = past[resolved]
        if len(train_rows) < max(1000, min_train // 4):
            continue
        model = _model(seed)
        model.fit(panel.X[train_rows], panel.y[train_rows])
        emit(test_rows, model.predict_proba(panel.X[test_rows])[:, 1])
        docs.append({"fold": k, "train": int(len(train_rows)), "test": int(len(test_rows)),
                     "purged": int(a - len(train_rows))})

    # The sealed half: one model fitted on ALL resolved research rows, then applied to
    # 2026. It never sees a 2026 row, so the readout stays honest.
    if len(sealed):
        resolved = panel.ns[research] + horizon_ns < lock_ns
        if train_window_days is not None:
            window_ns = int(train_window_days) * 86_400 * 1_000_000_000
            resolved &= panel.ns[research] >= lock_ns - window_ns
        final_rows = research[resolved]
        if len(final_rows) >= 1000:
            model = _model(seed)
            model.fit(panel.X[final_rows], panel.y[final_rows])
            emit(sealed, model.predict_proba(panel.X[sealed])[:, 1])
            docs.append({"fold": "sealed", "train": int(len(final_rows)),
                         "test": int(len(sealed)), "purged": 0})

    document = {"horizon_bars": HORIZON, "folds": docs, "features": FEATURES,
                "rows": int(len(panel.ns)), "research_rows": int(n),
                "train_window_days": train_window_days}
    return out, document


def write_tree(probs: dict[str, dict[int, float]], out_path: str) -> None:
    """Write the per-symbol directional channel to an .npz the Channels loader reads."""
    payload: dict[str, np.ndarray] = {}
    for sym, table in probs.items():
        if not table:
            continue
        ns = np.array(sorted(table), dtype=np.int64)
        payload[f"{sym}__tree_ns"] = ns
        payload[f"{sym}__tree"] = np.array([table[int(x)] for x in ns], dtype=np.float32)
    np.savez(out_path, **payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--data-root", default=str(DATA_ROOT))
    parser.add_argument("--out", default=str(_workspace("system06") / "tree.npz"))
    parser.add_argument("--folds", type=int, default=6)
    args = parser.parse_args(argv)
    symbols = [s for s in args.symbols.split(",") if s] if args.symbols else universe.load()
    panel = gather(args.data_root, symbols, args.interval)
    print(f"tree panel: {len(panel.ns):,} rows over {len(symbols)} symbols", flush=True)
    probs, doc = build_probs(panel, folds=args.folds)
    write_tree(probs, args.out)
    print(json.dumps(doc, indent=1))
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
