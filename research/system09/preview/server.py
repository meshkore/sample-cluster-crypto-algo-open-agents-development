"""The local frontend for system 09: `python research/system09/preview/server.py`.

Serves `dashboard.html` and one JSON route, `api/state`, built by
`system009_participant_ledger.frontend_data` from the artefacts the phases actually wrote. Nothing here
computes a result and nothing here invents one - if phase 3 has not run, the 2026 section
arrives as null and the page says so out loud rather than drawing a flat line.

This is the LOCAL view. It binds to localhost, it has no write routes, and it is not the
deployed dashboard.
"""

from __future__ import annotations

import json
import time
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "trading-system"))

PAGE = HERE / "dashboard.html"
STATE = ROOT / "research" / "system09" / "frontend.json"
PORT = 8709


def _state() -> bytes:
    """The payload, rebuilt on demand when it is missing.

    Rebuilding costs a reconstruction the first time and nothing afterwards, because
    `pipeline.reconstruct` caches. A stale file is never served silently: deleting
    `frontend.json` is the documented way to force a refresh.
    """
    if not STATE.is_file():
        from system009_participant_ledger import frontend_data
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(frontend_data.build()), encoding="utf-8")
    return STATE.read_bytes()


def _activity() -> dict:
    """Jobs running now, what the loop has finished, and what is still queued."""
    from system009_participant_ledger import heartbeat
    root = ROOT / "research" / "system09"

    def read(name, default):
        f = root / name
        if not f.is_file():
            return default
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default

    recent = []
    ledger = root / "loop.jsonl"
    if ledger.is_file():
        lines = ledger.read_text(encoding="utf-8").splitlines()[-12:]
        for line in lines:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            res = r.get("result") or {}
            recent.append({"at": r.get("at"), "experiment": r.get("experiment"),
                           "ok": r.get("ok"), "seconds": r.get("seconds"),
                           "why": r.get("why"),
                           "headline": _headline(r.get("experiment"), res, r.get("error"))})
    backlog = read("backlog.json", [])
    return {"jobs": heartbeat.active(), "recent": list(reversed(recent)),
            "backlog": backlog, "loop": read("loop_live.json", {}),
            "server_time": time.time()}


def _headline(name: str, result: dict, error: str | None) -> str:
    """One line a person can read without opening the JSON."""
    if error:
        return error[:120]
    if not isinstance(result, dict):
        return ""
    if name == "calibration":
        w = result.get("worst_float_error")
        return (f"{'CALIBRATED' if result.get('calibrated') else 'NOT CALIBRATED'}"
                f" - worst float error {w:.3%}" if w is not None else "")
    if name == "world":
        s = result.get("summary", {}).get("market+ledger+world", {})
        return (f"ledger+world mean IC {s.get('mean_ic', float('nan')):+.4f}, "
                f"positive {s.get('folds_positive')}/{s.get('n')}")
    if name == "policy":
        c = result.get("chosen", {})
        return (f"{c.get('horizon')}d {c.get('shape')} x{c.get('width')} - worst year "
                f"{c.get('worst', float('nan')):+.1%}, "
                + ("QUALIFIED" if result.get("qualified") else "none beat holding"))
    if name == "horizons":
        v = result.get("verdict", {})
        return f"best horizon {v.get('horizon')}d, mean IC {v.get('mean_ic', 0):+.4f}"
    if name == "behaviour":
        return (f"{result.get('beat_persistence')} of {result.get('total')} cohort-horizons "
                f"beat the group's own inertia")
    return ""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:                      # noqa: N802 - stdlib naming
        path = self.path.split("?")[0].strip("/")
        try:
            if path in ("", "index.html", "dashboard.html"):
                self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "api/state":
                self._send(_state(), "application/json")
            elif path == "api/activity":
                # Read from disk on every request, deliberately. This endpoint exists to say
                # what is happening RIGHT NOW, so a cached answer would defeat it.
                self._send(json.dumps(_activity()).encode(), "application/json")
            else:
                self._send(b"not found", "text/plain", 404)
        except Exception as exc:                   # noqa: BLE001 - report, never hide
            self._send(json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode(),
                       "application/json", 500)

    def log_message(self, fmt: str, *args) -> None:
        return                                     # the console is for the reconstruction


def main() -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"system 09 local frontend  ->  http://127.0.0.1:{PORT}/")
    print(f"  page   {PAGE}")
    print(f"  state  {STATE}"
          + ("" if STATE.is_file() else "   (will be built on the first request)"))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
