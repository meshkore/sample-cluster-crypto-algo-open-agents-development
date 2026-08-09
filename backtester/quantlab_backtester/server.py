"""The backtester as a service: a port, a start button, and a pulled tape.

Anyone with a code editor should be able to start this and drive it. Stdlib
only, no framework, no dependency to audit.

    python3 -m quantlab_backtester.server --port 8770

The protocol is HTTP/JSON, which is MeshKore's mandatory baseline, so any agent
or language can drive a run without a client library:

    POST /sessions              create a run from a config, returns backtest_id
    GET  /sessions              list runs
    GET  /sessions/{id}         summary
    GET  /sessions/{id}/next    ADVANCE one bar; returns candle + indicators + account
    POST /sessions/{id}/orders  queue orders against the tick just served
    POST /sessions/{id}/stop    end the run (the trading system's decision)
    GET  /sessions/{id}/events  Server-Sent Events for the visualiser
    GET  /health

Two properties are worth stating because they are the design, not details.

**The clock only moves on `GET /next`.** There is no timer anywhere in this
process. A trading system that needs a second to think costs itself a second;
one that is fast runs at whatever the machine allows.

**Orders queued against tick N fill at the open of tick N+1.** Enforced in the
session, not here, so it holds no matter how the session is driven.

This server binds loopback by default and is research-only: it simulates an
exchange and can place no real order, hold no key, and reach no venue.
"""

from __future__ import annotations

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import argparse
import json
import queue
import threading

from .backtest import CostModel
from .indicator_store import IndicatorStore
from .indicators import IndicatorSpec
from .ledger import BacktestRun
from .models import Bar, utc_now
from .session import BacktestSession, OrderRequest, SessionError

MAX_BODY_BYTES = 4 * 1024 * 1024


class SessionRegistry:
    """Live sessions, plus the subscribers watching them."""

    def __init__(self) -> None:
        self._sessions: dict[str, BacktestSession] = {}
        self._subscribers: dict[str, list[queue.Queue]] = {}
        self._lock = threading.Lock()

    def add(self, session: BacktestSession) -> str:
        with self._lock:
            self._sessions[session.run.backtest_id] = session
            self._subscribers.setdefault(session.run.backtest_id, [])
        return session.run.backtest_id

    def get(self, backtest_id: str) -> BacktestSession:
        with self._lock:
            session = self._sessions.get(backtest_id)
        if session is None:
            raise KeyError(backtest_id)
        return session

    def all(self) -> list[BacktestSession]:
        with self._lock:
            return list(self._sessions.values())

    def subscribe(self, backtest_id: str) -> queue.Queue:
        listener: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.setdefault(backtest_id, []).append(listener)
        return listener

    def unsubscribe(self, backtest_id: str, listener: queue.Queue) -> None:
        with self._lock:
            watchers = self._subscribers.get(backtest_id, [])
            if listener in watchers:
                watchers.remove(listener)

    def publish(self, backtest_id: str, event: dict[str, Any]) -> None:
        """Fan out to watchers, dropping for any that cannot keep up.

        A slow visualiser must never stall the backtest. Losing a frame on a
        chart is nothing; blocking the tape because a browser tab is busy would
        make the run's timing depend on who happens to be watching it.
        """
        with self._lock:
            watchers = list(self._subscribers.get(backtest_id, []))
        for listener in watchers:
            try:
                listener.put_nowait(event)
            except queue.Full:
                pass


REGISTRY = SessionRegistry()
DATA_LOADER = None  # set by main(); tests inject their own
# The 2025-12-31 lock, enforced by the tooling rather than by memory. The
# forward window is the only untouched evidence this project has and it cannot
# be un-seen, so a process serves it only when started with `--forward`.
FORWARD_ENABLED = False
# Backfilled indicators, when a root has been configured. Without one the
# session computes panels itself, which is fine for a handful of inline
# series and slow across the universe.
INDICATOR_STORE: IndicatorStore | None = None


def _bars_from_payload(payload: dict[str, Any]) -> dict[str, list[Bar]]:
    """Candles supplied inline. The loader path is for real universes."""
    out: dict[str, list[Bar]] = {}
    for symbol, rows in payload.items():
        bars = []
        for row in rows:
            stamp = row["timestamp"]
            bars.append(
                Bar(
                    timestamp=(
                        datetime.fromisoformat(stamp)
                        if isinstance(stamp, str)
                        else datetime.fromtimestamp(stamp, tz=timezone.utc)
                    ),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                )
            )
        out[symbol] = bars
    return out


