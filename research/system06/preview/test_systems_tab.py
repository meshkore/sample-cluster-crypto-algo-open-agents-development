"""The system registry and its Log tab, exercised in a real browser.

The markdown renderer on the page is the only piece of this change a static test cannot
judge: a table that silently renders as a paragraph, or an escaped `<b>` showing as
literal text, is invisible to grep and obvious to a browser. So this drives the actual
page with the actual documentation and asserts on what a reader would see.

The page is served over an EPHEMERAL localhost port inside the test rather than opened
as a file:// URL, because Chromium refuses fetch from a file origin and every stubbed
endpoint would fail before rendering. That server is a throwaway that dies with the
test; it is not the local mock_server on :8799, which stays off. Playwright only, never
a screenshot for judgement -- the assertions are on the DOM.

    python research/system06/preview/test_systems_tab.py
"""

from __future__ import annotations

import functools
import http.server
import json
import pathlib
import socketserver
import sys
import threading

REPO = pathlib.Path(__file__).resolve().parents[3]
PAGE = REPO / "research/system06/preview/dashboard.html"
TRADING = REPO / "trading-system"


def _registry() -> list[dict]:
    out = []
    for ctx in sorted(TRADING.glob("systems/system*/docs/context.json")):
        doc = json.loads(ctx.read_text(encoding="utf-8"))
        doc["package"] = ctx.parents[1].name
        doc["summary_md"] = (ctx.parent / "SUMMARY.md").read_text(encoding="utf-8")
        doc["results_md"] = (ctx.parent / "RESULTS.md").read_text(encoding="utf-8")
        out.append(doc)
    rank = {"champion": 0, "workshop": 1, "blank": 2, "frozen": 3}
    out.sort(key=lambda d: (rank.get(d.get("status"), 9), d.get("id") or ""))
    return out


def _serve(directory: pathlib.Path):
    """A throwaway static server on an ephemeral port. Dies with the test."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(directory))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def main() -> int:
    from playwright.sync_api import sync_playwright

    systems = _registry()
    assert systems, "no documented systems found"

    httpd, port = _serve(PAGE.parent)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        # Every endpoint the page polls is stubbed. /api/systems returns the real
        # registry; the rest return empty shapes so nothing else renders or throws.
        # /api/systems is deliberately made to FAIL here, so the test exercises the
        # fallback the public site actually uses today: the registry filed in the
        # details map under a reserved id.
        page.route("**/api/systems", lambda r: r.fulfill(status=404, body="not found"))
        page.route("**/api/detail?id=__systems__", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(systems)))
        for route in ("**/api/state", "**/api/knowledge", "**/api/iterations"):
            page.route(route, lambda r: r.fulfill(
                status=200, content_type="application/json", body="{}"))
        page.goto(f"http://127.0.0.1:{port}/{PAGE.name}")
        # `let` at script scope is reachable by name but is NOT a property of window,
        # so the condition asks for the binding rather than for window.SYSTEMS.
        page.wait_for_function("typeof SYSTEMS !== 'undefined' && SYSTEMS.length > 0",
                               timeout=10000)

        page.evaluate("setView('strategies')")
        page.wait_for_selector("#sysbox .syscard", timeout=8000)
        cards = page.query_selector_all("#sysbox .syscard")
        assert len(cards) == len(systems), \
            f"expected one box per system ({len(systems)}), rendered {len(cards)}"
        print(f"  {len(cards)} system boxes, one per system")

        first = cards[0].inner_text()
        assert "champion" in first, f"the champion should lead the list, got: {first!r}"
        print(f"  champion first: {first.splitlines()[0]}")

        page.evaluate("select('__sys__:system06')")
        page.wait_for_selector("#detail .md h2", timeout=8000)
        body = page.inner_text("#detail")
        for heading in ("Hypothesis", "What helped", "What hurt", "Rules learned"):
            assert heading in body, f"the Log tab is missing the {heading!r} section"
        print("  Log tab renders every required section")

        tables = page.query_selector_all("#detail .md table")
        assert len(tables) >= 3, \
            f"the helped/hurt/open tables must render AS TABLES; found {len(tables)}"
        print(f"  {len(tables)} markdown tables rendered as real tables")

        assert "<b>" not in page.inner_text("#detail"), \
            "markup is leaking as literal text - the renderer escaped after formatting"
        bolds = page.query_selector_all("#detail .md b")
        assert bolds, "bold emphasis produced no <b> elements at all"
        print(f"  {len(bolds)} emphasised spans, no literal markup")

        page.evaluate("setSysTab('res')")
        page.wait_for_timeout(150)
        results = page.inner_text("#detail")
        assert "SEALED" in results.upper(), "the Results tab is not showing the sealed era"
        print("  Results tab shows the sealed era")

        # The tab is STICKY across cards - the page's existing convention, so a reader
        # comparing two systems' logs is not thrown back to Results on every click.
        # Which means the test has to ask for Log rather than assume it.
        page.evaluate("select('__sys__:system08')")
        page.evaluate("setSysTab('log')")
        page.wait_for_timeout(150)
        closed = page.inner_text("#detail")
        # System 08 was BLANK when this line was written, and it checked that a blank
        # system still pointed a reader at what the champion had already refused. It is
        # now CLOSED, so the pointer that matters most is its own post-mortem: the reason
        # nobody should restart it and the fifteen ideas nobody should re-propose.
        assert "POSTMORTEM.md" in closed, \
            "the closed system must point a reader at its post-mortem"
        assert "system006_oracle_net_15m/docs/SUMMARY.md" in closed, \
            "the closed system must still point at what was already refused"
        print("  the closed system points at its post-mortem and the champion's refusals")

        browser.close()
    print("\nsystems tab OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
