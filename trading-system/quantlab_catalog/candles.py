"""Price candles, era-split at the 2026 lock, for any system.

This is a thin wrapper and stays thin on purpose. The loaders, the cache layout and the
research/forward split all belong to `quantlab_backtester.data.FocusedDataset`, which is
the frozen instrument every system in this laboratory already shares. What the wrapper
adds is the thing that keeps being re-implemented per system and re-broken per system:
the lock is enforced HERE, so `research()` is incapable of returning a 2026 bar and
reading the sealed window is an explicit call that shows up in a diff.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from quantlab_backtester.data import FocusedDataset
from quantlab_backtester.models import Bar

from .paths import DATA_ROOT, LOCK

# What has actually been downloaded. Not what the exchange offers - what is on this
# disk. `inventory` is the live answer; this is the declared expectation, and the two
# disagreeing is itself worth knowing.
INTERVALS = ("15m",)


def _dataset(interval: str, data_root: Path | str | None) -> FocusedDataset:
    if interval not in INTERVALS:
        raise ValueError(
            f"interval {interval!r} is not in the catalogue (have {INTERVALS}). "
            f"Nothing here downloads; fetch it deliberately first.")
    return FocusedDataset(str(data_root or DATA_ROOT), LOCK)


def research(symbols, interval: str = "15m",
             data_root: Path | str | None = None) -> dict[str, list[Bar]]:
    """Every bar strictly before the lock. Cannot return a 2026 bar, by construction.

    The filter is belt AND braces: `research_bars` already stops at the lock, and this
    re-checks it. The cost is one pass over a list that is already in memory; the thing
    it buys is that a change in the loader can never quietly widen what "research"
    means, which is the single mistake this laboratory cannot afford to make twice.
    """
    bars = _dataset(interval, data_root).research_bars(list(symbols), interval)
    lock = datetime.fromisoformat(LOCK)
    return {s: [b for b in series if b.timestamp < lock] for s, series in bars.items()}


def forward(symbols, interval: str = "15m", end: datetime | None = None,
            data_root: Path | str | None = None) -> dict[str, list[Bar]]:
    """The sealed window ALONE. Reading this is a deliberate act; make it visible."""
    bars = _dataset(interval, data_root).combined_bars(
        list(symbols), interval, end or datetime.now(timezone.utc))
    lock = datetime.fromisoformat(LOCK)
    return {s: [b for b in series if b.timestamp >= lock] for s, series in bars.items()}


def candles(symbols, interval: str = "15m", *, include_sealed: bool = False,
            end: datetime | None = None,
            data_root: Path | str | None = None) -> dict[str, list[Bar]]:
    """History, optionally spliced with the sealed window on the far end.

    A forward run needs the history in front of 2026 so every indicator is already warm
    when the first sealed bar arrives - that is what `include_sealed=True` is for, and
    it is keyword-only so it can never be passed by accident.
    """
    if not include_sealed:
        return research(symbols, interval, data_root)
    return _dataset(interval, data_root).combined_bars(
        list(symbols), interval, end or datetime.now(timezone.utc))
