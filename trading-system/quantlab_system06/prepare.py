"""Create a COMPLETE dataset, once: candles downloaded AND indicators precomputed.

A dataset is not "the candles". Training, inference and the backtest all read the
~91-column indicator panel, and computing it on every pass is the difference
between an iteration you run while you think and one you run while you wait. So
this step does both halves and both eras — it downloads the universe's 15-minute
history (research and the sealed forward window) and warms the indicator cache for
each, so everything after it reads panels from disk.

Idempotent and safe to re-run: candles already cached are not re-downloaded, and
a panel is rebuilt only when the candles it was built from changed (the cache key
is a digest of the OHLCV stream). Run this whenever the universe changes or new
forward bars have accrued; the rest of the pipeline assumes it has been run.

    python3 -m quantlab_system06.prepare
"""

from __future__ import annotations

import argparse
import time

from . import universe
from .dataset import Dataset
from .features import combined_store, research_store


def prepare(
    symbols: list[str] | None = None,
    data_root: str = "backtester/data",
    interval: str = "15m",
    forward: bool = True,
) -> dict:
    """Download candles and warm every indicator panel, research and forward."""
    symbols = symbols or universe.load()
    dataset = Dataset(data_root, symbols=symbols, interval=interval)

    started = time.time()
    research = dataset.research()
    rstore = research_store(data_root)
    warmed_r = 0
    for symbol, bars in sorted(research.items()):
        if len(bars) >= 2:
            rstore.panel(symbol, bars)  # compute + cache the full panel
            warmed_r += 1
    print(f"research: {warmed_r}/{len(symbols)} symbols, panels cached  "
          f"({time.time() - started:.0f}s)", flush=True)

    warmed_f = 0
    combined_bars: dict = {}
    if forward:
        started = time.time()
        combined_bars = dataset.combined()
        cstore = combined_store(data_root)
        for symbol, bars in sorted(combined_bars.items()):
            if len(bars) >= 2:
                cstore.panel(symbol, bars)
                warmed_f += 1
        print(f"forward:  {warmed_f}/{len(symbols)} symbols, panels cached  "
              f"({time.time() - started:.0f}s)", flush=True)

    return {
        "symbols": symbols,
        "research_symbols": sorted(research),
        "research_bars": {s: len(b) for s, b in sorted(research.items())},
        "forward_symbols": sorted(combined_bars),
        "research_panels": warmed_r,
        "forward_panels": warmed_f,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols", default=None, help="comma list; default = the saved universe")
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--data-root", default="backtester/data")
    parser.add_argument("--no-forward", action="store_true")
    args = parser.parse_args(argv)
    symbols = [s for s in args.symbols.split(",") if s] if args.symbols else None
    result = prepare(symbols, args.data_root, args.interval, forward=not args.no_forward)
    print(f"\nready: {result['research_panels']} research + {result['forward_panels']} "
          f"forward panels cached for {len(result['symbols'])} symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
