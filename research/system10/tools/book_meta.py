"""Meta-labelling sizer for the book (book audit 2026-10-15, phase 2 item 5; Lopez de Prado 2018).

For test year N: the base book's trades of years < N (each year's own walk-forward signals)
are labelled won / lost; a small net reads, at the entry bar, the 44 market columns, the
forecast, the regime and breadth, and gives P(win). In year N every entry stake is scaled by
clip(p / p-bar, lo, hi), p-bar = mean P on the training trades. Nothing of N or later is fitted.
Needs rnd/book_feats.npz (`book_inputs.py feats`).
"""

from __future__ import annotations

import numpy as np

import book_inputs as BI

_FEATS: dict = {}


def _feats() -> dict:
    if not _FEATS:
        _FEATS.update(BI.load_feats())
    return _FEATS


def _rows(lab, s: str, bars: np.ndarray, N: int) -> np.ndarray:
    """Feature rows for symbol s at its input-array bars (forecast of year N's signals)."""
    f = _feats()[s]
    d = lab.per[s]
    pos = np.clip(np.searchsorted(f["ns"], d["ns"][bars]), 0, len(f["ns"]) - 1)
    hit = f["ns"][pos] == d["ns"][bars]
    X = np.where(hit[:, None], f["X"][pos].astype(np.float32), 0.0)
    br = np.where(hit, f["breadth"][pos], 0.0)
    extra = np.stack([d[f"strength{N}"][bars] * 100, (d["size"][bars] >= 1.0) * 2.0 - 1, br * 2 - 1], axis=1)
    return np.concatenate([X, extra.astype(np.float32)], axis=1)


def scale_for_year(lab, N: int, clip: tuple, base: dict) -> dict:
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
    xs, ys = [], []
    for M in range(2020, N):
        r = lab.book(M, base)
        by: dict = {}
        for sym, bar, ret in r["trade_log"]:
            by.setdefault(sym, []).append((bar, ret))
        for sym, lst in by.items():
            bars = np.array([b for b, _ in lst], dtype=np.int64)
            xs.append(_rows(lab, sym, bars, M))
            ys.append(np.array([ret > 0 for _, ret in lst]))
    if sum(len(v) for v in ys) < 100:          # 2020 has no past book here: no sizer
        return {s: np.ones(len(d["ns"])) for s, d in lab.per.items()}
    X, y = np.concatenate(xs), np.concatenate(ys)
    sc = StandardScaler().fit(X)
    net = MLPClassifier(hidden_layer_sizes=(16,), alpha=1e-2, max_iter=300, early_stopping=True,
                        random_state=7).fit(sc.transform(X), y)
    pbar = float(net.predict_proba(sc.transform(X))[:, 1].mean())
    lo, hi = float(clip[0]), float(clip[1])
    out = {}
    for s, d in lab.per.items():
        m = np.ones(len(d["ns"]))
        bars = np.flatnonzero((d["year"] == N) & d[f"enter{N}"])
        if len(bars):
            p = net.predict_proba(sc.transform(_rows(lab, s, bars, N)))[:, 1]
            m[bars] = np.clip(p / pbar, lo, hi)
        out[s] = m
    return out
