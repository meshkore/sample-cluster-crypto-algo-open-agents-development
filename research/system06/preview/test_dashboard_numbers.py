"""The Live view opens with NUMBERS, from the real payloads, and does not throw.

Operator, 2026-09-16: "on the opening dashboard I want numbers". Operator, 2026-10-01:
the Live view became System 10's training monitor (renderMonitor), replacing the
system-06 loop tiles this file used to check (kpiRow, annual bars, model strip, Plan tab -
all removed on that instruction). What stays true and is asserted here, against the REAL
state and the REAL registry: the opening view is the monitor, it is mostly figures, and
the page raises no console error. The monitor's details are in test_training_monitor.py.

    python research/system06/preview/test_dashboard_numbers.py
"""

from __future__ import annotations

import functools
import http.server
import json
import pathlib
import socketserver
import sys
import threading

# This box's console is cp1252 and the page is full of arrows and middots. A test that
# dies formatting its own success line is a test nobody trusts.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parents[3]
PAGE = REPO / "research/system06/preview/dashboard.html"


def _serve(directory: pathlib.Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(directory))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def main() -> int:
    sys.path.insert(0, str(PAGE.parent))
    import mock_server
    from playwright.sync_api import sync_playwright

    state = mock_server._state()
    systems = mock_server._systems()

    errors: list[str] = []
    httpd, port = _serve(PAGE.parent)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/api/state", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(state, default=str)))
        page.route("**/api/systems", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(systems, default=str)))
        for route in ("**/api/knowledge", "**/api/iterations"):
            page.route(route, lambda r: r.fulfill(
                status=200, content_type="application/json", body="{}"))
        page.route("**/api/detail**", lambda r: r.fulfill(
            status=200, content_type="application/json", body="{}"))
        page.goto(f"http://127.0.0.1:{port}/{PAGE.name}")
        page.wait_for_selector("#tm #tmNow #tmLamp", timeout=10000)
        assert page.eval_on_selector("#viewLive", "e=>getComputedStyle(e).display") != "none",             "the page does not open on the Live view"
        text = page.inner_text("#tm")
        digits = sum(c.isdigit() for c in text)
        assert digits >= 120, f"only {digits} digits on the Live view - it is prose"
        assert "SUCCESS RATE" in text.upper(), "the progress chart is missing"
        print(f"  Live view = training monitor; {digits} digits")
        browser.close()
    httpd.shutdown()

    assert not errors, "the page threw:\n  " + "\n  ".join(errors[:6])
    print("  no console errors")
    print("dashboard numbers: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
