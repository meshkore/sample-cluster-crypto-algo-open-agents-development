"""The monitor daemon: serve the page and the backtest archive. Nothing else.

This replaces a 1,727-line module that mixed the research loop, the champion
pipeline, an experiment database, a cluster bridge and an HTTP server into one
process. The loop it contained ran the *old* evaluation path -- an in-process
engine writing `portfolio_*` tables keyed by strategy number, one run per
strategy, silently overwriting the previous one. Agents launch runs through the
backtester service now, and every run has its own id, so the old pipeline had
nothing left to do but keep two schemas disagreeing with each other.

What survives is the part that was always separate in spirit: a read-only window
onto what the laboratory has done. It reads one table family, serves one page,
and holds no research state of its own.

    python3 -m quantlab_manager.monitor_server --port 8766

Routes, all read-only except none:

    GET /                      the monitor page from `monitor/public/`
    GET /health
    GET /api/backtests         champion, live runs, chronological history
    GET /api/backtests/<id>    run + equity + orders + trades + decisions

There is deliberately no write endpoint. Runs arrive by being launched through
the orchestrator, which persists them; a monitor that could also create them
would be a second way for results to exist.
"""

from __future__ import annotations

from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import argparse
import json
import sqlite3

from .config import Settings
from .sessions import SessionStore, open_database, regime_timeline

import base64
import hashlib
import struct
import time

# RFC 6455's magic constant. The handshake is four lines and one SHA-1, and
# hand-rolling it here avoids adding a dependency to the process that serves the
# research. This socket is loopback-only and read-only: it accepts no frame from
# the client except a close, and every byte it sends is an event the loop
# already wrote to disk.
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_frame(payload: bytes) -> bytes:
    """One unmasked text frame. Server frames are never masked (RFC 6455 §5.1)."""
    header = bytearray([0x81])  # FIN + text
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < (1 << 16):
        header.append(126)
        header += struct.pack(">H", length)
    else:
        header.append(127)
        header += struct.pack(">Q", length)
    return bytes(header) + payload


# Pages the daemon will serve from `monitor/public/`, by name. An allow-list
# rather than a directory walk: serving "whatever is under this folder" turns
# one path-traversal slip into "whatever is on this disk", and the monitor runs
# on a machine that also holds the operator's credentials.
STATIC_PAGES: dict[str, str] = {
    "/": "index.html",
    "/index.html": "index.html",
    "/loop": "loop.html",
    "/loop.html": "loop.html",
    "/live": "live.html",
    "/live.html": "live.html",
}


def journal_root() -> Path | None:
    """Where the loop writes one event file per hypothesis."""
    for candidate in (
        Path(__file__).resolve().parents[1] / "loop" / "journal",
        Path.cwd() / "orchestrator-manager" / "loop" / "journal",
    ):
        if candidate.is_dir():
            return candidate
    return None


def _hypothesis_id(raw: str) -> str | None:
    """`H-L088` and nothing else. This names a file, so it is an allow-list."""
    cleaned = (raw or "").strip()
    if not cleaned or len(cleaned) > 40:
        return None
    if not all(c.isalnum() or c in "-_" for c in cleaned):
        return None
    return cleaned


def read_journal(identifier: str, limit: int = 20_000) -> list[dict[str, Any]]:
    root = journal_root()
    name = _hypothesis_id(identifier)
    if root is None or name is None:
        return []
    path = root / f"{name}.jsonl"
    # `resolve` after joining, so a name that escaped the check cannot leave the
    # directory even if the check is later loosened.
    if not path.resolve().is_relative_to(root.resolve()):
        return []
    events: list[dict[str, Any]] = []
    try:
        with path.open() as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return events[-limit:]


def list_journals(limit: int = 60) -> list[dict[str, Any]]:
    """Every hypothesis with a journal, newest first."""
    root = journal_root()
    if root is None:
        return []
    out = []
    try:
        for path in sorted(
            root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:limit]:
            out.append(
                {
                    "id": path.stem,
                    "events": sum(1 for _ in path.open()),
                    "updated_at": path.stat().st_mtime,
                }
            )
    except OSError:
        return []
    return out


