"""Prune the candle cache down to one copy per symbol, interval and era.

    python -m quantlab_catalog.prune            # report only
    python -m quantlab_catalog.prune --apply    # actually delete

WHAT THIS IS FIXING, found by `inventory` on 2026-09-08. The sealed 2026 window - eight
months - occupied 9.1GB while 2018-2025 occupied 403MB. Backwards, by a factor of
twenty-three.

The cause is a content-addressed cache doing exactly what it was told. The key hashes
the request, and a forward request ends at "now", so every refresh moved the end
timestamp, produced a new hash and wrote a fresh copy of nearly the same file. Research
requests end at the lock, which never moves, so research has exactly one copy per symbol
and forward accumulated 385 for BTCUSDT alone - 5,646 files across 27 symbols.

Nothing was WRONG in any of them. Every copy is a valid manifest and a valid CSV; they
are simply the same window re-downloaded with a slightly later right edge. The newest
covers the most bars, so the newest is the one to keep.

WHY A TOOL AND NOT A ONE-OFF DELETE. This will recur every time a forward run refreshes,
so a shell command run once solves it for a day. Keeping it as a tool means the cleanup
is repeatable, reviewable, and reports what it would do before it does it.

SAFETY. Deletion is opt-in, the newest copy per directory is never a candidate, a CSV
and its manifest are only removed as a pair, and a file another process holds open makes
Windows refuse the unlink - which is reported and skipped rather than swallowed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .paths import DATA_ROOT


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:,.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}GB"


def cache_dirs(root: Path | None = None):
    """Every <phase>/processed/<provider>/<symbol>/<interval> directory holding CSVs."""
    base = Path(root or DATA_ROOT)
    for phase in ("research", "forward"):
        proc = base / phase / "processed"
        if not proc.is_dir():
            continue
        for interval_dir in sorted(proc.glob("*/*/*")):
            if interval_dir.is_dir() and any(interval_dir.glob("*.csv")):
                yield phase, interval_dir


def stale_in(directory: Path) -> list[Path]:
    """Every CSV in the directory except the newest, paired with its manifest.

    Newest by modification time rather than by name: the name is a content hash and
    sorts arbitrarily, so picking the last one alphabetically would keep a random copy
    and throw away the one with the most recent bars in it.
    """
    csvs = sorted(directory.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    doomed: list[Path] = []
    for csv in csvs[1:]:
        doomed.append(csv)
        manifest = csv.with_suffix(".manifest.json")
        if manifest.exists():
            doomed.append(manifest)
    return doomed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="delete; without it this only reports")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    total_files = total_bytes = 0
    kept = 0
    failures: list[tuple[Path, str]] = []
    rows: list[tuple[str, str, int, int]] = []

    for phase, directory in cache_dirs(args.root):
        doomed = stale_in(directory)
        kept += 1
        if not doomed:
            continue
        size = sum(p.stat().st_size for p in doomed if p.exists())
        rows.append((phase, f"{directory.parent.name}/{directory.name}",
                     len(doomed), size))
        total_files += len(doomed)
        total_bytes += size
        if args.apply:
            for p in doomed:
                try:
                    p.unlink()
                except OSError as exc:               # held open by a running backtest
                    failures.append((p, str(exc)))

    rows.sort(key=lambda r: -r[3])
    print(f"{'phase':<9} {'symbol/interval':<22} {'files':>7} {'reclaim':>10}")
    for phase, name, n, size in rows[:12]:
        print(f"{phase:<9} {name:<22} {n:>7} {_human(size):>10}")
    if len(rows) > 12:
        print(f"  ... and {len(rows) - 12} more directories")

    verb = "deleted" if args.apply else "would delete"
    print(f"\n{kept} directories, one copy kept in each.")
    print(f"{verb} {total_files:,} files, {_human(total_bytes)} reclaimed.")
    if failures:
        print(f"\n{len(failures)} file(s) could not be removed - most likely open in a "
              f"running backtest. Re-run later; nothing was lost.")
        for p, why in failures[:5]:
            print(f"  {p.name}: {why}")
    if not args.apply and total_files:
        print("\nRun again with --apply to delete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
