"""One table: every bar of every symbol, its features, and how its trade ended.

This is where the three previous files meet, and where the two mistakes that
survive them both would be made.

**The timeline has to be shared before ranks mean anything.** Symbols start on
different dates -- SOL has no 2018 and AVAX has no 2019 -- so their arrays are
not aligned by position. Ranking position 4,000 of one against position 4,000 of
another compares two different moments and produces a feature that looks
informative and describes nothing. Everything here is indexed by TIMESTAMP.

**The lock is enforced by where the bars come from, not by a filter here.**
Research rows load through `IntradayDataset.research()`, which loads through
`DataManager`, which refuses post-lock data outright. There is deliberately no
`if timestamp < lock` in this file: a guard that can be edited out is weaker than
a path that cannot reach the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from quantlab_backtester.indicators import IndicatorSpec, panel_for

from . import features as F
from .labels import Barriers, net_of_costs, realised_volatility, triple_barrier

ROUND_TRIP = 0.003


@dataclass
class Observations:
    """The model's view of the world, and enough to check it was built honestly."""

    X: np.ndarray
    y: np.ndarray
    ret: np.ndarray
    ends_at: np.ndarray
    names: list[str]
    symbols: np.ndarray
    timestamps: np.ndarray
    meta: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.y)

    def document(self) -> dict[str, Any]:
        finite = np.isfinite(self.ret)
        return {
            "rows": len(self.y),
            "features": len(self.names),
            "symbols": sorted(set(self.symbols.tolist())),
            "span": [str(self.timestamps.min()), str(self.timestamps.max())],
            "label_balance": {
                "target_first": int((self.y == 1).sum()),
                "stop_first": int((self.y == -1).sum()),
                "timed_out": int((self.y == 0).sum()),
            },
            "mean_net_return": float(np.nanmean(self.ret[finite]))
            if finite.any()
            else None,
            **self.meta,
        }


def build(
    bars_by_symbol: dict[str, list],
    barriers: Barriers = Barriers(),
    volatility_span: int = 288,
    spec: IndicatorSpec | None = None,
    store: Any = None,
) -> Observations:
    """Features and triple-barrier labels for every symbol, on a shared clock.

    Rows are dropped when the label never resolved (the series ran out) or when
    the volatility estimate has not warmed up. Both are dropped rather than
    filled: an unresolved window imputed as flat teaches the model that the end
    of the file is a calm market, and a warm-up row filled with a default teaches
    it that every asset begins life at the same volatility.
    """
    spec = spec or IndicatorSpec()
    per_symbol: dict[str, dict[str, Any]] = {}

    for symbol, bars in sorted(bars_by_symbol.items()):
        if len(bars) < volatility_span + barriers.horizon + 10:
            continue
        close = np.array([b.close for b in bars], dtype=float)
        high = np.array([b.high for b in bars], dtype=float)
        low = np.array([b.low for b in bars], dtype=float)
        stamps = np.array([b.timestamp for b in bars], dtype=object)

        panel = (
            store.panel(symbol, bars, spec)
            if store is not None
            else panel_for(bars, spec)
        )
        columns = {
            name: np.asarray(panel.columns[name], dtype=float) for name in panel.names
        }

        volatility = realised_volatility(close, span=volatility_span)
        block = F.scale_free(columns, close, volatility, window=volatility_span)
        block.update(F.calendar(stamps))
        block.update(F.session_shape(close, stamps, volatility))
        outcome = triple_barrier(high, low, close, volatility, barriers)

        per_symbol[symbol] = {
            "features": block,
            "stamps": stamps,
            "close": close,
            "volatility": volatility,
            "outcome": outcome,
        }

    if not per_symbol:
        raise ValueError("no symbol has enough bars to build an observation table")

    # THE CROSS-SECTION, on the shared clock. Built by timestamp rather than by
    # position: symbols listed at different dates are not aligned by index, and
    # ranking position 4,000 of one against position 4,000 of another silently
    # compares two different days.
    ranked = _cross_sectional(per_symbol)

    names: list[str] | None = None
    X_parts, y_parts, ret_parts, end_parts, sym_parts, ts_parts = [], [], [], [], [], []
    offset = 0
    for symbol, data in per_symbol.items():
        block = dict(data["features"])
        block.update(ranked.get(symbol, {}))
        if names is None:
            names = sorted(block)
        matrix = np.column_stack([block[name] for name in names])

        outcome = data["outcome"]
        keep = (
            outcome["touched"]
            & np.isfinite(data["volatility"])
            & np.isfinite(matrix).all(axis=1)
        )
        if not keep.any():
            continue
        rows = np.flatnonzero(keep)
        X_parts.append(matrix[rows])
        y_parts.append(outcome["label"][rows])
        ret_parts.append(net_of_costs(outcome["ret"][rows], ROUND_TRIP))
        # `ends_at` is an index into THIS symbol's bars. The purge works over the
        # concatenated table, so it is rebased onto the row that bar became --
        # searchsorted rather than arithmetic, because rows were dropped and the
        # mapping is not a constant shift.
        ends = np.searchsorted(rows, outcome["ends_at"][rows]) + offset
        end_parts.append(np.minimum(ends, offset + len(rows) - 1))
        sym_parts.append(np.full(len(rows), symbol, dtype=object))
        ts_parts.append(data["stamps"][rows])
        offset += len(rows)

    return Observations(
        X=np.vstack(X_parts),
        y=np.concatenate(y_parts),
        ret=np.concatenate(ret_parts),
        ends_at=np.concatenate(end_parts),
        names=list(names or []),
        symbols=np.concatenate(sym_parts),
        timestamps=np.concatenate(ts_parts),
        meta={
            "barriers": {
                "target": barriers.target,
                "stop": barriers.stop,
                "horizon": barriers.horizon,
            },
            "round_trip": ROUND_TRIP,
            "volatility_span": volatility_span,
        },
    )


def _cross_sectional(
    per_symbol: dict[str, dict[str, Any]],
) -> dict[str, dict[str, np.ndarray]]:
    """Per-bar ranks across the universe, aligned on timestamps.

    Three quantities carry most of what the cross-section knows: how far today
    has moved, how violent the asset is, and how stretched it is inside its own
    day. Each becomes a percentile against whatever else was trading on that bar.
    """
    wanted = ("day_return_sigma", "day_range_sigma", "position_in_day_range")
    clock = sorted(
        {stamp for d in per_symbol.values() for stamp in d["stamps"].tolist()}
    )
    position = {stamp: i for i, stamp in enumerate(clock)}

    out: dict[str, dict[str, np.ndarray]] = {symbol: {} for symbol in per_symbol}
    for key in wanted:
        aligned: dict[str, np.ndarray] = {}
        for symbol, data in per_symbol.items():
            row = np.full(len(clock), np.nan)
            values = data["features"].get(key)
            if values is None:
                continue
            row[[position[s] for s in data["stamps"].tolist()]] = values
            aligned[symbol] = row
        if len(aligned) < 2:
            continue
        ranks = F.cross_sectional_rank(aligned)
        for symbol, data in per_symbol.items():
            if symbol not in ranks:
                continue
            out[symbol][f"rank_{key}"] = ranks[symbol][
                [position[s] for s in data["stamps"].tolist()]
            ]
    return out
