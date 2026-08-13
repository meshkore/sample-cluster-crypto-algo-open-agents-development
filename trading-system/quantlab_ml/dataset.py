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

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from quantlab_backtester.indicators import IndicatorSpec, panel_for

from . import features as F
from .labels import Barriers, net_of_costs, realised_volatility, triple_barrier

ROUND_TRIP = 0.003

# Bumped whenever a change to this file alters the table it produces. It is part
# of the cache key, so an old cache is a miss rather than a wrong answer -- the
# time-sort fix landed the day before this cache existed, and serving a
# pre-sort table from disk would have quietly restored the bug it cured.
CACHE_VERSION = 2


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


def fingerprint(
    bars_by_symbol: dict[str, list],
    barriers: Barriers,
    volatility_span: int,
    spec: IndicatorSpec,
) -> str:
    """A digest of everything that changes the table, for the cache key.

    The CLOSES are hashed, not just the symbol list and the span. A cache keyed on
    metadata alone would serve a stale table after the tape was refetched or
    repaired, and a silently stale observation table is the worst failure in this
    package: every downstream number would be computed correctly from the wrong
    data. Hashing 30 MB of float64 costs about a tenth of a second against the
    minutes the cache saves.
    """
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(
        json.dumps(
            {
                "target": barriers.target,
                "stop": barriers.stop,
                "horizon": barriers.horizon,
                "volatility_span": volatility_span,
                "indicators": sorted(getattr(spec, "names", ()) or ()),
                "round_trip": ROUND_TRIP,
                "version": CACHE_VERSION,
            },
            sort_keys=True,
        ).encode()
    )
    for symbol, bars in sorted(bars_by_symbol.items()):
        digest.update(symbol.encode())
        digest.update(str(len(bars)).encode())
        if not bars:
            continue
        digest.update(str(bars[0].timestamp).encode())
        digest.update(str(bars[-1].timestamp).encode())
        digest.update(np.array([b.close for b in bars], dtype=float).tobytes())
    return digest.hexdigest()[:16]


def _load_cached(path: Path) -> Observations | None:
    """A cached table, or None when it is missing or unreadable.

    A corrupt or half-written cache file must never be an error the caller has to
    handle: the whole point of a cache is that deleting it changes nothing but the
    time taken, so anything unexpected falls through to a rebuild.
    """
    try:
        with np.load(path, allow_pickle=False) as blob:
            stamps = [
                datetime.fromtimestamp(int(second), tz=timezone.utc)
                for second in blob["timestamps"]
            ]
            return Observations(
                X=blob["X"],
                y=blob["y"],
                ret=blob["ret"],
                ends_at=blob["ends_at"],
                names=json.loads(str(blob["names"])),
                symbols=np.array([str(s) for s in blob["symbols"]], dtype=object),
                timestamps=np.array(stamps, dtype=object),
                meta=json.loads(str(blob["meta"])),
            )
    except (OSError, KeyError, ValueError, EOFError):
        return None


def _store_cached(path: Path, observations: Observations) -> None:
    """Write the table, atomically, and never fail the caller if it cannot.

    Timestamps are stored as INTEGER SECONDS rather than floats. These bars sit
    on a five-minute grid so seconds are exact, and a float round trip would
    reconstruct a timestamp a microsecond off -- which `barrier_sigma` matches
    with `==` against the bar's own timestamp, so every row would silently fail
    to find its volatility.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        scratch = path.with_suffix(".partial")
        np.savez(
            scratch,
            X=observations.X,
            y=observations.y,
            ret=observations.ret,
            ends_at=observations.ends_at,
            names=json.dumps(list(observations.names)),
            symbols=np.array([str(s) for s in observations.symbols]),
            timestamps=np.array(
                [int(stamp.timestamp()) for stamp in observations.timestamps],
                dtype=np.int64,
            ),
            meta=json.dumps(observations.meta, default=str),
        )
        scratch.with_suffix(".partial.npz").replace(path)
    except (OSError, ValueError):
        return


def build(
    bars_by_symbol: dict[str, list],
    barriers: Barriers = Barriers(),
    volatility_span: int = 288,
    spec: IndicatorSpec | None = None,
    store: Any = None,
    cache: str | Path | None = None,
) -> Observations:
    """Features and triple-barrier labels for every symbol, on a shared clock.

    Rows are dropped when the label never resolved (the series ran out) or when
    the volatility estimate has not warmed up. Both are dropped rather than
    filled: an unresolved window imputed as flat teaches the model that the end
    of the file is a calm market, and a warm-up row filled with a default teaches
    it that every asset begins life at the same volatility.

    `cache` is a directory. Building this table over eight years of five-minute
    bars is minutes of arithmetic that does not change between experiments -- it
    was built three times in one afternoon while a single filter was being
    measured -- so the result is keyed by a digest of the closes and the barrier
    configuration and written there. The cache is never load-bearing: a missing,
    corrupt or stale file changes how long the call takes and nothing else.
    """
    spec = spec or IndicatorSpec()
    cache_path: Path | None = None
    if cache is not None:
        key = fingerprint(bars_by_symbol, barriers, volatility_span, spec)
        cache_path = Path(cache) / f"observations-{key}.npz"
        cached = _load_cached(cache_path) if cache_path.exists() else None
        if cached is not None:
            return cached
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

    observations = Observations(
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
    if cache_path is not None:
        _store_cached(cache_path, observations)
    return observations


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
