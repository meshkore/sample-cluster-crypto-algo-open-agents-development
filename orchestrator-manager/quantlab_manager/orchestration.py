"""The orchestrator: starts the backtester, runs a brain against it, records it.

The operator's shape, and the reason this file exists: **neither half works
alone**. A strategy with no tape decides nothing; a tape with no strategy is a
CSV reader. So one thing owns both -- it makes sure the backtester is listening,
hands the brain the wire, and writes the result down.

Nothing here needs a human. An agent that has just written a strategy calls

    from quantlab_manager.orchestration import Orchestrator

    lab = Orchestrator()
    result = lab.launch("my-idea", symbols=["BTCUSDT"], start="2022-01-01")

and gets back a persisted `backtest_id`. The backtester is started if it is not
already up, reused if it is, and left running for the next launch. That is the
whole autonomous path: write a brain, register it, launch it.

**The clock is pulled over the wire.** The orchestrator asks for a candle, hands
it to the brain, sends back whatever the brain decided, and asks for the next
one. The backtester never pushes and never waits on a timer, so a slow brain
costs only its own time.

**The run is read back before it is stored.** Having driven the session over
HTTP, the orchestrator does not hold the book -- it fetches orders, equity and
decisions from the backtester and persists those. Storing what it *believed* it
sent would make the record a transcript of its intentions rather than of what
actually filled.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

from quantlab_backtester.ledger import BacktestRun
from quantlab_backtester.models import utc_now
from quantlab_trading import brains

from .sessions import SessionStore, _pair_trades, open_database

DEFAULT_PORT = 8770


class BacktesterProcess:
    """Supervises the backtester service. Idempotent: reuses a healthy one."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
        database: Path | str | None = None,
        indicators: Path | str | None = None,
    ):
        self.host, self.port = host, port
        self.database = Path(database) if database else None
        self.indicators = Path(indicators) if indicators else None
        self.base_url = f"http://{host}:{port}"
        self.process: subprocess.Popen | None = None

    def healthy(self, timeout: float = 1.0) -> bool:
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/health", timeout=timeout
            ) as r:
                return json.loads(r.read()).get("status") == "ok"
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def ensure(self, wait_seconds: float = 15.0) -> str:
        """Start the service unless something is already answering on the port.

        Reusing a live server matters more than it looks: sessions live in the
        server's memory, so a second process on the same port would serve a
        different set of runs and ids would appear to vanish.
        """
        if self.healthy():
            return self.base_url

        command = [
            sys.executable,
            "-m",
            "quantlab_backtester.server",
            "--host",
            self.host,
            "--port",
            str(self.port),
        ]
        if self.database:
            command += ["--database", str(self.database)]
        if self.indicators:
            command += ["--indicators", str(self.indicators)]
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if self.healthy():
                return self.base_url
            if self.process.poll() is not None:
                output = (self.process.stdout.read() if self.process.stdout else "")[
                    :2000
                ]
                raise RuntimeError(f"the backtester exited on startup:\n{output}")
            time.sleep(0.15)
        self.stop()
        raise RuntimeError(
            f"the backtester did not answer on {self.base_url} within {wait_seconds}s"
        )

    def stop(self) -> None:
        """Only ever stops a server this object started."""
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        if self.process.stdout is not None:
            self.process.stdout.close()
        self.process = None


class _Wire:
    """The pull loop's half of the conversation. Small on purpose."""

    def __init__(self, base_url: str, timeout: float = 60.0):
        self.base_url, self.timeout = base_url.rstrip("/"), timeout

    def call(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"backtester {exc.code} on {method} {path}: "
                f"{exc.read().decode(errors='replace')[:400]}"
            ) from exc


