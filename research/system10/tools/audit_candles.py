"""S10-4: is what 010 trains on whole, causal, and physically separated from 2026?

Reads the 14-symbol universe at 15m through the catalogue's research entry point - the
same one 010 will train from - and counts, per symbol: bars, first and last stamp, gaps
(a step longer than 15 minutes, and the bars they cost), duplicate stamps, stamps off the
15-minute grid, non-positive prices, high < low, open/close outside [low, high], and zero
volume. Writes a dated JSON beside itself; DATA_AUDIT.md is written from it.

Run from the repo root with PYTHONPATH="trading-system;trading-system/systems;backtester".
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quantlab_catalog.candles import research
from quantlab_catalog.paths import LOCK

REPO = Path(__file__).resolve().parents[3]
STEP = timedelta(minutes=15)
LAST_ALLOWED = datetime(2025, 12, 31, 23, 45, tzinfo=timezone.utc)


def audit(symbol: str, bars) -> dict:
    stamps = [b.timestamp for b in bars]
    gaps, missing, longest, dups, off_grid = 0, 0, timedelta(0), 0, 0
    worst_gap_at = None
    for a, b in zip(stamps, stamps[1:]):
        d = b - a
        if d == timedelta(0):
            dups += 1
        elif d < STEP or d % STEP:
            off_grid += 1
        elif d > STEP:
            gaps += 1
            missing += d // STEP - 1
            if d > longest:
                longest, worst_gap_at = d, a
    nonpos = sum(1 for b in bars if min(b.open, b.high, b.low, b.close) <= 0)
    inverted = sum(1 for b in bars if b.high < b.low)
    outside = sum(1 for b in bars if not (b.low <= b.open <= b.high and b.low <= b.close <= b.high))
    zero_vol = sum(1 for b in bars if (b.volume or 0) <= 0)
    off_clock = sum(1 for t in stamps if t.minute % 15 or t.second or t.microsecond)
    span = (stamps[-1] - stamps[0]) // STEP + 1
    return {
        "symbol": symbol, "bars": len(bars),
        "first": stamps[0].isoformat(), "last": stamps[-1].isoformat(),
        "expected_bars": span, "coverage": round(len(bars) / span, 6),
        "gaps": gaps, "missing_bars": missing,
        "longest_gap_hours": round(longest.total_seconds() / 3600, 2),
        "longest_gap_after": worst_gap_at.isoformat() if worst_gap_at else None,
        "duplicate_stamps": dups, "off_grid_steps": off_grid, "off_clock_stamps": off_clock,
        "non_positive_price": nonpos, "high_below_low": inverted,
        "open_or_close_outside_range": outside, "zero_volume": zero_vol,
        "any_2026_bar": any(t >= datetime.fromisoformat(LOCK) for t in stamps),
        "last_within_seal": stamps[-1] <= LAST_ALLOWED,
    }


def main() -> None:
    symbols = json.loads((REPO / "research/system06/universe.json").read_text())["symbols"]
    data = research(symbols)
    rows = [audit(s, data[s]) for s in symbols if data.get(s)]
    absent = [s for s in symbols if not data.get(s)]
    # Clock alignment across symbols: from the latest listing on, every symbol should
    # carry the same stamps. Count the stamps some symbols have and others do not.
    common_from = max(datetime.fromisoformat(r["first"]) for r in rows)
    sets = {s: {b.timestamp for b in data[s] if b.timestamp >= common_from} for s in symbols if data.get(s)}
    union = set().union(*sets.values())
    inter = set.intersection(*sets.values())
    out = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lock": LOCK, "universe": symbols, "absent": absent, "per_symbol": rows,
        "alignment": {"common_from": common_from.isoformat(), "union_stamps": len(union),
                      "stamps_on_every_symbol": len(inter),
                      "stamps_missing_somewhere": len(union - inter)},
    }
    path = Path(__file__).with_name(f"audit_candles_{datetime.now(timezone.utc):%Y-%m-%d}.json")
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(path)
    for r in rows:
        print(r["symbol"], r["bars"], r["first"][:10], r["last"][:16], "gaps", r["gaps"], "miss", r["missing_bars"],
              "long_h", r["longest_gap_hours"], "dup", r["duplicate_stamps"], "offgrid", r["off_grid_steps"],
              "bad", r["non_positive_price"], r["high_below_low"], r["open_or_close_outside_range"],
              "zvol", r["zero_volume"], "2026", r["any_2026_bar"])
    print("absent", absent, "alignment", out["alignment"])


if __name__ == "__main__":
    main()
