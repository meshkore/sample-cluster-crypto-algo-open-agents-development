"""One table: every bar of every symbol, its features, and how its trade ended.

This is where the three previous files meet, and where the two mistakes that
survive them both would be made.

**The timeline has to be shared before ranks mean anything.** Symbols start on
different dates -- SOL has no 2018 and AVAX has no 2019 -- so their arrays are
not aligned by position. Ranking position 4,000 of one against position 4,000 of
another compares two different moments and produces a feature that looks
informative and describes nothing. Everything here is indexed by TIMESTAMP.

**The table is returned sorted by TIMESTAMP, and that is load-bearing.** It is
assembled symbol by symbol, so before the final sort it ran BNB 2017-2025, then
BTC 2017-2025, then ETH: time jumped backwards at every symbol boundary.
`splits.purged_walk_forward` slices by POSITION, so on that table a "fold" was a
slice of the symbol list -- the model trained on BNB through 2025 and was tested
on BTC from 2017, while the purge compared row indices that had never been on one
clock. It reported six of six folds positive at +0.49% net per trade. Anything
measured off this table before the sort existed is void.

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

    # SORTED BY TIME, and this line is the difference between a walk-forward and
    # a fiction. The parts above are concatenated symbol by symbol, so the raw
    # table runs BNB 2017-2025, then BTC 2017-2025, then ETH -- time jumps
    # backwards at every symbol boundary. `purged_walk_forward` slices that table
    # by POSITION, so a "fold" was a slice of the symbol list rather than of
    # history: the model trained on BNB through 2025 and was tested on BTC from
    # 2017, and the purge compared row indices that were never on one clock. It
    # is how a run reported six of six folds positive at +0.49% net per trade.
    # Every figure that split this table before this sort should be treated as
    # void. Ties keep the symbol-major order, which is arbitrary and harmless.
    stamps = np.concatenate(ts_parts)
    ends = np.concatenate(end_parts)
    order = np.argsort(
        np.array([s.timestamp() for s in stamps], dtype=float), kind="stable"
    )
    inverse = np.empty(len(order), dtype=np.int64)
    inverse[order] = np.arange(len(order), dtype=np.int64)

    return Observations(
        X=np.vstack(X_parts)[order],
        y=np.concatenate(y_parts)[order],
        ret=np.concatenate(ret_parts)[order],
        # Rebased twice: `ends[order]` puts each row's resolution index in the new
        # row order, `inverse[...]` maps that index from the old table to the new.
        ends_at=inverse[ends[order]],
        names=list(names or []),
        symbols=np.concatenate(sym_parts)[order],
        timestamps=stamps[order],
        meta={
            "barriers": {
                "target": barriers.target,
                "stop": barriers.stop,
                "horizon": barriers.horizon,
            },
            "round_trip": ROUND_TRIP,
            "volatility_span": volatility_span,
            "sorted_by": "timestamp",
        },
    )


def barrier_sigma(
    observations: Observations,
    bars_by_symbol: dict[str, list],
    horizon: int,
    span: int = 288,
) -> np.ndarray:
    """Barrier-scale volatility for every observation, in the table's row order.

    `expected_net` needs this to turn a probability into a payoff, and it has two
    ways to be silently wrong. The scaling by `sqrt(horizon)` must match
    `triple_barrier` exactly -- at five minutes over 864 bars the mismatch is a
    factor of 29, and the filter then refuses every trade while every other
    metric reads normally. And the ALIGNMENT must be per row: the caller used to
    build this by concatenating one array per symbol, which was correct only
    while the observation table was symbol-major, and became a silent
    misalignment the moment the table was sorted by time.
    """
    out = np.full(len(observations.timestamps), np.nan)
    scale = float(np.sqrt(max(horizon, 1)))
    for symbol in sorted(set(observations.symbols.tolist())):
        bars = bars_by_symbol.get(symbol) or []
        if not bars:
            continue
        close = np.array([b.close for b in bars], dtype=float)
        volatility = realised_volatility(close, span=span)
        bar_stamps = np.array([b.timestamp for b in bars], dtype=object)
        rows = np.flatnonzero(observations.symbols == symbol)
        wanted = observations.timestamps[rows]
        position = np.searchsorted(bar_stamps, wanted)
        position = np.clip(position, 0, len(bar_stamps) - 1)
        # An inexact hit means the row's bar is not in this symbol's tape, which
        # would be a construction bug rather than a missing value. Leave it NaN
        # so it is dropped loudly instead of priced against the wrong bar.
        exact = bar_stamps[position] == wanted
        out[rows[exact]] = volatility[position[exact]]
    return scale * out


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
