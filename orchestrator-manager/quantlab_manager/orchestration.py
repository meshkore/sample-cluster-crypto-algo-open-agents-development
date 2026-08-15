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

from dataclasses import asdict, is_dataclass
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

from . import quality
from .backtests import describe
from .sessions import SessionStore, _pair_trades, open_database, regime_timeline

DEFAULT_PORT = 8770

# How often a watched run copies its book out of the backtester. A forward run
# over 55 symbols takes about half a minute, so this is roughly forty frames --
# enough for the curve to draw itself rather than appear finished.
PROGRESS_SECONDS = 0.75
# The edge is not on this machine. Each snapshot is a whole payload over the
# network, so it gets one every few seconds rather than every frame.
PROGRESS_PUBLISH_SECONDS = 5.0


def _describe(brain: Any) -> dict[str, Any]:
    """Everything that makes this brain the brain it is.

    A brain may publish `parameters()`; otherwise its scalar attributes are
    used. The distinction matters because `backtest_id` is DERIVED from this
    dict, so anything left out of it is a configuration two different runs can
    disagree on while sharing an id -- and the second silently overwrites the
    first.
    """
    describe = getattr(brain, "parameters", None)
    if callable(describe):
        described = describe()
        if isinstance(described, dict):
            return {
                key: value
                for key, value in described.items()
                if isinstance(value, (int, float, str, bool, type(None)))
            }
    return {
        key: value
        for key, value in vars(brain).items()
        if isinstance(value, (int, float, str, bool))
    }


def _policy_of(brain: Any) -> dict[str, Any]:
    """The brain's money management, as a fingerprint input.

    This used to be `{}`, unconditionally. Sizing, stops and the drawdown
    mandate are the trading system's hypothesis -- the operator's own words --
    and leaving them out of the identity cost a result the day it was written:
    the same four-module system run once on a ratchet drawdown basis and once
    on a peak basis produced `30af15cbe2f17cf2` twice, and the second run
    overwrote the first with no trace that two different things had been tried.
    """
    policy = getattr(brain, "policy", None)
    if policy is None:
        return {}
    if is_dataclass(policy) and not isinstance(policy, type):
        return asdict(policy)
    if isinstance(policy, dict):
        return dict(policy)
    return {}


