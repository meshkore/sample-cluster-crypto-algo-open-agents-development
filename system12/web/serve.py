"""Serve the built pages on http://localhost:8799 (read-only; the paper job rebuilds them every 4h).

python -m system12.web.serve [port]
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..config import SITE_DIR
from . import FILES

ROUTES = {**FILES, "/live": FILES["/"]}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server API)
        name = ROUTES.get(self.path.split("?")[0].rstrip("/") or "/")
        path = SITE_DIR / name if name else None
        if path is None or not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8" if name.endswith(".txt") else "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
