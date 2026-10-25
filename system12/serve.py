"""Serve the built pages locally: http://localhost:8799 (live) and /architecture. Rebuilt every 4h by the paper job.

python -m system12.serve [port]
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .publish import SITE_DIR

ROUTES = {
    "/": ("index.html", "text/html"),
    "/live": ("index.html", "text/html"),
    "/architecture": ("architecture.html", "text/html"),
    "/architecture.txt": ("architecture.txt", "text/plain"),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        name, ctype = ROUTES.get(self.path.split("?")[0].rstrip("/") or "/", (None, None))
        f = SITE_DIR / name if name else None
        if not f or not f.exists():
            self.send_error(404)
            return
        body = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
