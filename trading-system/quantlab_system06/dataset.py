"""BTCUSDT at 15 minutes, split at the 2026 lock, downloaded once.

Everything here goes through the frozen instrument's own loaders
(`quantlab_backtester.data.FocusedDataset`), so the research/forward split and
the 2026 lock are enforced by the same code as everywhere else in the lab, and
this system learns no second universe table. Candles cache under
`backtester/data/research/processed/binance/BTCUSDT/15m/` and `.../forward/...`,
both gitignored.

`research()` is all history strictly before 2026-01-01; `combined()` splices the
sealed 2026 window on the far end. A run scores only bars at or after the lock,
but needs the history in front of it so every indicator is already warm when the
first 2026 bar arrives.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from quantlab_backtester.data import FocusedDataset
from quantlab_backtester.models import Bar

# One symbol, one timeframe for v1. Both are `--flags` so the pipeline scales,
# but the hypothesis is deliberately measured on BTCUSDT/15m first.
SYMBOL = "BTCUSDT"
INTERVAL = "15m"
BARS_PER_DAY = 96  # 15-minute bars

# Timezone-aware so it compares against the loader's aware timestamps; the bare
# "2026-01-01" raises deep in the loader with an offset-naive/aware error.
LOCK = "2026-01-01T00:00:00+00:00"

DATA_ROOT = "backtester/data"


class Dataset:
    """15-minute candles for system06, cached and era-split at the lock."""

    def __init__(
        self,
        data_root: Path | str = DATA_ROOT,
        lock: str = LOCK,
        symbols: Iterable[str] = (SYMBOL,),
        interval: str = INTERVAL,
    ):
        self.root = Path(data_root)
        self.lock = datetime.fromisoformat(lock)
        self.interval = interval
        self.symbols = list(symbols)
        self.source = FocusedDataset(self.root, lock)

    def research(self) -> dict[str, list[Bar]]:
        """All available history strictly before the 2026 lock. Downloads once."""
        return self.source.research_bars(self.symbols, self.interval)

    def combined(self, end: datetime | None = None) -> dict[str, list[Bar]]:
        """Research history spliced with the sealed 2026 window, for a forward run."""
        return self.source.combined_bars(
            self.symbols, self.interval, end or datetime.now(timezone.utc)
        )


def _summary(tag: str, bars_by_symbol: dict[str, list[Bar]]) -> None:
    for symbol, bars in sorted(bars_by_symbol.items()):
        first = bars[0].timestamp.date() if bars else "-"
        last = bars[-1].timestamp.date() if bars else "-"
        print(f"  {tag:8} {symbol:9} {len(bars):>8,} bars  {first} -> {last}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols", default=SYMBOL)
    parser.add_argument("--interval", default=INTERVAL)
    parser.add_argument("--data-root", default=DATA_ROOT)
    parser.add_argument(
        "--forward",
        action="store_true",
        help="also download/splice the sealed 2026 window (needs network to 2026 bars)",
    )
    args = parser.parse_args(argv)

    dataset = Dataset(
        args.data_root,
        symbols=[s for s in args.symbols.split(",") if s],
        interval=args.interval,
    )

    print(f"downloading {args.interval} candles (this caches to disk; re-runs are free)")
    research = dataset.research()
    _summary("research", research)

    if args.forward:
        combined = dataset.combined()
        forward = {
            s: [b for b in bars if b.timestamp >= dataset.lock]
            for s, bars in combined.items()
        }
        _summary("forward", forward)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