class Orchestrator:
    """Launch strategies against the backtester, autonomously."""

    def __init__(
        self,
        database: Path | str,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
        store: SessionStore | None = None,
        indicators: Path | str | None = None,
    ):
        self.database = Path(database)
        # Backfilled panels, so a launch reads indicators instead of
        # recomputing seventy-nine columns per symbol per run.
        self.indicators = (
            Path(indicators)
            if indicators
            else self.database.parent.parent / "data" / "indicators"
        )
        self.service = BacktesterProcess(
            host, port, database=self.database, indicators=self.indicators
        )
        self.store = store or open_database(self.database)

    # -- what an agent calls ------------------------------------------------- #

    def strategies(self) -> list[dict[str, str]]:
        """Every registered brain. An agent lists this to see its own work."""
        return brains.available()

    def launch(
        self,
        strategy: str,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        capital: float = 100_000.0,
        commission_bps: float = 10.0,
        slippage_bps: float = 5.0,
        parameters: dict[str, Any] | None = None,
        label: str | None = None,
        submitted_by: str = "agent",
        candles: dict[str, list[dict]] | None = None,
        on_tick: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Run a registered brain end to end and return the persisted summary."""
        entry = brains.get(strategy)
        brain = entry.build(**(parameters or {}))
        base_url = self.service.ensure()
        wire = _Wire(base_url)

        config: dict[str, Any] = {
            "label": label or f"{entry.name}-{utc_now()[:19]}",
            "initial_capital": capital,
            "commission_bps": commission_bps,
            "slippage_bps": slippage_bps,
            "strategy_family": entry.name,
            "strategy_params": {
                key: value
                for key, value in vars(brain).items()
                if isinstance(value, (int, float, str, bool))
            },
            "window_start": start,
            "window_end": end,
        }
        if candles is not None:
            config["candles"] = candles
        elif symbols:
            config["symbols"] = symbols

        created = wire.call("POST", "/sessions", config)
        backtest_id = created["backtest_id"]

        run = BacktestRun(
            backtest_id=backtest_id,
            label=config["label"],
            created_at=utc_now(),
            initial_capital=capital,
            strategy_family=entry.name,
            strategy_params=config["strategy_params"],
            policy={},
            universe_size=len(candles or symbols or []),
            window_start=start,
            window_end=end,
        )
        self.store.open_run(run, submitted_by=submitted_by)

        try:
            stopped_for = self._pull(wire, backtest_id, brain, on_tick)
        except Exception as exc:  # noqa: BLE001 - a dead run must leave a record
            self.store.fail_run(backtest_id, f"{type(exc).__name__}: {exc}")
            raise
        return self._persist(wire, backtest_id, stopped_for)

    # -- the loop ------------------------------------------------------------ #

    def _pull(self, wire, backtest_id, brain, on_tick) -> str | None:
        """Ask, decide, answer, ask again. The whole conversation."""
        while True:
            tick = wire.call("GET", f"/sessions/{backtest_id}/next")
            if tick.get("done"):
                return None
            if on_tick is not None:
                on_tick(tick)
            decision = brain.decide(tick)
            reason = getattr(decision, "stop", None)
            if reason:
                wire.call("POST", f"/sessions/{backtest_id}/stop", {"reason": reason})
                return reason
            orders = getattr(decision, "orders", []) or []
            note = getattr(decision, "note", "") or ""
            if orders or note:
                wire.call(
                    "POST",
                    f"/sessions/{backtest_id}/orders",
                    {"orders": orders, "note": note},
                )

    def _persist(
        self, wire, backtest_id: str, stop_reason: str | None
    ) -> dict[str, Any]:
        """Read the book back from the backtester and store what actually filled."""
        summary = wire.call("GET", f"/sessions/{backtest_id}")
        orders = wire.call("GET", f"/sessions/{backtest_id}/orders")["orders"]
        equity = wire.call("GET", f"/sessions/{backtest_id}/equity")["equity"]
        decisions = wire.call("GET", f"/sessions/{backtest_id}/decisions")["decisions"]

        trades = _pair_trades(_OrdersOnly(orders))
        wins = sum(1 for trade in trades if trade["pnl"] > 0)
        exposures = [
            max(0.0, 1 - point["cash"] / point["equity"])
            if point["equity"] > 0
            else 0.0
            for point in equity
        ]
        initial = summary["initial_capital"]

        with self.store._connect() as connection:
            connection.execute(
                """UPDATE backtest_runs SET status=?, final_equity=?, return_pct=?,
                   max_drawdown=?, capital_drawdown=?, average_exposure=?,
                   peak_exposure=?, time_in_market=?, trades=?, wins=?, losses=?,
                   win_rate=?, aborted=?, abort_reason=?, last_active_timestamp=?,
                   updated_at=? WHERE backtest_id=?""",
                (
                    summary["status"],
                    summary["final_equity"],
                    summary["return_pct"],
                    summary["max_drawdown"],
                    max(
                        (max(0.0, 1 - p["equity"] / initial) for p in equity),
                        default=0.0,
                    ),
                    sum(exposures) / len(exposures) if exposures else 0.0,
                    max(exposures) if exposures else 0.0,
                    sum(1 for e in exposures if e > 0) / len(exposures)
                    if exposures
                    else 0.0,
                    len(trades),
                    wins,
                    len(trades) - wins,
                    wins / len(trades) if trades else 0.0,
                    int(bool(stop_reason)),
                    stop_reason or summary.get("stop_reason"),
                    next(
                        (p["timestamp"] for p in reversed(equity) if p.get("active")),
                        None,
                    ),
                    utc_now(),
                    backtest_id,
                ),
            )
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
                """INSERT INTO backtest_orders (backtest_id, sequence, timestamp, symbol,
                   side, quantity, price, notional, fee, reason, cash_after)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        backtest_id,
                        o["sequence"],
                        o["timestamp"],
                        o["symbol"],
                        o["side"],
                        o["quantity"],
                        o["price"],
                        o["notional"],
                        o["fee"],
                        o["reason"],
                        o["cash_after"],
                    )
                    for o in orders
                ],
            )
            connection.executemany(
                """INSERT INTO backtest_trades (backtest_id, symbol, sequence, entry_time,
                   exit_time, entry_price, exit_price, duration_seconds, invested_capital,
                   pnl, pnl_pct, exit_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                        p["timestamp"],
                        p["equity"],
                        p["cash"],
                        p["open_positions"],
                        int(bool(p["active"])),
                        None,
                    )
                    for p in equity
                ],
            )
            connection.executemany(
                """INSERT INTO backtest_decisions (backtest_id, sequence, timestamp,
                   note, orders_json, rejected_json) VALUES (?,?,?,?,?,?)""",
                [
                    (
                        backtest_id,
                        d["sequence"],
                        d["timestamp"],
                        d.get("note", ""),
                        json.dumps(d.get("orders", []), default=str),
                        json.dumps(d.get("rejected", []), default=str),
                    )
                    for d in decisions
                ],
            )
        return self.store.run(backtest_id)

    def close(self) -> None:
        self.service.stop()

    def __enter__(self) -> Orchestrator:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class _OrdersOnly:
    """Adapts wire-shaped order dicts to what `_pair_trades` reads.

    Trade pairing is written once, against the ledger. Rewriting it for the HTTP
    path would give the two routes two chances to disagree about what a trade
    is, and they would eventually take them.
    """

    def __init__(self, orders: list[dict[str, Any]]):
        from datetime import datetime
        from types import SimpleNamespace

        self.orders = [
            SimpleNamespace(
                sequence=o["sequence"],
                timestamp=datetime.fromisoformat(o["timestamp"]),
                symbol=o["symbol"],
                side=o["side"],
                quantity=o["quantity"],
                price=o["price"],
                notional=o["notional"],
                fee=o["fee"],
                reason=o["reason"],
                cash_after=o["cash_after"],
            )
            for o in orders
        ]
