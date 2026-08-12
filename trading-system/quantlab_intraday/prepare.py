"""Get the data and the indicators ready, once, so iterating costs nothing.

    python3 -m quantlab_intraday.prepare

Downloads 5-minute candles for the universe (research and the sealed 2026
window, through the backtester's own loaders so the lock is enforced by the
same code as everywhere else), then computes and stores the indicator panel for
every window a run will ask for: the twelve training blocks and the forward
window.

After this, launching a hypothesis reads panels from disk instead of computing
seventy-nine columns per symbol per window. That is the difference between an
iteration you run while you think and one you run while you wait.

Re-running is cheap and safe. Candles already cached are not downloaded again,
and a panel is rebuilt only when the candles it was built from changed -- the
cache key is a digest of the OHLCV stream, so a stale panel is discarded rather
than served.
"""

from __future__ import annotations

import argparse
import time
from typing import Any

from .dataset import (
    DEFAULT_BLOCKS,
    DEFAULT_SYMBOLS,
    INTERVAL,
    LOCK,
    IntradayDataset,
)


def prepare(
    data_root: str = "backtester/data",
    interval: str = INTERVAL,
    symbols: list[str] | None = None,
    blocks: int = DEFAULT_BLOCKS,
    forward: bool = True,
) -> dict[str, Any]:
    """Download, then warm every panel. Returns what it did, in counts."""
    dataset = IntradayDataset(data_root, LOCK, symbols or DEFAULT_SYMBOLS, interval)

    started = time.time()
    research = dataset.research()
    print(
        f"candles  research {interval}: "
        + ", ".join(f"{s} {len(b):,}" for s, b in sorted(research.items()))
        + f"  ({time.time() - started:.0f}s)",
        flush=True,
    )

    windows = IntradayDataset.blocks(research, count=blocks)
    warmed = 0
    for window in windows:
        warmed += _warm(dataset, research, window)
        print(f"panels   {window.label}: {len(research)} symbols", flush=True)

    forward_bars: dict[str, Any] = {}
    if forward:
        started = time.time()
        forward_bars = dataset.combined()
        sealed = IntradayDataset.forward_window(forward_bars, dataset.lock)
        print(
            f"candles  forward {interval}: "
            + ", ".join(f"{s} {len(b):,}" for s, b in sorted(forward_bars.items()))
            + f"  ({time.time() - started:.0f}s)",
            flush=True,
        )
        warmed += _warm(dataset, forward_bars, sealed)
        print(f"panels   {sealed.label}: {len(forward_bars)} symbols", flush=True)

    return {
        "interval": interval,
        "symbols": sorted(research),
        "research_bars": {s: len(b) for s, b in sorted(research.items())},
        "forward_bars": {s: len(b) for s, b in sorted(forward_bars.items())},
        "windows": len(windows) + (1 if forward else 0),
        "panels_warmed": warmed,
        "indicator_root": str(dataset.indicators.root),
    }


def _warm(dataset: IntradayDataset, bars_by_symbol: dict, window: Any) -> int:
    """Compute and store the panel for one window, symbol by symbol.

    Sliced exactly the way `run_window` slices, because the cache is keyed on
    the candles: a panel warmed over a different slice is a different key and
    would be recomputed on the first real run, which would make this whole
    module a no-op that looked like it worked.
    """
    count = 0
    for symbol, bars in bars_by_symbol.items():
        sliced = [bar for bar in bars if window.start <= bar.timestamp <= window.end]
        if len(sliced) < 2:
            continue
        dataset.indicators.panel(symbol, sliced)
        count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--interval", default=INTERVAL)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--data-root", default="backtester/data")
    parser.add_argument("--blocks", type=int, default=DEFAULT_BLOCKS)
    parser.add_argument(
        "--no-forward",
        action="store_true",
        help="skip the sealed window; training blocks only",
    )
    args = parser.parse_args(argv)

    result = prepare(
        args.data_root,
        args.interval,
        [s for s in args.symbols.split(",") if s],
        args.blocks,
        forward=not args.no_forward,
    )
    print(
        f"\nready: {len(result['symbols'])} symbols at {result['interval']}, "
        f"{result['windows']} windows, {result['panels_warmed']} panels cached "
        f"under {result['indicator_root']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
