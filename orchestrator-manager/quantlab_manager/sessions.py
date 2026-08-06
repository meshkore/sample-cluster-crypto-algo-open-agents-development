"""Driving a brain against a session and persisting the result under its id.

This is the piece that connects the three folders end to end: the backtester
serves the tape, the trading system decides, and the lab writes it all down
against one `backtest_id` so a visualiser has something to read.

Runs in-process by default. The HTTP service exists so that anyone -- another
language, another agent, a contributor on their own machine -- can drive a run
without importing Python; this path is the same session object driven directly,
for when the lab is already in the process and a network hop would buy nothing.

The two produce identical records, which is the point: a contributor's run over
HTTP and the lab's own run land in the same tables with the same shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import json
import sqlite3

from quantlab_backtester.ledger import AccountLedger, BacktestRun
from quantlab_backtester.models import Bar, utc_now
from quantlab_backtester.session import BacktestSession, OrderRequest

from .backtests import BacktestStore


def _pair_trades(ledger: AccountLedger) -> list[dict[str, Any]]:
    """Round trips reconstructed from the order log.

    The session records fills, not trades: a trade is a pairing, and pairing is
    an interpretation the instrument has no reason to impose. Doing it here
    keeps the backtester free of the concept while the lab still gets the
    per-trade view every report is built on. Positions still open at the end are
    deliberately absent -- an unclosed position has no realised PnL, and
    inventing one is how a run flatters itself.
    """
    open_buys: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    trades: list[dict[str, Any]] = []
    for order in ledger.orders:
        if order.side == "BUY":
            open_buys[order.symbol] = {
                "entry_time": order.timestamp,
                "entry_price": order.price,
                "invested": order.notional,
            }
            continue
        entry = open_buys.pop(order.symbol, None)
        if entry is None:
            continue
        counts[order.symbol] = counts.get(order.symbol, 0) + 1
        invested = entry["invested"]
        pnl = order.notional - order.fee - invested
        trades.append(
            {
                "symbol": order.symbol,
                "sequence": counts[order.symbol],
                "entry_time": entry["entry_time"].isoformat(),
                "exit_time": order.timestamp.isoformat(),
                "entry_price": entry["entry_price"],
                "exit_price": order.price,
                "duration_seconds": (
                    order.timestamp - entry["entry_time"]
                ).total_seconds(),
                "invested_capital": invested,
                "pnl": pnl,
                "pnl_pct": pnl / invested if invested else 0.0,
                "exit_reason": order.reason or "EXIT",
            }
        )
    return trades


class SessionStore(BacktestStore):
    """A `BacktestStore` that can also persist a live session directly."""

    def complete_session(self, session: BacktestSession) -> dict[str, Any]:
        summary = session.summary()
        trades = _pair_trades(session.ledger)
        wins = sum(1 for trade in trades if trade["pnl"] > 0)

        peak = session.ledger.initial_capital
        capital_drawdown = 0.0
        exposures = []
        for point in session.equity_curve:
            peak = max(peak, point["equity"])
            capital_drawdown = max(
                capital_drawdown,
                max(0.0, 1 - point["equity"] / session.ledger.initial_capital),
            )
            equity = point["equity"]
            exposures.append(
                max(0.0, 1 - point["cash"] / equity) if equity > 0 else 0.0
            )

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE backtest_runs SET
                    status=?, final_equity=?, return_pct=?, max_drawdown=?,
                    capital_drawdown=?, average_exposure=?, peak_exposure=?,
                    time_in_market=?, trades=?, wins=?, losses=?, win_rate=?,
                    aborted=?, abort_reason=?, last_active_timestamp=?, updated_at=?
                WHERE backtest_id=?
                """,
                (
                    summary["status"],
                    summary["final_equity"],
                    summary["return_pct"],
                    summary["max_drawdown"],
                    capital_drawdown,
                    sum(exposures) / len(exposures) if exposures else 0.0,
                    max(exposures) if exposures else 0.0,
                    (
                        sum(1 for e in exposures if e > 0) / len(exposures)
                        if exposures
                        else 0.0
                    ),
                    len(trades),
                    wins,
                    len(trades) - wins,
                    wins / len(trades) if trades else 0.0,
                    int(summary["status"] == "stopped"),
                    summary["stop_reason"],
                    next(
                        (
                            point["timestamp"]
                            for point in reversed(session.equity_curve)
                            if point.get("active")
                        ),
                        None,
                    ),
                    utc_now(),
                    summary["backtest_id"],
                ),
            )
            backtest_id = summary["backtest_id"]
            for table in (
                "backtest_orders",
                "backtest_trades",
                "backtest_equity",
                "backtest_decisions",
            ):
                connection.execute(
                    f"DELETE FROM {table} WHERE backtest_id=?", (backtest_id,)
                )
            connection.executemany(
                """INSERT INTO backtest_orders (backtest_id, sequence, timestamp,
                   symbol, side, quantity, price, notional, fee, reason, cash_after)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        backtest_id,
                        o.sequence,
                        o.timestamp.isoformat(),
                        o.symbol,
                        o.side,
                        o.quantity,
                        o.price,
                        o.notional,
                        o.fee,
                        o.reason,
                        o.cash_after,
                    )
                    for o in session.ledger.orders
                ],
            )
            connection.executemany(
                """INSERT INTO backtest_trades (backtest_id, symbol, sequence,
                   entry_time, exit_time, entry_price, exit_price, duration_seconds,
                   invested_capital, pnl, pnl_pct, exit_reason)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        backtest_id,
                        t["symbol"],
                        t["sequence"],
                        t["entry_time"],
                        t["exit_time"],
                        t["entry_price"],
                        t["exit_price"],
                        t["duration_seconds"],
                        t["invested_capital"],
                        t["pnl"],
                        t["pnl_pct"],
                        t["exit_reason"],
                    )
                    for t in trades
                ],
            )
            connection.executemany(
                """INSERT INTO backtest_equity (backtest_id, timestamp, equity, cash,
                   open_positions, active, capital_drawdown) VALUES (?,?,?,?,?,?,?)""",
                [
                    (
                        backtest_id,
                        point["timestamp"],
                        point["equity"],
                        point["cash"],
                        point["open_positions"],
                        int(bool(point["active"])),
                        None,
                    )
                    for point in session.equity_curve
                ],
            )
            # The narration the visualiser shows: what the brain did on each bar
            # and, when it did nothing, that it decided so on purpose. A blank
            # chart between two trades is otherwise indistinguishable from a
            # strategy that crashed.
            connection.executemany(
                """INSERT INTO backtest_decisions (backtest_id, sequence, timestamp,
                   note, orders_json, rejected_json) VALUES (?,?,?,?,?,?)""",
                [
                    (
                        backtest_id,
                        d["sequence"],
                        d["timestamp"],
                        d["note"],
                        json.dumps(d["orders"], default=str),
                        json.dumps(d["rejected"], default=str),
                    )
                    for d in session.decisions
                ],
            )
        return summary

    def decisions(self, backtest_id: str, limit: int = 20_000) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM backtest_decisions WHERE backtest_id=? "
                "ORDER BY sequence LIMIT ?",
                (backtest_id, limit),
            ).fetchall()
        out = []
        for row in rows:
            record = dict(row)
            record["orders"] = json.loads(record.pop("orders_json"))
            record["rejected"] = json.loads(record.pop("rejected_json"))
            out.append(record)
        return out


