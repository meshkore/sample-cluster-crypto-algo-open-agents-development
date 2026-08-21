"""One place that owns the precomputed signal channels.

`infer.py` writes causal per-bar arrays into `signals.npz` — `prob`, `trend`,
`vol`, `mom`, and (later) meta verdicts and microstructure. Before this file,
every reader re-implemented the same `table.get(symbol, {}).get(channel, {})...`
lookup with its own defaults scattered through `strategy.py`. That is exactly the
"second implementation of the same arithmetic" `quantlab_ml/meta.py` warns about:
the day two copies drift, a module is fed garbage while every metric reads normal.

`Channels` is that single implementation. It holds the table (dict-of-dicts, O(1)
lookup, same structure `infer.load_table` produces) and exposes one method per
channel with the ONE canonical default:

  - `prob`  missing -> 0.0   (no conviction)
  - `trend` missing -> True  (risk-on; matches pre-gate signals, backward compatible)
  - `vol`   missing -> None   (neutral sizing; caller multiplies by 1.0)
  - `mom`   missing -> None   (excluded from the cross-sectional rank)

Construct from a file for the real run, or from an in-memory table for tests, so a
module can be exercised without writing an .npz.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def load_table(path: str | Path) -> dict[str, dict]:
    """Read a signals `.npz` into `{symbol: {"prob": {ns: p}, "trend": {ns: bit}, …}}`.

    Pure numpy — no torch — so the channel path stays light and importable without
    the model stack. `infer.py` re-exports this for backward compatibility.

    Older files without a `__trend`/`__vol`/`__mom` array load with an empty map for
    it, which `Channels` reads as the neutral default (risk-on / flat sizing / no
    rank) — backward compatible with pre-gate signals.
    """
    data = np.load(path)
    keys = {k.rsplit("__", 1)[0] for k in data.files}
    table: dict[str, dict] = {}
    for symbol in keys:
        ns = data[f"{symbol}__epoch_ns"]
        prob = data[f"{symbol}__prob"].astype(np.float32)
        entry: dict[str, dict] = {"prob": dict(zip(ns.tolist(), prob.tolist()))}
        for channel in ("trend", "vol", "mom"):
            field = f"{symbol}__{channel}"
            if field in data.files:
                cast = np.int8 if channel == "trend" else np.float32
                values = data[field].astype(cast)
                entry[channel] = dict(zip(ns.tolist(), values.tolist()))
            else:
                entry[channel] = {}
        table[symbol] = entry
    return table


class Channels:
    """Fast, defaulted access to the precomputed per-(symbol, bar) signal channels."""

    def __init__(self, table: dict[str, dict[str, dict[int, float]]]):
        # {symbol: {"prob": {ns: p}, "trend": {ns: bit}, "vol": {ns: r}, "mom": {ns: m}}}
        self._table = table

    @classmethod
    def from_file(cls, path: str | Path) -> "Channels":
        """The production path: read the .npz `infer.export` wrote."""
        return cls(load_table(path))

    # -- channel accessors: one canonical default each -------------------------

    def prob(self, symbol: str, ns: int) -> float:
        """Model conviction (bagged sigmoid). Missing -> 0.0 (no conviction)."""
        return self._table.get(symbol, {}).get("prob", {}).get(ns, 0.0)

    def uptrend(self, symbol: str, ns: int) -> bool:
        """Causal slow-trend bit. Missing map -> True (risk-on), as pre-gate files behaved."""
        trend = self._table.get(symbol, {}).get("trend")
        if not trend:
            return True
        return bool(trend.get(ns, 0))

    def volratio(self, symbol: str, ns: int) -> float | None:
        """Recent/typical realized-vol ratio. Missing -> None (size flat)."""
        vol = self._table.get(symbol, {}).get("vol")
        ratio = vol.get(ns) if vol else None
        return float(ratio) if ratio and ratio > 0 else None

    def momentum(self, symbol: str, ns: int) -> float | None:
        """Trailing return for cross-sectional ranking. Missing -> None (excluded)."""
        mom = self._table.get(symbol, {}).get("mom")
        if not mom:
            return None
        return float(mom.get(ns, 0.0))

    def has(self, channel: str, symbol: str) -> bool:
        """Whether `symbol` carries a non-empty `channel` map (feature detection)."""
        return bool(self._table.get(symbol, {}).get(channel))

    @property
    def symbols(self) -> list[str]:
        return list(self._table)
