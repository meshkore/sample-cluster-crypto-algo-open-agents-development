"""Getting a fresh machine from `git clone` to a runnable laboratory.

This module exists because of a gap nobody had noticed from inside the
operator's machine: **the public repository could not acquire its own data.**
`asset_universe` -- the table every other component reads to learn which symbols
exist and where their candles live -- was created by code that is not in this
tree, and `quantlab download` crashed on its first line because it passed a
provider where a path belonged. Both facts are invisible to anyone whose machine
already had the table. They are the first thing anyone else hits.

So this is the bootstrap. One command, resumable, that:

  * asks Binance which USDT spot symbols exist,
  * downloads daily candles for each one into the RESEARCH store, which is
    hard-stopped at the 2025-12-31 lock,
  * downloads 2026 into a SEPARATE forward store that research code refuses to
    read,
  * records both paths in `asset_universe` so the rest of the laboratory can
    find them.

**The two stores are not a tidiness preference.** `DataManager.validate` raises
if a research dataset contains a single post-lock bar, and the backtester
process only splices the forward file in when it was started with `--forward`.
That is the mechanism behind "2026 is sealed": a strategy cannot accidentally
see next year's tape, because the process fitting it does not have the file
open. Keeping acquisition in one function keeps that separation in one place.

Nothing here computes an indicator. Candles land on disk raw; `backfill` turns
them into the 91-column panels every strategy reads. Downloading is network
bound and backfilling is CPU bound, so they stay separate commands -- a failed
download should not cost an hour of arithmetic, and a re-backfill should not
re-hit the exchange.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
import shutil
import sqlite3

from quantlab_backtester.data import (
    BinanceProvider,
    DataError,
    DataManager,
    ForwardDataManager,
)

from .config import Settings

# The first day Binance quoted a USDT spot pair. Starting earlier buys empty
# pages; starting later silently truncates BTC's history for everyone.
HISTORY_BEGINS = "2017-08-17"

# Where research stops, forever. Read from `splits.future_lock_start` when the
# config has one, so the boundary has a single owner.
DEFAULT_LOCK = "2026-01-01T00:00:00Z"

# Measured, not guessed: 386 symbols of daily candles occupy 36 MB of research
# CSV plus 17 MB of forward CSV on the operator's machine, and the indicator
# panels built from them occupy 591 MB. Refuse to start a download that cannot
# finish, because a half-filled universe is worse than an empty one -- every
# result computed on it is quietly narrower than it claims.
BYTES_PER_SYMBOL_CANDLES = 140_000
BYTES_PER_SYMBOL_INDICATORS = 1_600_000
DISK_HEADROOM = 512 * 1024 * 1024


UNIVERSE_SCHEMA = """
CREATE TABLE IF NOT EXISTS asset_universe (
  symbol TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  research_path TEXT,
  forward_path TEXT,
  last_error TEXT,
  updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def lock_of(settings: Settings) -> str:
    return str((settings.splits or {}).get("future_lock_start") or DEFAULT_LOCK)


def ensure_schema(database: Path | str) -> None:
    """Create `asset_universe` if this machine has never had one."""
    path = Path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(UNIVERSE_SCHEMA)
        connection.commit()
    finally:
        connection.close()


def disk_budget(settings: Settings, symbols: int) -> dict[str, Any]:
    """What this download will cost and whether the disk can pay for it.

    Reported whether or not it passes: a contributor who knows the number can
    decide to take fifty symbols instead of four hundred, which is a perfectly
    good contribution. A contributor who only learns it when the disk fills
    mid-write has a corrupt store and no idea which symbol is short.
    """
    root = Path(settings.data_root)
    anchor = root if root.exists() else Path(".")
    usage = shutil.disk_usage(anchor)
    candles = symbols * BYTES_PER_SYMBOL_CANDLES
    indicators = symbols * BYTES_PER_SYMBOL_INDICATORS
    needed = candles + indicators + DISK_HEADROOM
    return {
        "symbols": symbols,
        "candles_bytes": candles,
        "indicators_bytes": indicators,
        "total_bytes_needed": needed,
        "free_bytes": usage.free,
        "sufficient": usage.free >= needed,
        "note": (
            "indicators are not written by this command -- the figure is what "
            "`backfill` will add afterwards, and it is the larger half"
        ),
    }


def _record(
    connection: sqlite3.Connection,
    symbol: str,
    *,
    status: str,
    research: str | None,
    forward: str | None,
    error: str | None,
) -> None:
    stamp = _now()
    connection.execute(
        """
        INSERT INTO asset_universe
          (symbol, status, first_seen, last_seen, research_path, forward_path,
           last_error, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
          status = excluded.status,
          last_seen = excluded.last_seen,
          -- A failed refresh must not erase a path that already works. The
          -- error is recorded beside the good data, not instead of it.
          research_path = COALESCE(excluded.research_path, asset_universe.research_path),
          forward_path = COALESCE(excluded.forward_path, asset_universe.forward_path),
          last_error = excluded.last_error,
          updated_at = excluded.updated_at
        """,
        (symbol, status, stamp, stamp, research, forward, error, stamp),
    )


def _download_one(
    provider: BinanceProvider,
    research: DataManager,
    forward: ForwardDataManager | None,
    symbol: str,
    interval: str,
    lock: datetime,
) -> tuple[str | None, str | None]:
    research_path: str | None = None
    forward_path: str | None = None

    bars = provider.bars(symbol, interval, _moment(HISTORY_BEGINS), lock)
    if len(bars) >= 3:
        # `require_clean_audit=False`: Binance's first months have documented
        # gaps, and refusing the whole symbol over a 2017 outage would drop real
        # history. The gap stays in the manifest either way, so it is disclosed
        # rather than hidden, and `validate()` still enforces OHLCV sanity.
        research_path = str(
            research.save_csv(
                bars, "binance", symbol, interval, require_clean_audit=False
            )
        )

    if forward is not None:
        ahead = provider.bars(symbol, interval, lock, datetime.now(timezone.utc))
        if len(ahead) >= 3:
            forward_path = str(
                forward.save_csv(
                    ahead, "binance", symbol, interval, require_clean_audit=False
                )
            )
    return research_path, forward_path


def acquire(
    settings: Settings,
    symbols: Iterable[str] | None = None,
    interval: str = "1d",
    forward: bool = True,
    limit: int | None = None,
    progress: Callable[[int, int, str, str], None] | None = None,
) -> dict[str, Any]:
    """Download the universe. Safe to interrupt and safe to re-run.

    Symbols already on disk are re-downloaded rather than skipped, because the
    forward window grows every day and a store that silently stops at whenever
    it was first built is the kind of staleness that produces a wrong number
    without producing an error. Re-running is cheap relative to being wrong.
    """
    provider = BinanceProvider()
    lock_text = lock_of(settings)
    lock = _moment(lock_text)

    wanted = sorted(symbols) if symbols else provider.spot_usdt_symbols()
    if limit:
        wanted = wanted[:limit]

    budget = disk_budget(settings, len(wanted))
    if not budget["sufficient"]:
        raise DataError(
            f"{len(wanted)} symbols need about "
            f"{budget['total_bytes_needed'] / 1e9:.1f} GB including the indicator "
            f"backfill, and {budget['free_bytes'] / 1e9:.1f} GB is free. Pass "
            "--limit to take a smaller universe, or free space first."
        )

    root = Path(settings.data_root)
    research_store = DataManager(root / "research", lock_text)
    forward_store = ForwardDataManager(root / "forward", lock_text) if forward else None

    ensure_schema(settings.database_path)
    connection = sqlite3.connect(settings.database_path)

    report: dict[str, Any] = {
        "interval": interval,
        "lock": lock_text,
        "requested": len(wanted),
        "research_ready": 0,
        "forward_ready": 0,
        "failed": 0,
        "errors": {},
        "disk": budget,
    }

    try:
        for index, symbol in enumerate(wanted, 1):
            try:
                research_path, forward_path = _download_one(
                    provider, research_store, forward_store, symbol, interval, lock
                )
            except (DataError, OSError, ValueError) as exc:
                # One delisted or malformed symbol must not end the run. Four
                # hundred downloads take long enough that restarting from zero
                # over a single bad series is its own kind of failure.
                report["failed"] += 1
                report["errors"][symbol] = str(exc)[:200]
                _record(
                    connection,
                    symbol,
                    status="ERROR",
                    research=None,
                    forward=None,
                    error=str(exc)[:400],
                )
                state = "failed"
            else:
                report["research_ready"] += 1 if research_path else 0
                report["forward_ready"] += 1 if forward_path else 0
                _record(
                    connection,
                    symbol,
                    status="TRADING",
                    research=research_path,
                    forward=forward_path,
                    error=None,
                )
                state = "ok" if research_path else "empty"
            connection.commit()
            if progress:
                progress(index, len(wanted), symbol, state)
    finally:
        connection.commit()
        connection.close()

    return report


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="download the candle universe")
    parser.add_argument(
        "--config", default="orchestrator-manager/config/default.json", type=Path
    )
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--no-forward",
        action="store_true",
        help="skip the 2026 store; research-only machines do not need it",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="report the disk cost and exit without downloading anything",
    )
    args = parser.parse_args(argv)

    settings = Settings.load(args.config)

    if args.plan:
        count = len(args.symbols) if args.symbols else 400
        print(json.dumps(disk_budget(settings, count), indent=2))
        return 0

    def show(index: int, total: int, symbol: str, state: str) -> None:
        print(f"[{index:>4}/{total}] {symbol:<14} {state}", flush=True)

    report = acquire(
        settings,
        symbols=args.symbols,
        interval=args.interval,
        forward=not args.no_forward,
        limit=args.limit,
        progress=show,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