def create_session(config: dict[str, Any]) -> BacktestSession:
    label = str(config.get("label", "unnamed"))
    initial_capital = float(config.get("initial_capital", 100_000.0))
    window_start = config.get("window_start")
    window_end = config.get("window_end")

    if "candles" in config:
        bars = _bars_from_payload(config["candles"])
    elif DATA_LOADER is not None:
        bars = DATA_LOADER(config.get("symbols"), window_start, window_end)
    else:
        raise SessionError(
            "supply `candles` inline, or start the server with a data loader"
        )

    run = BacktestRun(
        backtest_id=BacktestRun.fingerprint(
            config.get("strategy_family", label),
            config.get("strategy_params", {}),
            config.get("policy", {}),
            BacktestRun.universe_digest(bars),
            window_start,
            window_end,
            initial_capital,
        ),
        label=label,
        created_at=utc_now(),
        initial_capital=initial_capital,
        strategy_family=str(config.get("strategy_family", label)),
        strategy_params=config.get("strategy_params", {}) or {},
        policy=config.get("policy", {}) or {},
        universe_size=len(bars),
        window_start=window_start,
        window_end=window_end,
    )
    costs = CostModel(
        float(config.get("commission_bps", 0.0)),
        float(config.get("slippage_bps", 0.0)),
    )
    spec = (
        IndicatorSpec(**config["indicators"])
        if config.get("indicators")
        else IndicatorSpec()
    )
    return BacktestSession(
        run=run,
        bars_by_symbol=bars,
        costs=costs,
        indicator_spec=spec,
        start=_as_utc(window_start),
        end=_as_utc(window_end),
        indicator_store=INDICATOR_STORE,
        skip_warmup=bool(config.get("skip_warmup", True)),
    )


