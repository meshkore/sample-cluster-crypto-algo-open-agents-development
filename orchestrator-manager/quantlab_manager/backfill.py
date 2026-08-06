"""Backfill indicators for the whole universe, once, from day one.

Called by the orchestrator before a research campaign, or on its own when the
candle set grows. After it runs, every backtest reads indicator values from disk
instead of deriving them, which is the point: the arithmetic is generic work and
generic work belongs to the instrument, not to the brain.

    from quantlab_manager.backfill import backfill_universe
    report = backfill_universe(settings)

Re-running is cheap and safe. A symbol whose cached panel already matches its
candles is skipped, and a symbol whose candles have changed is rebuilt, because
the cache header carries a digest of the OHLCV stream it was computed from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import sqlite3

from quantlab_backtester.data import DataManager
from quantlab_backtester.indicator_store import IndicatorStore
from quantlab_backtester.indicators import IndicatorSpec

from .config import Settings


def indicator_root(settings: Settings) -> Path:
    """Beside the candles, not inside the repository.

    These files are derived data: large, regenerable, and worthless to a reader
    of the source. They live with the market data that produced them.
    """
    return Path(getattr(settings, "data_root", "data")) / "indicators"


def load_universe(
    settings: Settings, symbols: list[str] | None = None
) -> dict[str, list]:
    connection = sqlite3.connect(f"file:{settings.database_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT symbol, research_path FROM asset_universe "
            "WHERE research_path IS NOT NULL ORDER BY symbol"
        ).fetchall()
    finally:
        connection.close()
    wanted = set(symbols or [])
    out: dict[str, list] = {}
    for row in rows:
        if wanted and row["symbol"] not in wanted:
            continue
        bars = DataManager.load_csv(row["research_path"])
        if len(bars) >= 2:
            out[row["symbol"]] = bars
    return out


def backfill_universe(
    settings: Settings,
    symbols: list[str] | None = None,
    spec: IndicatorSpec | None = None,
    on_progress: Callable[[int, str, int, int, int], None] | None = None,
) -> dict[str, Any]:
    spec = spec or IndicatorSpec()
    store = IndicatorStore(indicator_root(settings))
    universe = load_universe(settings, symbols)
    if not universe:
        return {
            "symbols": 0,
            "written": 0,
            "reused": 0,
            "failed": 0,
            "note": "empty universe",
        }
    report = store.backfill(universe, spec, progress=on_progress)
    report["root"] = str(store.root)
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="orchestrator-manager/config/default.json", type=Path
    )
    parser.add_argument("--symbols", nargs="*", default=None)
    args = parser.parse_args(argv)
    settings = Settings.load(args.config)

    def progress(index, symbol, written, reused, failed):
        if index % 25 == 0:
            print(
                f"  {index:>4}  {symbol:<14} written {written} reused {reused} failed {failed}",
                flush=True,
            )

    report = backfill_universe(settings, args.symbols, on_progress=progress)
    print(
        f"\n{report['symbols']} symbols · {report.get('columns', 0)} columns · "
        f"warm-up {report.get('warmup_bars', 0)} bars\n"
        f"written {report['written']}  reused {report['reused']}  failed {report['failed']}\n"
        f"root {report.get('root')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
