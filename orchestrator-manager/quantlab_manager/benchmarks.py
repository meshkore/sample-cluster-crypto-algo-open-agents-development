"""What the market did, so a return can be read as skill or as weather.

The laboratory spent ninety iterations reporting 2026 as an absolute number and
concluding it was failing. Over 2026-01-01..07-31 the equal-weight basket of the
436 assets it holds forward data for returned **-39.8%**, the median asset
-48.5%, and 41 of 436 finished up. Against that, the best forward result the
laboratory has produced -- +1.12% -- is not "almost nothing". It is the market
minus forty-one points of loss.

That does not make the strategy good. It makes the comparison necessary before
anyone can say. A long-only book in a year where nine assets in ten fell has a
ceiling near cash, and a scoreboard reading against zero cannot tell "correctly
refused to participate" from "did nothing", which are the same number and
completely different findings.

`quantlab_backtester.benchmark` already computes both references from bars. It
was never wired to the loop because the loop has no bars -- the backtester holds
them. This module is the missing half: it loads the same CSVs the run was served
from, over the same window, and hands them to that function. Costs are charged
to the benchmark exactly as the strategy pays them, so the comparison is not
quietly rigged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import sqlite3

from quantlab_backtester import benchmark
from quantlab_backtester.data import DataManager

from .config import Settings


def _moment(value: str) -> datetime:
    text = str(value).replace("Z", "+00:00")
    stamp = datetime.fromisoformat(text)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _paths(
    database: Path | str, forward: bool, symbols: Iterable[str] | None
) -> dict[str, str]:
    column = "forward_path" if forward else "research_path"
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    except sqlite3.Error:
        return {}
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            f"SELECT symbol, {column} AS path FROM asset_universe "
            f"WHERE {column} IS NOT NULL"
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        connection.close()
    wanted = set(symbols) if symbols else None
    return {
        row["symbol"]: row["path"]
        for row in rows
        if wanted is None or row["symbol"] in wanted
    }


def market(
    settings: Settings,
    start: str,
    end: str,
    strategy_return: float | None = None,
    symbols: Iterable[str] | None = None,
    forward: bool = True,
    commission_bps: float = 10.0,
    slippage_bps: float = 5.0,
) -> dict[str, Any]:
    """Both references over `start..end`, and the strategy's excess over them.

    Never raises. A benchmark that can take an iteration down is worse than no
    benchmark: this is commentary on a result, and the result is the thing that
    must survive. A machine with no universe table, an unreadable CSV or a
    window with no bars in it all come back as `None` references and an honest
    `error`, and the caller records the run either way.

    The forward store is the default because the question that prompted this is
    a 2026 question, and reading 2026 here is not a leak -- the benchmark is
    reported beside a result already decided and never enters selection. That
    is the same standing the forward run itself has.
    """
    report: dict[str, Any] = {
        "window": {"start": start, "end": end},
        "buy_and_hold": None,
        "equal_weight": None,
        "reference": None,
        "reference_name": None,
        "excess_return": None,
        "assets": 0,
        "error": None,
    }
    try:
        opened, closed = _moment(start), _moment(end)
        paths = _paths(settings.database_path, forward, symbols)
        if not paths:
            report["error"] = "no candles registered for this window"
            return report
        bars_by_symbol = {}
        for symbol, path in paths.items():
            try:
                bars = DataManager.load_csv(path)
            except (OSError, ValueError, KeyError):
                # One unreadable series is a gap in the comparison, not a
                # reason to withhold the comparison.
                continue
            if bars:
                bars_by_symbol[symbol] = bars
        if not bars_by_symbol:
            report["error"] = "no readable candles for this window"
            return report
        report["assets"] = len(bars_by_symbol)
        report.update(
            benchmark.evaluate(
                bars_by_symbol,
                opened,
                closed,
                strategy_return,
                commission_bps=commission_bps,
                slippage_bps=slippage_bps,
            )
        )
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return report


def describe(report: dict[str, Any]) -> str:
    """One line a person can read in the ledger without opening the JSON."""
    if not report or report.get("reference") is None:
        return f"benchmark unavailable ({(report or {}).get('error') or 'no data'})"
    even = report.get("equal_weight")
    hold = report.get("buy_and_hold")
    excess = report.get("excess_return")
    parts = [f"equal-weight {even:+.2%}" if even is not None else "equal-weight n/a"]
    if hold is not None:
        parts.append(f"BTC hold {hold:+.2%}")
    if excess is not None:
        parts.append(f"excess over {report.get('reference_name')} {excess:+.2%}")
    return " · ".join(parts) + f" ({report.get('assets', 0)} assets)"