def _as_utc(value: str | None) -> datetime | None:
    """Parse a window bound and force it onto UTC.

    Callers write "2022-01-01", which `fromisoformat` returns naive, while every
    bar carries a timezone. Comparing the two raises deep inside the session and
    surfaces as an unhelpful 500 on session creation -- which is exactly how this
    was found.
    """
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class Handler(BaseHTTPRequestHandler):
    server_version = "QuantLabBacktester/1"

    def log_message(self, *args) -> None:  # noqa: D102 - quiet by default
        pass

    # -- plumbing ------------------------------------------------------------ #

    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            raise SessionError("request body too large")
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SessionError(f"body is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SessionError("body must be a JSON object")
        return parsed

    def _parts(self) -> list[str]:
        return [p for p in self.path.split("?")[0].strip("/").split("/") if p]

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # -- routes -------------------------------------------------------------- #

    def do_GET(self) -> None:  # noqa: N802
        parts = self._parts()
        try:
            if parts == ["health"]:
                return self._send(
                    200,
                    {
                        "status": "ok",
                        "sessions": len(REGISTRY.all()),
                        # Whether this process can serve bars past the 2025-12-31
                        # lock. A caller that needs the forward window and reuses
                        # a server without it would get a silently truncated tape
                        # and read the missing year as "no trades in 2026".
                        "forward": FORWARD_ENABLED,
                    },
                )
            if parts == ["sessions"]:
                return self._send(
                    200, {"sessions": [s.summary() for s in REGISTRY.all()]}
                )
            if len(parts) == 2 and parts[0] == "sessions":
                return self._send(200, REGISTRY.get(parts[1]).summary())
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "next":
                session = REGISTRY.get(parts[1])
                tick = session.next_tick()
                REGISTRY.publish(parts[1], {"type": "tick", "data": tick})
                return self._send(200, tick)
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "events":
                return self._stream(parts[1])
            # The book, readable after the fact. The orchestrator drives a run
            # over HTTP and has no session object of its own, so it reads the
            # record back from here to persist it. Serving these is not the
            # instrument forming an opinion -- it is the instrument being
            # auditable, which is the opposite.
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "orders":
                session = REGISTRY.get(parts[1])
                return self._send(
                    200,
                    {"orders": [order.document() for order in session.ledger.orders]},
                )
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "equity":
                return self._send(200, {"equity": REGISTRY.get(parts[1]).equity_curve})
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "decisions":
                return self._send(200, {"decisions": REGISTRY.get(parts[1]).decisions})
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "rejected":
                return self._send(200, {"rejected": REGISTRY.get(parts[1]).rejected})
            return self._send(404, {"error": "not found", "path": self.path})
        except KeyError:
            self._send(404, {"error": "no such session"})
        except SessionError as exc:
            self._send(409, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - a server must not die on one request
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:  # noqa: N802
        parts = self._parts()
        try:
            if parts == ["sessions"]:
                session = create_session(self._body())
                REGISTRY.add(session)
                return self._send(201, session.summary())
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "orders":
                session = REGISTRY.get(parts[1])
                body = self._body()
                orders = [
                    OrderRequest.from_payload(item) for item in body.get("orders", [])
                ]
                result = session.submit(orders, note=str(body.get("note", "")))
                REGISTRY.publish(
                    parts[1],
                    {
                        "type": "decision",
                        "data": {
                            "sequence": session.cursor,
                            "note": str(body.get("note", ""))[:500],
                            "orders": [order.__dict__ for order in orders],
                            "rejected": result["rejected"],
                        },
                    },
                )
                return self._send(202, result)
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "stop":
                session = REGISTRY.get(parts[1])
                summary = session.stop(str(self._body().get("reason", "unspecified")))
                REGISTRY.publish(parts[1], {"type": "stopped", "data": summary})
                return self._send(200, summary)
            return self._send(404, {"error": "not found", "path": self.path})
        except KeyError:
            self._send(404, {"error": "no such session"})
        except SessionError as exc:
            self._send(409, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def _stream(self, backtest_id: str) -> None:
        """Server-Sent Events for the visualiser.

        The backtester streams rather than the trading system, for one reason:
        it is the only party that sees both the candle and the fills, and the
        only one that cannot misreport them. A strategy narrating its own
        results would be marking its own homework.
        """
        REGISTRY.get(backtest_id)  # 404 before we commit to a long-lived response
        listener = REGISTRY.subscribe(backtest_id)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            while True:
                try:
                    event = listener.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    continue
                self.wfile.write(
                    f"event: {event['type']}\ndata: {json.dumps(event['data'], default=str)}\n\n".encode()
                )
                self.wfile.flush()
                if event["type"] in ("stopped", "complete"):
                    break
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            REGISTRY.unsubscribe(backtest_id, listener)


def _splice(research: list[Bar], forward: list[Bar]) -> list[Bar]:
    """Research bars, then whatever the forward file adds after them.

    Overlapping timestamps keep the RESEARCH bar. The two files are downloaded
    at different times from the same exchange and a bar that appears in both
    must resolve one way, permanently -- otherwise the same window returns
    different candles depending on which download ran last, and every
    `backtest_id` derived from a universe digest becomes unstable.
    """
    seen = {bar.timestamp for bar in research}
    extra = [bar for bar in forward if bar.timestamp not in seen]
    return sorted(research + extra, key=lambda bar: bar.timestamp)


def build_server(host: str = "127.0.0.1", port: int = 8770) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument(
        "--indicators",
        type=Path,
        default=None,
        help="root of backfilled indicator panels; served instead of recomputing",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="optional experiment database, to serve a real universe by symbol",
    )
    parser.add_argument(
        "--forward",
        action="store_true",
        help="splice the post-2025 forward window onto each series. OFF by "
        "default: 2026 is a locked forward evaluation and never feedback, so "
        "reaching it has to be a deliberate act rather than the default tape.",
    )
    args = parser.parse_args(argv)

    if args.forward:
        global FORWARD_ENABLED
        FORWARD_ENABLED = True

    if args.database:
        from .data import DataManager  # local import: only needed for this path

        def loader(symbols, window_start, window_end):
            import sqlite3

            connection = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            wanted = set(symbols or [])
            out: dict[str, list[Bar]] = {}
            for row in connection.execute(
                "SELECT symbol, research_path, forward_path FROM asset_universe "
                "WHERE research_path IS NOT NULL ORDER BY symbol"
            ):
                if wanted and row["symbol"] not in wanted:
                    continue
                bars = DataManager.load_csv(row["research_path"])
                if args.forward and row["forward_path"]:
                    bars = _splice(bars, DataManager.load_csv(row["forward_path"]))
                if len(bars) >= 2:
                    out[row["symbol"]] = bars
            connection.close()
            if not out:
                raise SessionError("no symbols matched the request")
            return out

        global DATA_LOADER
        DATA_LOADER = loader

    if args.indicators:
        global INDICATOR_STORE
        INDICATOR_STORE = IndicatorStore(args.indicators)

    server = build_server(args.host, args.port)
    print(f"backtester listening on http://{args.host}:{args.port}")
    print("  POST /sessions   GET /sessions/<id>/next   POST /sessions/<id>/orders")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