def run_session(
    brain: Any,
    run: BacktestRun,
    bars_by_symbol: dict[str, list[Bar]],
    store: SessionStore | None = None,
    costs: Any = None,
    submitted_by: str = "lab",
    on_tick: Callable[[dict[str, Any]], None] | None = None,
    **session_kwargs,
) -> dict[str, Any]:
    """Drive `brain` over the tape and persist everything under `run.backtest_id`."""
    kwargs = dict(session_kwargs)
    if costs is not None:
        kwargs["costs"] = costs
    session = BacktestSession(run=run, bars_by_symbol=bars_by_symbol, **kwargs)

    if store is not None:
        store.open_run(run, submitted_by=submitted_by)
    try:
        while True:
            tick = session.next_tick()
            if tick.get("done"):
                break
            if on_tick is not None:
                on_tick(tick)
            decision = brain.decide(tick)
            if getattr(decision, "stop", None):
                session.stop(decision.stop)
                break
            orders = [OrderRequest.from_payload(item) for item in decision.orders]
            if orders or decision.note:
                session.submit(orders, note=decision.note)
    except Exception as exc:  # noqa: BLE001 - a failed run must leave a record
        if store is not None:
            store.fail_run(run.backtest_id, f"{type(exc).__name__}: {exc}")
        raise
    if store is not None:
        return store.complete_session(session)
    return session.summary()


def open_database(path: Path | str) -> SessionStore:
    """A store on a database that already has the schema, or a fresh one."""
    from .memory import SCHEMA

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.close()
    return SessionStore(path)
