"""Persisting a backtest under its own id, so many can coexist.

The backtester owns the live book; this owns the durable record. That division
is not cosmetic -- the layering contract forbids the instrument from importing
the lab, so the engine cannot write to a database even if it wanted to, and the
book it produces stays a plain object anyone can inspect without a database at
all.

Everything here hangs off `backtest_id`. Before this, a run's records were keyed
by `strategy_number`, which allowed exactly one run per strategy and silently
overwrote the previous one -- fine for a single-champion pipeline, useless the
moment a contributor wants to launch three variants and compare them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sqlite3

from quantlab_backtester.engine import PortfolioEvaluation
from quantlab_backtester.ledger import AccountLedger, BacktestRun

from quantlab_backtester.models import utc_now


class BacktestStore:
    """Reads and writes `backtest_*` tables. One connection, one run at a time."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def open_run(self, run: BacktestRun, submitted_by: str = "unknown") -> str:
        """Register a run before it starts, so a crash still leaves a trace.

        Status moves running -> complete (or failed). A row that stays 'running'
        is itself information: something died, and the operator can see which
        configuration it was.
        """
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO backtest_runs (
                    backtest_id, label, created_at, status, submitted_by,
                    strategy_family, strategy_params_json, policy_json,
                    universe_size, window_start, window_end, initial_capital,
                    updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(backtest_id) DO UPDATE SET
                    status='running', label=excluded.label,
                    updated_at=excluded.updated_at
                """,
                (
                    run.backtest_id,
                    run.label,
                    run.created_at,
                    "running",
                    submitted_by,
                    run.strategy_family,
                    json.dumps(run.strategy_params, sort_keys=True),
                    json.dumps(run.policy, sort_keys=True),
                    run.universe_size,
                    run.window_start,
                    run.window_end,
                    run.initial_capital,
                    utc_now(),
                ),
            )
        return run.backtest_id

    def complete_run(
        self,
        backtest_id: str,
        evaluation: PortfolioEvaluation,
        ledger: AccountLedger | None = None,
    ) -> None:
        total = evaluation.wins + evaluation.losses
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE backtest_runs SET
                    status='complete', final_equity=?, return_pct=?,
                    max_drawdown=?, capital_drawdown=?, average_exposure=?,
                    peak_exposure=?, time_in_market=?, trades=?, wins=?,
                    losses=?, win_rate=?, aborted=?, abort_reason=?,
                    last_active_timestamp=?, updated_at=?
                WHERE backtest_id=?
                """,
                (
                    evaluation.final_equity,
                    evaluation.return_pct,
                    evaluation.max_drawdown,
                    evaluation.capital_drawdown,
                    evaluation.average_exposure,
                    evaluation.peak_exposure,
                    evaluation.time_in_market,
                    len(evaluation.trades),
                    evaluation.wins,
                    evaluation.losses,
                    evaluation.wins / total if total else 0.0,
                    int(evaluation.aborted),
                    evaluation.abort_reason,
                    evaluation.last_active_timestamp,
                    utc_now(),
                    backtest_id,
                ),
            )
            # Rewritten wholesale rather than appended: re-running an id must
            # replace its records, not interleave them with the previous run's.
            for table in ("backtest_orders", "backtest_trades", "backtest_equity"):
                connection.execute(
                    f"DELETE FROM {table} WHERE backtest_id=?", (backtest_id,)
                )

            if ledger is not None:
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
                        for o in ledger.orders
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
                        t.symbol,
                        t.sequence,
                        t.entry_time.isoformat(),
                        t.exit_time.isoformat(),
                        t.entry_price,
                        t.exit_price,
                        t.duration_seconds,
                        t.invested_capital,
                        t.pnl,
                        t.pnl_pct,
                        t.exit_reason,
                    )
                    for t in evaluation.trades
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
                        point.get("open_positions", 0),
                        int(bool(point.get("active"))),
                        point.get("capital_drawdown"),
                    )
                    for point in evaluation.equity_curve
                ],
            )

    def fail_run(self, backtest_id: str, reason: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE backtest_runs SET status='failed', abort_reason=?, updated_at=? "
                "WHERE backtest_id=?",
                (reason[:500], utc_now(), backtest_id),
            )

    # -- reads ---------------------------------------------------------------- #

    def runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM backtest_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def run(self, backtest_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM backtest_runs WHERE backtest_id=?", (backtest_id,)
            ).fetchone()
        return dict(row) if row else None

    def orders(self, backtest_id: str, limit: int = 5000) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM backtest_orders WHERE backtest_id=? "
                "ORDER BY sequence LIMIT ?",
                (backtest_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def equity(self, backtest_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT timestamp, equity, cash, open_positions, active, "
                "capital_drawdown FROM backtest_equity WHERE backtest_id=? "
                "ORDER BY timestamp",
                (backtest_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def trades(self, backtest_id: str, limit: int = 5000) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM backtest_trades WHERE backtest_id=? "
                "ORDER BY exit_time LIMIT ?",
                (backtest_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]