def monitor_root() -> Path | None:
    for candidate in (
        Path(__file__).resolve().parents[2] / "monitor" / "public",
        Path.cwd() / "monitor" / "public",
    ):
        if candidate.is_dir():
            return candidate
    return None


def static_page(filename: str) -> str | None:
    root = monitor_root()
    if root is None:
        return None
    path = root / filename
    try:
        return path.read_text()
    except OSError:
        return None


def monitor_page() -> str:
    """The page is a file in `monitor/`, not a string in this module.

    It used to be 1,306 lines of HTML inside the daemon, which meant it could
    not be opened, edited or deployed without touching the process that runs the
    research. The deployed copy on the edge is now literally the same file.
    """
    for candidate in (
        Path(__file__).resolve().parents[2] / "monitor" / "public" / "index.html",
        Path.cwd() / "monitor" / "public" / "index.html",
    ):
        if candidate.exists():
            return candidate.read_text()
    return (
        "<!doctype html><meta charset=utf-8><title>QuantLab</title>"
        "<body style='font:14px system-ui;background:#0b0f14;color:#e8eef7;padding:40px'>"
        "<h1>Monitor page not found</h1>"
        "<p>Expected <code>monitor/public/index.html</code> beside the packages.</p>"
        "</body>"
    )


class MonitorData:
    """Everything the page can ask for, from one store."""

    def __init__(self, store: SessionStore):
        self.store = store

    def sidebar(self) -> dict[str, Any]:
        try:
            return self.store.sidebar()
        except sqlite3.Error:
            # A monitor that dies because one table is missing is worse than a
            # monitor with one empty panel.
            return {"best_2026": None, "live": [], "history": []}

    def activity(self) -> dict[str, Any] | None:
        """The loop's heartbeat, or nothing if no loop has ever written one."""
        try:
            return self.store.activity()
        except (sqlite3.Error, AttributeError):
            return None

    def detail(self, backtest_id: str) -> dict[str, Any] | None:
        """One run, whole. Deliberately NOT its twin.

        A hypothesis exists as two runs -- one over the fittable era, one over
        2026 -- and the page offers a button for each. It used to be told here
        which run the other button led to, which meant the answer was frozen
        at publication time: a training run published before its 2026 half
        finished said "no 2026 half" for ever, and on the public mirror it
        still would.

        The page resolves the twin from the index it already holds, using the
        `pair_key` every row now carries. Same answer on this machine and on
        the edge, and it is never stale.
        """
        try:
            run = self.store.run(backtest_id)
        except sqlite3.Error:
            return None
        if run is None:
            return None
        decisions = self.store.decisions(backtest_id, limit=20_000)
        return {
            "run": run,
            "equity": self.store.equity(backtest_id),
            "orders": self.store.orders(backtest_id, limit=2000),
            "trades": self.store.trades(backtest_id, limit=2000),
            # The orders and decisions tables are read by a person and stay
            # capped. The regime is read by the chart and must cover every bar
            # drawn, so it is derived from the whole decision record and sent as
            # change points -- two dozen entries for eight years of tape.
            "decisions": decisions[:5000],
            "regimes": regime_timeline(decisions),
        }


