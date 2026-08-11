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


# Pages the daemon will serve from `monitor/public/`, by name. An allow-list
# rather than a directory walk: serving "whatever is under this folder" turns
# one path-traversal slip into "whatever is on this disk", and the monitor runs
# on a machine that also holds the operator's credentials.
STATIC_PAGES: dict[str, str] = {
    "/": "index.html",
    "/index.html": "index.html",
    "/loop": "loop.html",
    "/loop.html": "loop.html",
}


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

    # A promoted genome is run twice: once over the fittable era and once over
    # 2026. The two are the same hypothesis seen from two sides, and the loop
    # names them so -- `loop-085-bear-training` and `loop-085-bear-2026`. The
    # pairing is by label because it needs no schema change and no column that
    # every historical row would carry as NULL.
    PHASES = {"2026": "training", "training": "2026"}

    def companion(self, run: dict[str, Any]) -> dict[str, Any] | None:
        """The other half of this run, if the loop recorded one.

        Returns the barest identification rather than the whole payload: the
        page only needs enough to fetch it when the reader asks, and shipping a
        second full curve with every detail request would double the response
        for a panel most visits never open.
        """
        label = str(run.get("label") or "")
        stem, _, suffix = label.rpartition("-")
        other = self.PHASES.get(suffix)
        if not stem or other is None:
            return None
        try:
            for candidate in self.store.runs(limit=400):
                if candidate.get("label") == f"{stem}-{other}":
                    return {
                        "backtest_id": candidate["backtest_id"],
                        "label": candidate["label"],
                        "phase": other,
                        "return_pct": candidate.get("return_pct"),
                        "trades": candidate.get("trades"),
                    }
        except sqlite3.Error:
            return None
        return None

    def detail(self, backtest_id: str) -> dict[str, Any] | None:
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
            "companion": self.companion(run),
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

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        try:
            if path == "/health":
                return self._json({"status": "ok"})
            if path == "/api/backtests":
                return self._json(self.data.sidebar())
            if path == "/api/loop":
                return self._json(self.data.activity() or {})
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
