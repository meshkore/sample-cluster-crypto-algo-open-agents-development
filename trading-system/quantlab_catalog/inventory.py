"""What this laboratory actually has on disk, and what it does not.

    python -m quantlab_catalog.inventory

The second half is the point. A catalogue that lists only what it holds lets a reader
assume the rest is a fetch away, and this project has queued experiments against data
nobody had - A87 waited on macro vintages for weeks. So the report ends with an
explicit MISSING section naming the things a new system might reasonably expect and
will not find: hourly candles, 5-minute candles, order-book depth, news text.

Everything here is measured from the filesystem at the moment you run it. Nothing is
declared, because a declared inventory is a document that starts being wrong the day
it is written.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .candles import INTERVALS
from .external import series_status
from .paths import (DATA_ROOT, EXTERNAL_DIR, INDICATOR_ROOT, LOCK, UNIVERSE_DIR,
                    legacy_hits, universe_file)

# What a new system might reasonably expect and will not find here. Each with the
# reason, so nobody re-discovers it by writing an experiment first.
MISSING = [
    ("1h candles", "never downloaded; the 15m series can be resampled, which is not "
                   "the same thing as an independently sourced hourly bar"),
    ("5m candles", "quantlab_intraday's timeframe; its cache is not on this machine"),
    ("order-book depth", "no venue feed has ever been ingested; the participation cap "
                         "in the backtester is a modelled constraint, not measured depth"),
    ("news text", "no feed, no archive, no vendor. The nearest thing the catalogue "
                  "holds is Fear & Greed, which is a sentiment INDEX and not news"),
    ("macro vintages", "FRED is here, ALFRED (point-in-time revisions) is not, which "
                       "is what A87 has been queued on"),
]


def _size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:,.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}GB"


def _symbols_with(phase: str, interval: str) -> list[str]:
    root = DATA_ROOT / phase / "processed" / "binance"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if (p / interval).is_dir() and any((p / interval).glob("*.csv")))


def main() -> int:
    print("=" * 78)
    print("SHARED DATA CATALOGUE")
    print(f"root: {DATA_ROOT}")
    print(f"lock: {LOCK}  (research is strictly before; forward is at or after)")
    print("=" * 78)

    print("\nPRICE")
    for interval in INTERVALS:
        for phase in ("research", "forward"):
            syms = _symbols_with(phase, interval)
            size = _size(DATA_ROOT / phase / "processed" / "binance")
            print(f"  {phase:<9} {interval:<4} {len(syms):>3} symbols  {_human(size):>9}"
                  + (f"   e.g. {', '.join(syms[:4])}" if syms else "   (none)"))

    print("\nUNIVERSE")
    up = universe_file()
    if up.is_file():
        import json
        data = json.loads(up.read_text(encoding="utf-8"))
        syms = data.get("symbols") if isinstance(data, dict) else data
        print(f"  {len(syms):>3} symbols   {up}")
    else:
        print(f"  MISSING - {up}")

    print("\nEXTERNAL (non-price)")
    for fam, st in series_status().items():
        loc = "" if st["in_catalogue"] in (True, None) else "   [LEGACY PATH]"
        print(f"  {fam:<10} {st['files']:>3} file(s)  {_human(st['bytes']):>9}  "
              f"{st['what']}{loc}")

    print("\nDERIVED (per system, not interchangeable)")
    if INDICATOR_ROOT.is_dir():
        for sysdir in sorted(p for p in INDICATOR_ROOT.iterdir() if p.is_dir()):
            phases = sorted(p.name for p in sysdir.iterdir() if p.is_dir())
            print(f"  {sysdir.name:<10} {_human(_size(sysdir)):>9}  phases: "
                  f"{', '.join(phases) or 'none'}")
    else:
        print("  (no indicator caches)")

    stale = legacy_hits()
    if stale:
        print("\nNOT YET MIGRATED - still only in a pre-catalogue location")
        for kind, names in stale.items():
            print(f"  {kind}: {len(names)} file(s) - {', '.join(names[:4])}"
                  + (" ..." if len(names) > 4 else ""))

    print("\nMISSING - what a new system might expect and will NOT find here")
    for name, why in MISSING:
        print(f"  {name:<18} {why}")

    print("\nNothing in this package downloads. Fetching is a deliberate act with its "
          "own entry point,\nso no backtest can reach the internet halfway through a run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
