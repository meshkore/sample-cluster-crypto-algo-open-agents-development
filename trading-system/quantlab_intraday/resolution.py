"""Which bar interval can pay for itself? The one measurement that decides.

    python3 -m quantlab_intraday.resolution

The operator's premise for this system is that raising the resolution raises
the number of opportunities, and that more opportunities is more edge. The
first half is arithmetic and true: 15-minute bars carry 96 times the decisions
of daily ones. The second half is the part that has to be measured, because
raising the resolution also shrinks the move each decision is about while
leaving the toll exactly where it was. A round trip costs 0.30% whether the bar
is five minutes or five days.

So the question this module answers is not "does the signal work" but "at what
interval does what the signal predicts become larger than what trading it
costs". The same scale-free rule -- a bar closing near its low, more than 1.5
ATR below its own 20-bar VWAP -- is run at every interval, and the answer is
read off one column: `net`, the conditional mean forward return minus the
round trip. Every negative number in that column is an interval at which this
mechanism cannot be traded, however good its win rate looks.

Two properties make the comparison fair. The turnover floor is converted into
each interval's own units, so the capacity invariant is the same dollars
everywhere rather than 96 times stricter at 15m. And the horizons are quoted in
hours as well as bars, so a row is comparable to the row above it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from . import edge
from .dataset import DEFAULT_SYMBOLS, LOCK, IntradayDataset

# Bars per day at each interval, which is what converts the charter's daily
# capacity floor into the unit `dollar_volume_20` is actually measured in.
BARS_PER_DAY = {"5m": 288, "15m": 96, "30m": 48, "1h": 24, "4h": 6, "1d": 1}

# Horizons in HOURS, converted to bars per interval. Comparing "eight bars" at
# 5m against "eight bars" at 4h would compare forty minutes to thirty-two
# hours, which is not a comparison.
HORIZON_HOURS = (0.5, 1, 2, 4, 8, 24)


def horizons_for(interval: str) -> tuple[int, ...]:
    per_hour = BARS_PER_DAY[interval] / 24
    bars = {max(1, round(hours * per_hour)) for hours in HORIZON_HOURS}
    return tuple(sorted(bars))


def scan_interval(
    data_root: Path | str,
    interval: str,
    symbols: Iterable[str] = DEFAULT_SYMBOLS,
    **overrides: Any,
) -> dict[str, Any]:
    """One interval, research bars only. The sealed window is never touched."""
    dataset = IntradayDataset(data_root, LOCK, symbols, interval=interval)
    bars = dataset.research()
    report = edge.scan(
        bars,
        horizons=horizons_for(interval),
        bars_per_day=BARS_PER_DAY[interval],
        **overrides,
    )
    report["interval"] = interval
    report["symbols"] = sorted(bars)
    report["bars"] = {symbol: len(series) for symbol, series in bars.items()}
    return report


def best_row(report: dict[str, Any]) -> dict[str, Any] | None:
    """The horizon where this interval comes closest to paying for itself.

    Chosen on the NET mean, not the gross and not the win rate. A rule with a
    70% win rate and a negative net is a rule that loses money reliably, which
    is the specific illusion short-horizon systems are built out of.
    """
    rows = [row for row in report["signal"] if row.get("n")]
    return max(rows, key=lambda row: row["net_mean"]) if rows else None


def table(reports: list[dict[str, Any]]) -> str:
    lines = [
        f"{'interval':>9}{'signals':>10}{'best h':>9}{'hours':>8}"
        f"{'gross':>10}{'net':>10}{'indep n':>9}{'t*':>7}{'win%':>7}{'drift':>10}",
        "-" * 96,
    ]
    for report in reports:
        row = best_row(report)
        if row is None:
            lines.append(f"{report['interval']:>9}{'no signals':>10}")
            continue
        drift = {
            base["horizon"]: base.get("gross_mean", 0.0) for base in report["baseline"]
        }.get(row["horizon"], 0.0)
        thin = {item["horizon"]: item for item in report.get("independent", [])}.get(
            row["horizon"], {}
        )
        hours = row["horizon"] / (BARS_PER_DAY[report["interval"]] / 24)
        lines.append(
            f"{report['interval']:>9}{row['n']:>10,}{row['horizon']:>9}"
            f"{hours:>8.1f}{row['gross_mean']:>10.3%}{row['net_mean']:>10.3%}"
            f"{thin.get('n', 0):>9,}{thin.get('net_t', 0.0):>7.1f}"
            f"{row['win_rate']:>7.0%}{drift:>10.3%}"
        )
    lines += [
        "",
        "gross = mean return after a qualifying bar, filled at the next open",
        "net   = gross minus the 0.30% round trip. Positive is the whole question.",
        "t*    = t on NON-OVERLAPPING observations only. The t on all of them is",
        "        inflated by however many windows share the same move -- 288 of",
        "        them at a 24-hour horizon on 5-minute bars.",
        "drift = the same horizon after ANY bar. gross must beat this, not zero.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-root", default="backtester/data")
    parser.add_argument("--intervals", default="5m,15m,30m,1h,4h")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    symbols = [symbol for symbol in args.symbols.split(",") if symbol]
    reports = []
    for interval in args.intervals.split(","):
        if not interval:
            continue
        try:
            report = scan_interval(args.data_root, interval, symbols)
        except Exception as exc:  # noqa: BLE001 - a missing cache is not a crash
            print(f"{interval}: skipped ({type(exc).__name__}: {exc})")
            continue
        reports.append(report)
        print(f"{interval}: {sum(report['bars'].values()):,} bars scanned", flush=True)

    print()
    print(table(reports))
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(reports, indent=2, default=str))
        print(f"\nreport: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
