"""What the monitor reads: one JSON file, all figures.

The operator asked for the live area to show *"the asset's price, the price of the
portfolio, the list of orders we have executed with their profits"* - so this publishes
exactly that, next to the two facts that make it auditable: which engine version decided,
and how fresh the channels behind the decision are.

It is deliberately a snapshot of the book rather than a stream of events. The ledger is
the event log and is append-only; this file is what is TRUE right now, rewritten every
bar, so a reader that misses a tick is never left with a stale half-state.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from . import config
from .book import LiveBook, read_ledger


def _equity_point(book: LiveBook) -> dict[str, Any]:
    return {"at": datetime.now(timezone.utc).isoformat(),
            "equity": round(book.equity, 2), "cash": round(book.cash, 2),
            "invested": round(book.invested, 2), "dd": round(book.drawdown, 5)}


def append_equity(book: LiveBook) -> None:
    """One point per bar. The curve the live panel draws, and the only history of it."""
    path = config.STATE_DIR / "equity.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_equity_point(book)) + "\n")


def equity_curve(limit: int = 600) -> list[dict[str, Any]]:
    path = config.STATE_DIR / "equity.jsonl"
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    if len(rows) <= limit:
        return rows
    step = len(rows) / limit
    return [rows[int(i * step)] for i in range(limit)] + rows[-1:]


def publish(*, book: LiveBook, package, tick: dict[str, Any], decision, fills: list,
            quotes: dict, halted: str | None = None, dry_run: bool = False,
            overlays_at: datetime | None = None,
            signals_at: datetime | None = None) -> dict[str, Any]:
    append_equity(book)
    trades = [row for row in read_ledger(limit=400) if row.get("kind") == "FILL"]
    closed = [row for row in trades if row.get("realised") is not None]
    wins = [row for row in closed if row["realised"] > 0]
    payload = {
        "at": datetime.now(timezone.utc).isoformat(),
        "mode": "paper" + (" (dry run)" if dry_run else ""),
        "halted": halted,
        "cutover": config.CUTOVER.isoformat(),
        "trading_since": book.opened_at.isoformat(),
        "engine": {
            "version": package.version,
            "system": package.manifest.get("system"),
            "provenance": package.manifest.get("provenance"),
            "band": package.band,
            "risk": package.risk,
            "metrics": package.manifest.get("metrics", {}),
            "signals_at": signals_at.isoformat() if signals_at else None,
            "overlays_at": overlays_at.isoformat() if overlays_at else None,
        },
        "account": {
            "initial_capital": book.initial_capital,
            "equity": round(book.equity, 2),
            "cash": round(book.cash, 2),
            "invested": round(book.invested, 2),
            "exposure": round(book.exposure, 4),
            "return_pct": round(book.return_pct, 6),
            "drawdown": round(book.drawdown, 5),
            "high_water": round(book.high_water, 2),
            "realised": round(book.realised, 2),
            "fees_paid": round(book.fees_paid, 2),
            "trades_closed": book.trades_closed,
            "win_rate": round(len(wins) / len(closed), 4) if closed else None,
        },
        "positions": [
            {"symbol": symbol, "quantity": p.quantity, "entry_price": p.entry_price,
             "entry_time": p.entry_time.isoformat(), "price": book.price_of(symbol),
             "value": round(p.quantity * book.price_of(symbol), 2),
             "unrealised_pct": round(book.unrealised_pct(symbol), 5)}
            for symbol, p in sorted(book.positions.items())
        ],
        "prices": [
            {"symbol": symbol, "bid": q.bid, "ask": q.ask, "mid": round(q.mid, 8),
             "spread_bps": round(q.spread_bps, 3)}
            for symbol, q in sorted(quotes.items())
        ],
        "orders": list(reversed(trades[-60:])),
        "last_bar": tick.get("timestamp"),
        "last_note": getattr(decision, "note", "")[:400],
        "orders_this_bar": len(getattr(decision, "orders", []) or []),
        "fills_this_bar": [f.to_json() for f in fills],
        "equity_curve": equity_curve(),
    }
    path = config.STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)
    return payload


def read() -> dict[str, Any] | None:
    """What the monitor calls. None when the trader has never published."""
    if not config.STATE_PATH.is_file():
        return None
    try:
        return json.loads(config.STATE_PATH.read_text(encoding="utf-8"))
    except ValueError:
        return None
