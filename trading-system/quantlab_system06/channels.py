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
        for channel in ("trend", "vol", "mom", "hurst", "feargreed", "sweep"):
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
                  micro_path: str | Path | None = None,
                  tree_path: str | Path | None = None,
                  size_path: str | Path | None = None) -> "Channels":
        """The production path: read the .npz `infer.export` wrote, plus optional overlays.

        `meta_path` attaches the meta verdict channel; `micro_path` attaches the
        microstructure contrarian-sentiment channel; `size_path` attaches the learned
        money-management multipliers. All are optional overlays, loaded only when the
        corresponding lever is active.
        """
        table = load_table(path)
        for overlay_path, key in ((meta_path, "meta"), (micro_path, "micro"),
                                  (tree_path, "tree"), (size_path, "size")):
            if overlay_path:
                for sym, series in load_overlay(overlay_path, key).items():
                    table.setdefault(sym, {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "hurst": {}, "feargreed": {}, "sweep": {}, "tree": {}})[key] = series
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

    def hurst(self, symbol: str, ns: int) -> float | None:
        """Generalized Hurst exponent (fractal regime). Missing -> None (module abstains).

        >0.5 persistent/trending, ~0.5 random walk, <0.5 anti-persistent/choppy. The
        warm-up region is written as the neutral 0.5, so an early bar reads as 'unknown'
        rather than a fabricated regime call."""
        hurst = self._table.get(symbol, {}).get("hurst")
        if not hurst:
            return None
        return hurst.get(ns)

    def feargreed(self, symbol: str, ns: int) -> float | None:
        """Behavioural fear/greed index in [0,1]. Missing -> None (module abstains).

        0.5 neutral, >0.5 greedy (extended above trend, calm), <0.5 fearful (below trend,
        turbulent). The warm-up region reads near 0.5, so early bars carry no strong call."""
        fg = self._table.get(symbol, {}).get("feargreed")
        if not fg:
            return None
        return fg.get(ns)

    def sweep(self, symbol: str, ns: int) -> float | None:
        """Market-maker two-sided stop-sweep score in [0,1). Missing -> None (abstain).

        High only when long upper AND lower wicks, a volume spike and an unusually wide
        range coincide — a liquidity cleanup that price often reverses out of."""
        sweep = self._table.get(symbol, {}).get("sweep")
        if not sweep:
            return None
        return sweep.get(ns)

    def tree(self, symbol: str, ns: int) -> float | None:
        """Decision-tree P(up) for this bar. Missing -> None (the voter abstains).

        Walk-forward and purged: the first training block carries no verdict, and the
        sealed window is scored by a model fitted only on research bars."""
        tree = self._table.get(symbol, {}).get("tree")
        if not tree:
            return None
        return tree.get(ns)

    def size(self, symbol: str, ns: int) -> float | None:
        """Learned money-management size multiplier for entering this bar.

        Walk-forward and embargoed: research years are scored by models fitted only
        on trades completed strictly before them, and the sealed window by a model
        fitted on research trades alone. Missing -> None (the sizing module abstains,
        so early years without enough history size exactly as before)."""
        size = self._table.get(symbol, {}).get("size")
        if not size:
            return None
        return size.get(ns)

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
