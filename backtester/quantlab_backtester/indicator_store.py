"""Backfilled indicator panels on disk, so nothing is computed twice.

The operator's ask: compute the indicators once, from day one, store them beside
the candles, and let every backtest read rather than derive. This is that store.

One gzipped CSV per (symbol, spec) — the spec is hashed into the filename, so
changing the catalogue produces a new file rather than silently serving values
computed under different parameters. That is the failure this design exists to
prevent: a stale cache is indistinguishable from a correct one until a result is
already published.

Cheap correctness checks live in the header: the bar count and the first and
last timestamps the panel was built from. A cache whose header disagrees with
the candles it is asked about is discarded and rebuilt rather than trusted.

Format is gzipped CSV rather than a binary layout because this data outlives the
code that writes it. A file someone can gunzip and read in a spreadsheet is
worth more than the bytes a packed format would save, and the compression does
most of that work anyway.
"""

from __future__ import annotations

from array import array
from pathlib import Path
from typing import Iterable
import csv
import gzip
import hashlib
import math

from .indicators import IndicatorPanel, IndicatorSpec, panel_for, panel_from_columns
from .models import Bar

NAN = float("nan")


def candle_digest(bars: list[Bar]) -> str:
    """A fingerprint of the candles a panel was built from.

    Bar count and endpoints are not enough, and a test proved it: a series with
    the same dates and a different price history was accepted from cache, which
    would have served indicators computed on somebody else's prices. Hashing the
    OHLCV stream costs one pass against the seventy-nine columns it protects.
    """
    digest = hashlib.sha256()
    for bar in bars:
        digest.update(
            f"{bar.timestamp.isoformat()}|{bar.open!r}|{bar.high!r}|"
            f"{bar.low!r}|{bar.close!r}|{bar.volume!r}\n".encode()
        )
    return digest.hexdigest()[:24]


class IndicatorStore:
    """Reads and writes cached panels under a root directory."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def path_for(self, symbol: str, spec: IndicatorSpec, timeframe: str = "1d") -> Path:
        safe = "".join(c for c in symbol if c.isalnum() or c in "._-") or "unknown"
        return self.root / safe / timeframe / f"indicators-{spec.cache_key()}.csv.gz"

    # -- writing -------------------------------------------------------------- #

    def save(
        self,
        symbol: str,
        bars: list[Bar],
        panel: IndicatorPanel,
        spec: IndicatorSpec,
        timeframe: str = "1d",
    ) -> Path:
        path = self.path_for(symbol, spec, timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written to a neighbour and moved into place, so a run interrupted
        # halfway leaves no half-file that a later run would happily read.
        staging = path.with_suffix(".partial")
        with gzip.open(staging, "wt", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["#bars", len(bars)])
            writer.writerow(["#first", bars[0].timestamp.isoformat() if bars else ""])
            writer.writerow(["#last", bars[-1].timestamp.isoformat() if bars else ""])
            writer.writerow(["#warmup", panel.warmup_bars])
            writer.writerow(["#digest", candle_digest(bars)])
            writer.writerow(["timestamp", *panel.names])
            for index, bar in enumerate(bars):
                row = [bar.timestamp.isoformat()]
                for name in panel.names:
                    value = panel.columns[name][index]
                    row.append("" if math.isnan(value) else repr(value))
                writer.writerow(row)
        staging.replace(path)
        return path

    # -- reading -------------------------------------------------------------- #

    def load(
        self,
        symbol: str,
        bars: list[Bar],
        spec: IndicatorSpec,
        timeframe: str = "1d",
    ) -> IndicatorPanel | None:
        """The cached panel, or `None` if absent or not about these candles."""
        path = self.path_for(symbol, spec, timeframe)
        if not path.exists() or not bars:
            return None
        try:
            with gzip.open(path, "rt", newline="") as handle:
                reader = csv.reader(handle)
                header = {}
                for _ in range(5):
                    key, value = next(reader)
                    header[key] = value
                names = next(reader)[1:]

                if int(header["#bars"]) != len(bars):
                    return None
                if header["#first"] != bars[0].timestamp.isoformat():
                    return None
                if header["#last"] != bars[-1].timestamp.isoformat():
                    return None
                if header.get("#digest") != candle_digest(bars):
                    return None

                columns = {name: array("d") for name in names}
                count = 0
                for row in reader:
                    for name, cell in zip(names, row[1:]):
                        columns[name].append(NAN if cell == "" else float(cell))
                    count += 1
        except (OSError, ValueError, KeyError, StopIteration):
            # A corrupt cache must never be a hard failure: rebuilding costs
            # seconds, and refusing to run because a cache file was truncated
            # would make the store a liability rather than an optimisation.
            return None
        if count != len(bars):
            return None
        return panel_from_columns(
            names, columns, count, int(header["#warmup"]), spec.cache_key()
        )

    def panel(
        self,
        symbol: str,
        bars: list[Bar],
        spec: IndicatorSpec | None = None,
        timeframe: str = "1d",
        write: bool = True,
    ) -> IndicatorPanel:
        """Cached if usable, computed and cached otherwise."""
        spec = spec or IndicatorSpec()
        cached = self.load(symbol, bars, spec, timeframe)
        if cached is not None:
            return cached
        panel = panel_for(bars, spec)
        if write:
            try:
                self.save(symbol, bars, panel, spec, timeframe)
            except OSError:
                # A read-only or full disk should slow the laboratory down, not
                # stop it.
                pass
        return panel

    # -- backfill -------------------------------------------------------------- #

    def backfill(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        spec: IndicatorSpec | None = None,
        timeframe: str = "1d",
        progress: Iterable | None = None,
    ) -> dict[str, int]:
        """Compute and store every symbol. Returns a small report."""
        spec = spec or IndicatorSpec()
        written = skipped = failed = 0
        for index, (symbol, bars) in enumerate(sorted(bars_by_symbol.items()), 1):
            if len(bars) < 2:
                skipped += 1
                continue
            try:
                if self.load(symbol, bars, spec, timeframe) is not None:
                    skipped += 1
                else:
                    self.save(symbol, bars, panel_for(bars, spec), spec, timeframe)
                    written += 1
            except OSError:
                failed += 1
            if progress is not None:
                progress(index, symbol, written, skipped, failed)
        return {
            "written": written,
            "reused": skipped,
            "failed": failed,
            "symbols": len(bars_by_symbol),
            "columns": len(spec_columns(spec)),
            "spec": spec.cache_key(),
            "warmup_bars": spec.warmup_bars(),
        }


def spec_columns(spec: IndicatorSpec) -> tuple[str, ...]:
    from .indicators import column_names

    return column_names(spec)
