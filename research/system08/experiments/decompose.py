"""Where the residual book's money actually comes from, by year and by component.

WHY THIS EXISTS

Cycle 3 widened the cross-section from fourteen names to thirty-two on an identical
configuration. The research drawdown improved a third, and two things went the other way:
the sealed 2026 read turned negative, and funding flipped from +26k received to -10.8k
PAID. The second of those contradicts the design's own thesis - crypto perpetual funding is
structurally positive, so a book that is short the losers is supposed to be PAID to hold
them. A thesis that the book's own ledger contradicts is either wrong or wrongly
implemented, and guessing which one costs more than measuring it.

So this reads the four components the book already records separately - asset, hedge,
funding, cost - and reports them per year as a fraction of the equity they were earned on.
It decides nothing. It is a diagnostic, and its only job is to say which component to go
and look at.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

sys.path.insert(0, "trading-system")

from quantlab_catalog.paths import universe_file          # noqa: E402
import quantlab_catalog as cat                            # noqa: E402
from quantlab_system08.system import Config, build        # noqa: E402


def decompose(days) -> dict[str, dict[str, float]]:
    """Per-year totals of every component, each divided by the equity it was earned on.

    Dividing by the START-of-day equity rather than the initial equity is what makes the
    years comparable: a book that has compounded 5x earns absolute dollars that dwarf its
    first year without earning a better return, and summing raw dollars would report that
    as a trend.
    """
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    prev = None
    for d in days:
        base = prev if prev and prev > 0 else d.equity
        y = d.day[:4]
        row = out[y]
        row["asset"] += d.asset_pnl / base
        row["hedge"] += d.hedge_pnl / base
        row["funding"] += d.funding_pnl / base
        row["cost"] -= d.cost / base
        row["net"] += d.net / base if getattr(d, "net", None) is not None else 0.0
        row["gross_avg"] += d.gross
        row["n_long"] += d.n_long
        row["n_short"] += d.n_short
        row["days"] += 1
        prev = d.equity
    for row in out.values():
        n = row["days"] or 1
        row["gross_avg"] /= n
        row["n_long"] /= n
        row["n_short"] /= n
    return {k: dict(v) for k, v in sorted(out.items())}


def run(universe: str, sealed: bool) -> dict:
    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    declared = [str(s) for s in meta["symbols"]]
    bars = (cat.candles(declared, include_sealed=True) if sealed
            else cat.research(declared))
    bars = {s: b for s, b in bars.items() if b}
    return decompose(build(bars, Config()).result.days)


def main() -> int:
    for universe in ("universe.json", "universe_wide.json"):
        rows = run(universe, sealed=True)
        print(f"\n=== {universe} ===")
        print(f"{'year':<6}{'asset':>9}{'hedge':>9}{'funding':>9}{'cost':>9}"
              f"{'gross':>8}{'long':>7}{'short':>7}")
        for y, r in rows.items():
            print(f"{y:<6}{r['asset']:>9.3f}{r['hedge']:>9.3f}{r['funding']:>9.4f}"
                  f"{r['cost']:>9.3f}{r['gross_avg']:>8.2f}{r['n_long']:>7.1f}"
                  f"{r['n_short']:>7.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
