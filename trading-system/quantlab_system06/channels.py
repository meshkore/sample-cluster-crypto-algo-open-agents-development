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


def load_overlay(path: str | Path, key: str) -> dict[str, dict[int, float]]:
    """Read a sparse per-symbol overlay `.npz` (`{sym}__{key}_ns`, `{sym}__{key}`).

    Used for the meta verdict and microstructure channels — both are keyed by bar and
    attached onto the base signal table by `Channels.from_file`.
    """
    data = np.load(path)
    syms = {k[: -len(f"__{key}_ns")] for k in data.files if k.endswith(f"__{key}_ns")}
    out: dict[str, dict[int, float]] = {}
    for sym in syms:
        ns = data[f"{sym}__{key}_ns"].astype(np.int64)
        val = data[f"{sym}__{key}"].astype(np.float32)
        out[sym] = dict(zip(ns.tolist(), val.tolist()))
    return out


def load_meta(path: str | Path) -> dict[str, dict[int, float]]:
    """Read a meta verdict `.npz` into `{sym: {ns: expected_net}}`."""
    return load_overlay(path, "meta")


class Channels:
    """Fast, defaulted access to the precomputed per-(symbol, bar) signal channels."""

    def __init__(self, table: dict[str, dict[str, dict[int, float]]]):
        # {symbol: {"prob": {ns: p}, "trend": {ns: bit}, "vol": {ns: r}, "mom": {ns: m},
        #           "meta": {ns: expected_net}}}  — meta present only when attached.
        self._table = table

    @classmethod
    def from_file(cls, path: str | Path, meta_path: str | Path | None = None,
                  micro_path: str | Path | None = None) -> "Channels":
        """The production path: read the .npz `infer.export` wrote, plus optional overlays.

        `meta_path` attaches the meta verdict channel; `micro_path` attaches the
        microstructure contrarian-sentiment channel. Both are optional overlays, loaded
        only when the corresponding lever is active.
        """
        table = load_table(path)
        for overlay_path, key in ((meta_path, "meta"), (micro_path, "micro")):
            if overlay_path:
                for sym, series in load_overlay(overlay_path, key).items():
                    table.setdefault(sym, {"prob": {}, "trend": {}, "vol": {}, "mom": {}})[key] = series
        return cls(table)

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

    def meta(self, symbol: str, ns: int) -> float | None:
        """Meta expected-net verdict at a candidate bar. Missing -> None (module abstains)."""
        meta = self._table.get(symbol, {}).get("meta")
        if not meta:
            return None
        return meta.get(ns)  # None when this bar has no out-of-sample verdict

    def micro(self, symbol: str, ns: int) -> float | None:
        """Microstructure contrarian sentiment in [-1,1]. Missing -> None (module abstains).

        Positive = longs have capitulated / crowd is short (contrarian bullish);
        negative = crowded, over-levered longs (contrarian bearish, avoid entering).
        """
        micro = self._table.get(symbol, {}).get("micro")
        if not micro:
            return None
        return micro.get(ns)

    def has(self, channel: str, symbol: str) -> bool:
        """Whether `symbol` carries a non-empty `channel` map (feature detection)."""
        return bool(self._table.get(symbol, {}).get(channel))

    @property
    def symbols(self) -> list[str]:
        return list(self._table)