class Handler(BaseHTTPRequestHandler):
    server_version = "QuantLabMonitor/2"

    def __init__(self, *args, data: MonitorData, **kwargs):
        self.data = data
        super().__init__(*args, **kwargs)

    def log_message(self, *args) -> None:
        return

    def _send(self, payload: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        # The monitor is a live page. Cached, a redeploy silently reaches nobody.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, value: Any, status: int = 200) -> None:
        self._send(
            json.dumps(value, default=str, allow_nan=False).encode(),
            "application/json",
            status,
        )

    # -- the live socket ------------------------------------------------------ #

    def _websocket(self) -> None:
        """Push journal events as the loop writes them.

        The loop does not talk to this process. It appends to a file, and this
        tails that file -- which means the socket cannot slow the research down,
        cannot lose events to a dropped connection, and replays the whole
        hypothesis to a browser that arrives halfway through. The alternative,
        the loop holding a socket open to the monitor, makes the observer
        something the observed has to wait for.

        Loopback only. There is no authentication here because there is no
        listener off this machine and nothing to authorise: every byte is an
        event already served by `/api/journal`.
        """
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            return self._json({"error": "not a websocket handshake"}, 400)
        accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode()).digest()
        ).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        sent = 0
        current = ""
        try:
            while True:
                beat = self.data.activity() or {}
                hypothesis = str(beat.get("hypothesis") or "")
                if hypothesis and hypothesis != current:
                    # A new hypothesis: replay it from its first event so the
                    # diagram is never half-drawn.
                    current, sent = hypothesis, 0
                events = read_journal(current) if current else []
                for event in events[sent:]:
                    self.wfile.write(ws_frame(json.dumps(event, default=str).encode()))
                    self.wfile.flush()
                if len(events) > sent:
                    sent = len(events)
                # A heartbeat of our own, so a page can tell "nothing is
                # happening" from "the socket died two hours ago".
                self.wfile.write(
                    ws_frame(
                        json.dumps({"type": "tick", "beat": beat}, default=str).encode()
                    )
                )
                self.wfile.flush()
                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        try:
            if path == "/health":
                # `websocket` is a capability, not trivia. The live page asks
                # before opening a socket, because the public mirror is a Worker
                # that receives pushed snapshots and can never hold one open --
                # and a page that tries anyway leaves a failed handshake in every
                # visitor's console before falling back to what it was always
                # going to use.
                return self._json({"status": "ok", "websocket": True})
            if path == "/ws":
                return self._websocket()
            if path == "/api/backtests":
                return self._json(self.data.sidebar())
            if path == "/api/loop":
                return self._json(self.data.activity() or {})
            if path == "/api/journals":
                return self._json({"journals": list_journals()})
            if path == "/api/journal":
                # The hypothesis in flight, so a page needs no id to start.
                beat = self.data.activity() or {}
                identifier = str(beat.get("hypothesis") or "")
                return self._json(
                    {
                        "id": identifier,
                        "events": read_journal(identifier) if identifier else [],
                    }
                )
            if path.startswith("/api/journal/"):
                identifier = path.rsplit("/", 1)[-1]
                return self._json(
                    {"id": identifier, "events": read_journal(identifier)}
                )
            if path.startswith("/api/backtests/"):
                backtest_id = path.rsplit("/", 1)[-1]
                detail = self.data.detail(backtest_id)
                if detail is None:
                    return self._json({"error": "not found"}, 404)
                return self._json(detail)
            if path in STATIC_PAGES:
                if path in ("/", "/index.html"):
                    return self._send(
                        monitor_page().encode(), "text/html; charset=utf-8"
                    )
                page = static_page(STATIC_PAGES[path])
                if page is not None:
                    return self._send(page.encode(), "text/html; charset=utf-8")
            self._json({"error": "not found", "path": path}, 404)
        except Exception as exc:  # noqa: BLE001 - one bad request must not end the server
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)


def build_server(
    store: SessionStore, host: str = "127.0.0.1", port: int = 8766
) -> ThreadingHTTPServer:
    handler = partial(Handler, data=MonitorData(store))
    return ThreadingHTTPServer((host, port), handler)


def run_daemon(
    settings: Settings, host: str = "127.0.0.1", port: int | None = None
) -> int:
    port = port or int(getattr(settings, "dashboard_port", 8766) or 8766)
    server = build_server(open_database(settings.database_path), host, port)
    print(f"monitor on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("orchestrator-manager/config/default.json")
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)
    return run_daemon(Settings.load(args.config), args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
