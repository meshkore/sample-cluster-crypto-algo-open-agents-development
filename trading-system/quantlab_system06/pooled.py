"""One dataset from many symbols, for training a single symbol-agnostic model.

The whole reason a multi-crypto model is worth building is that the features are
**stationary** — a return, an oscillator, a candle shape mean the same thing on
BTC and on a small alt — so one net trained on all of them learns the *mechanism*
of a swing rather than one coin's price history. This module pools the symbols
into one training table for exactly that.

Two invariants make the pooling honest:

- **A window never crosses a symbol boundary.** Each symbol's rows are a
  contiguous block, and a window ending at bar `i` reads `[i-K+1, i]`, all inside
  that block, so BTC's last bar and ETH's first are never spliced into one input.
- **The train/validation split is chronological within each symbol.** Val is the
  last slice of each symbol's own timeline, with an embargo, so no window in
  training overlaps one in validation. Pooling by row index instead would let a
  2019 BTC bar validate against a 2024 BTC bar, which measures nothing.

The standardiser is fitted on the pooled TRAINING rows only — the same no-leak
rule as the single-symbol path, now across the whole universe at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .dataset import Dataset
from .features import Standardizer, build_matrix, finite_rows, research_store
from .oracle import holding_labels


@dataclass
class Pooled:
    symbols: list[str]
    window: int
    Xz: np.ndarray                       # [total, F] standardised, float32
    labels: np.ndarray                   # [total] int8
    train_ends: np.ndarray               # global end indices, training
    val_ends: np.ndarray                 # global end indices, validation
    scaler: Standardizer
    close: dict[str, np.ndarray] = field(default_factory=dict)
    val_ends_by_symbol: dict[str, np.ndarray] = field(default_factory=dict)
    bounds: dict[str, tuple[int, int]] = field(default_factory=dict)

    @property
    def n_features(self) -> int:
        return self.Xz.shape[1]


def _local_ends(matrix: np.ndarray, window: int) -> np.ndarray:
    finite = finite_rows(matrix)
    if len(finite) == 0:
        return np.array([], dtype=np.int64)
    return np.arange(int(finite[0]) + window - 1, len(matrix), dtype=np.int64)


def build_pooled(
    symbols: list[str],
    data_root: str = "backtester/data",
    interval: str = "15m",
    threshold: float = 0.01,
    window: int = 64,
    val_fraction: float = 0.2,
    embargo: int = 0,
) -> Pooled:
    """Pool the universe's research history into one train/val table.

    `embargo` (bars, idea purged-cv from Lopez de Prado) purges leakage at the
    train/val boundary: the last `embargo` train ends before the split are DROPPED,
    and validation starts `embargo` bars later still. Because the zigzag oracle labels
    are computed over the whole series, train bars adjacent to the split can 'know'
    post-split prices via pivots; the embargo removes those leaky samples so the
    validation number the loop selects on is honest. embargo=0 = the prior behaviour.
    """
    dataset = Dataset(data_root, symbols=symbols, interval=interval)
    research = dataset.research()
    store = research_store(data_root)  # cached panels; computed once, read after

    raw_blocks: list[np.ndarray] = []
    label_blocks: list[np.ndarray] = []
    close: dict[str, np.ndarray] = {}
    bounds: dict[str, tuple[int, int]] = {}
    train_ends: list[np.ndarray] = []
    val_ends: list[np.ndarray] = []
    val_ends_by_symbol: dict[str, np.ndarray] = {}
    train_bar_rows: list[np.ndarray] = []
    offset = 0
    kept: list[str] = []

    for symbol in symbols:
        bars = research.get(symbol) or []
        if len(bars) < window * 4:
            continue  # too little history to form a train and a val slice
        matrix, _ = build_matrix(bars, store=store, symbol=symbol)
        labels = holding_labels(np.array([b.close for b in bars], dtype=float), threshold)
        ends = _local_ends(matrix, window)
        if len(ends) < 500:
            continue
        split = int(len(ends) * (1 - val_fraction))
        # Purge: drop the last `embargo` train ends before the split (leaky boundary).
        # Embargo: start val `embargo` bars further after the window gap.
        tr = ends[:max(0, split - embargo)]
        va = ends[split + window + embargo:]
        if len(tr) == 0 or len(va) == 0:
            continue

        raw_blocks.append(matrix.astype(np.float32))
        label_blocks.append(labels.astype(np.int8))
        close[symbol] = np.array([b.close for b in bars], dtype=float)
        bounds[symbol] = (offset, offset + len(matrix))
        train_ends.append(tr + offset)
        val_ends.append(va + offset)
        val_ends_by_symbol[symbol] = va + offset
        # Bars any training window touches, for the standardiser fit.
        train_bar_rows.append(np.arange(int(tr[0]) - window + 1, int(tr[-1]) + 1) + offset)
        offset += len(matrix)
        kept.append(symbol)

    if not kept:
        raise RuntimeError("no symbol had enough history; download more or widen the universe")

    raw = np.concatenate(raw_blocks, axis=0)
    labels_all = np.concatenate(label_blocks, axis=0)
    scaler = Standardizer.fit(raw, np.concatenate(train_bar_rows))
    Xz = scaler.transform(raw).astype(np.float32)

    return Pooled(
        symbols=kept,
        window=window,
        Xz=Xz,
        labels=labels_all,
        train_ends=np.concatenate(train_ends),
        val_ends=np.concatenate(val_ends),
        scaler=scaler,
        close=close,
        val_ends_by_symbol=val_ends_by_symbol,
        bounds=bounds,
    )