class BacktesterProcess:
    """Supervises the backtester service. Idempotent: reuses a healthy one."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
        database: Path | str | None = None,
        indicators: Path | str | None = None,
        mirror_url: str | None = None,
        mirror_token: str | None = None,
        forward: bool = False,
    ):
        self.host, self.port = host, port
        self.database = Path(database) if database else None
        self.indicators = Path(indicators) if indicators else None
        # Whether this laboratory is allowed to see past 2025-12-31 today.
        self.forward = forward
        self.base_url = f"http://{host}:{port}"
        self.process: subprocess.Popen | None = None

    def health(self, timeout: float = 1.0) -> dict[str, Any] | None:
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/health", timeout=timeout
            ) as r:
                payload = json.loads(r.read())
                return payload if payload.get("status") == "ok" else None
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def healthy(self, timeout: float = 1.0) -> bool:
        return self.health(timeout) is not None

    def ensure(self, wait_seconds: float = 15.0) -> str:
        """Start the service unless something is already answering on the port.

        Reusing a live server matters more than it looks: sessions live in the
        server's memory, so a second process on the same port would serve a
        different set of runs and ids would appear to vanish.

        The one thing it refuses to reuse is a server serving a different tape.
        A forward run against a research-only process gets a tape that simply
        stops at 2025-12-31, and the missing year reads as "the strategy took no
        trades in 2026" rather than as a misconfiguration.
        """
        health = self.health()
        if health is not None:
            if self.forward and not health.get("forward"):
                raise RuntimeError(
                    f"a backtester is already running on {self.base_url} without "
                    "the forward window, and this launch asked for it. Stop it "
                    "and let the orchestrator start one with --forward."
                )
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
        if self.forward:
            command += ["--forward"]
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

    # Creating a session is the one call whose cost scales with the universe:
    # the server loads every symbol's candles and its indicator panel before it
    # can serve tick zero. Cold across 386 symbols that is ~37s, and it was
    # measured against a 60s ceiling that fitted comfortably when the loop
    # traded 55. Iteration 69 opened the 2026 window, spent thirty minutes
    # fitting, and then lost the whole iteration to `TimeoutError: timed out`
    # on POST /sessions -- no forward run, no ledger record, and the loop did
    # not even count it as a failure. Every other call answers from memory in
    # milliseconds, so only this one needs the room.
    SESSION_TIMEOUT = 600.0

    def __init__(self, base_url: str, timeout: float = 60.0):
        self.base_url, self.timeout = base_url.rstrip("/"), timeout

    def call(self, method: str, path: str, payload: dict | None = None) -> dict:
        timeout = (
            self.SESSION_TIMEOUT
            if method == "POST" and path == "/sessions"
            else self.timeout
        )
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
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
        mirror_url: str | None = None,
        mirror_token: str | None = None,
        forward: bool = False,
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
            host,
            port,
            database=self.database,
            indicators=self.indicators,
            forward=forward,
        )
        self.store = store or open_database(self.database)
        # Where finished runs are published so the deployed page has an
        # archive rather than only whatever fitted in the last snapshot.
        self.mirror_url = (mirror_url or "").rstrip("/") or None
        self.mirror_token = mirror_token
        # Set by every publish attempt. Readable, because "it published fine"
        # was reported by silence once and the silence was a 403.
        self.last_publish_error: str | None = None

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
        progress: bool = False,
    ) -> dict[str, Any]:
        """Run a registered brain end to end and return the persisted summary.

        `progress` makes the run visible while it happens. It costs a snapshot
        of the book every fraction of a second, so it belongs on runs a person
        might watch -- not inside a search, where six hundred of them would
        write far more than they would ever be read.
        """
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
            "strategy_params": _describe(brain),
            "policy": _policy_of(brain),
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
            policy=config["policy"],
            universe_size=len(candles or symbols or []),
            window_start=start,
            window_end=end,
        )
        self.store.open_run(run, submitted_by=submitted_by)

        hook = on_tick
        if progress:
            beat = self._progress_hook(wire, backtest_id)
            hook = (lambda tick: (on_tick(tick), beat(tick))) if on_tick else beat

        try:
            stopped_for = self._pull(wire, backtest_id, brain, hook)
        except Exception as exc:  # noqa: BLE001 - a dead run must leave a record
            self.store.fail_run(backtest_id, f"{type(exc).__name__}: {exc}")
            raise
        return self._persist(wire, backtest_id, stopped_for)

    def evaluate(
        self,
        strategy: str,
        symbols: list[str],
        start: str,
        end: str,
        parameters: dict[str, Any] | None = None,
        capital: float = 100_000.0,
        commission_bps: float = 10.0,
        slippage_bps: float = 5.0,
    ) -> dict[str, Any]:
        """Run a configuration and return its summary WITHOUT recording it.

        A parameter search evaluates hundreds of configurations that are not
        results -- they are the arithmetic that produces one. Persisting each
        would bury the four runs that mean something under six hundred that do
        not, and the ledger would stop being readable by a person.

        The tape, the fills and the costs are identical to `launch`; only the
        bookkeeping is skipped. What comes back is what the backtester says
        happened, not what the caller believed it sent.
        """
        wire = _Wire(self.service.ensure())
        config = {
            "label": f"search-{strategy}",
            "initial_capital": capital,
            "commission_bps": commission_bps,
            "slippage_bps": slippage_bps,
            "symbols": symbols,
            "window_start": start,
            "window_end": end,
        }
        brain = brains.get(strategy).build(**(parameters or {}))
        backtest_id = wire.call("POST", "/sessions", config)["backtest_id"]
        stopped = self._pull(wire, backtest_id, brain, None, quiet=True)
        summary = wire.call("GET", f"/sessions/{backtest_id}")
        summary["stop_reason"] = stopped or summary.get("stop_reason")
        return summary

    # -- the loop ------------------------------------------------------------ #

    def _pull(
        self, wire, backtest_id, brain, on_tick, quiet: bool = False
    ) -> str | None:
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
            # A note on every bar is one HTTP round trip per bar. That is the
            # right trade for a recorded run -- "why did it do nothing here" is
            # the question the monitor exists to answer -- and the wrong one
            # inside a search, where it triples the traffic of six hundred runs
            # nobody will read.
            note = "" if quiet else (getattr(decision, "note", "") or "")
            if orders or note:
                wire.call(
                    "POST",
                    f"/sessions/{backtest_id}/orders",
                    {"orders": orders, "note": note},
                )

    def _progress_hook(self, wire, backtest_id: str):
        """A run that reports itself while it is still running.

        Everything a run produces used to land in one write at the end, so a
        backtest in flight was a row saying `running` with nothing behind it --
        the monitor could name it and show nothing. The book already exists in
        the backtester; this copies it out on a clock so the curve draws itself
        and the orders arrive as they fill.

        Never allowed to raise. A snapshot is an observation of the run, and an
        observation that can kill what it observes is worse than no snapshot.
        """
        state = {"stored": 0.0, "published": 0.0}

        def beat(_tick: dict[str, Any]) -> None:
            now = time.monotonic()
            if now - state["stored"] < PROGRESS_SECONDS:
                return
            state["stored"] = now
            # The edge gets far fewer: each one is a whole payload over the
            # network, and a run lasts half a minute.
            publish = now - state["published"] >= PROGRESS_PUBLISH_SECONDS
            if publish:
                state["published"] = now
            try:
                self._write(wire, backtest_id, None, final=False, publish=publish)
            except Exception:  # noqa: BLE001 - see the docstring
                pass

        return beat

    def _persist(
        self, wire, backtest_id: str, stop_reason: str | None
    ) -> dict[str, Any]:
        """Read the book back from the backtester and store what actually filled."""
        return self._write(wire, backtest_id, stop_reason, final=True, publish=True)

    def _write(
        self,
        wire,
        backtest_id: str,
        stop_reason: str | None,
        final: bool = True,
        publish: bool = True,
    ) -> dict[str, Any]:
        """One writer for both the snapshot and the final record.

        Two writers would drift, and the one that drifts is always the one
        nobody reads until it matters. The only difference between them is the
        status the row is left in: a snapshot is still `running`.
        """
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
                    summary["status"] if final else "running",
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
        stored = self.store.run(backtest_id)
        if publish:
            self._publish(backtest_id, stored, equity, orders, decisions, trades)
        return stored

    @staticmethod
    def _trade_from(run: Any) -> str | None:
        """When this run was allowed to START trading, off its own genome.

        The same rule the public page applies, for the same reason: a run's
        window start is when its tape begins, not when it was allowed to act, and
        reading one as the other is how a 2026 run's four-month warm-up got
        counted as part of its result.
        """
        try:
            params = json.loads(dict(run).get("strategy_params_json") or "{}")
        except (TypeError, ValueError):
            return None
        value = params.get("trade_from")
        return str(value) if value else None

    def _publish(
        self, backtest_id, run, equity, orders, decisions, trades, regimes=None
    ) -> None:
        """Push a finished run to the public mirror, best effort.

        Publication must never be able to fail a backtest. The evidence is
        already in the local database by the time this runs; the edge copy is a
        convenience for readers, and a network blip is not a research event.
        """
        if not run:
            return
        graded = quality.from_curve(equity, self._trade_from(run)).document()
        # Inside the run row as well as beside it. The edge builds its sidebar
        # index out of `run` alone and nothing else survives into it, so a
        # verdict published only at the top level is a verdict the board cannot
        # rank on -- which is the whole point of computing it.
        row = {**describe(dict(run)), "quality": graded}
        self._to_mirror(
            f"/api/backtests/{backtest_id}",
            {
                # `era` and `pair_key` go over the wire because the edge cannot
                # derive them: it holds JSON blobs, not a database, and the one
                # time it tried to reimplement "is this run in the forward
                # window" it got the answer wrong and crowned a training result
                # as the best of 2026. Deriving it once, here, means the edge
                # has nothing left to get wrong.
                "run": row,
                # How good this curve is for someone who did NOT buy on the first
                # day: growth, the return of whoever bought at the peak, maximum
                # drawdown, time spent underwater, the longest run of losing
                # months, and whether the growth is a line or a spike.
                #
                # Computed HERE, in the one function every publication passes
                # through -- the loop, the operator's publisher, and the backfill
                # all reach the mirror this way. Computing it at the call sites
                # instead would mean three copies of the definition and a fourth
                # publisher, written later, that quietly ships runs with no
                # verdict on them.
                "quality": graded,
                "equity": equity,
                "orders": orders[:2000],
                "trades": trades[:2000],
                "decisions": [d for d in decisions if d.get("orders")][:2000],
                # The detected major trend, as change points. The line above
                # keeps only decisions that TRADED, which is the right filter
                # for an orders table and the wrong one for a regime: the
                # public chart would be grey through every stretch the strategy
                # stood still, which is most of a bear market.
                # `regimes` may be supplied by a caller that knows better --
                # the global cycle is a property of the MARKET and is the same
                # series under every run, so the backfill dates it once from the
                # candles and hands it to all of them. Runs recorded before the
                # cycle existed cannot recover it from their own notes.
                "regimes": regimes
                if regimes is not None
                else regime_timeline(decisions),
            },
        )

    def publish_activity(self, document: dict) -> None:
        """Push the loop's heartbeat to the edge.

        The archive tells a visitor what finished; without this they cannot tell
        a laboratory that is thinking hard from one that died at midnight.
        """
        self._to_mirror("/api/loop", document)

    def publish_journal(self, identifier: str, events: list) -> None:
        """Push one hypothesis's event journal to the edge.

        This is what the live diagram reads in public. On this machine the page
        holds a WebSocket the daemon feeds by tailing the file; the edge
        receives pushed snapshots instead, because nothing on the internet may
        open a connection to this host. The events and their order are the same
        either way, so the page cannot tell which transport it got.

        Sent whole rather than as a delta: the file is small, last-write-wins is
        the only merge rule that cannot reorder a record, and a dropped delta
        would leave the public journal permanently missing a stage.
        """
        if not identifier or not events:
            return
        self._to_mirror(f"/api/journal/{identifier}", {"events": events})

    def _to_mirror(self, path: str, body: dict) -> None:
        if not self.mirror_url or not self.mirror_token:
            return
        request = urllib.request.Request(
            f"{self.mirror_url}{path}",
            data=json.dumps(body, default=str).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.mirror_token}",
                # Cloudflare's browser-integrity check answers the default
                # `Python-urllib/3.x` agent with a 403 and error code 1010, and
                # publication swallows failures by design -- so without this the
                # archive silently never reaches the edge while every run
                # reports success.
                "User-Agent": "QuantLab-backtest-publisher/1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20):
                pass
        except (urllib.error.URLError, OSError) as exc:
            # Still best effort -- a network blip is not a research event and the
            # evidence is already in the local database. But silence cost an
            # afternoon once: eight runs reported published and none arrived,
            # because a 403 is an HTTPError and HTTPError is a URLError.
            self.last_publish_error = f"{type(exc).__name__}: {exc}"
            return
        self.last_publish_error = None

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
