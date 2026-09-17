"""The dashboard opens with NUMBERS, and the numbers are the real ones.

Operator, 2026-09-16, looking at the live page: "I see a lot of absurd text I am not
going to read and I do not see numbers or charts, which is what matters most... on the
opening dashboard I want numbers. I want to see the best results per year. I want you to
flag what you are trying to improve."

So this drives the real page with the real state payload and asserts on what a reader
would actually see: four headline tiles, a flag naming the running experiment, one bar
per calendar year with its value written on it, and the net's figures as chips. It also
fails on any console error, because a page that throws halfway renders a convincing
partial dashboard and says nothing about it.

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
    assert state.get("best"), "no champion in the state payload"
    assert state.get("model"), "no model block in the state payload"

    errors: list[str] = []
    httpd, port = _serve(PAGE.parent)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/api/state", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(state, default=str)))
        for route in ("**/api/knowledge", "**/api/iterations", "**/api/systems"):
            page.route(route, lambda r: r.fulfill(
                status=200, content_type="application/json", body="{}"))
        page.route("**/api/detail**", lambda r: r.fulfill(
            status=200, content_type="application/json", body="{}"))
        page.goto(f"http://127.0.0.1:{port}/{PAGE.name}")
        page.wait_for_function("typeof STATE !== 'undefined' && STATE && STATE.best",
                               timeout=10000)
        page.evaluate("setView('live'); setLiveTab('dashboard')")
        page.wait_for_selector("#liveBody .kpi .kt", timeout=8000)

        tiles = page.query_selector_all("#liveBody .kpi .kt")
        assert len(tiles) == 4, f"expected four headline tiles, found {len(tiles)}"
        hero = page.inner_text("#liveBody .kpi .kt.hero")
        assert "%" in hero and "2026" in hero, f"the hero tile is not the sealed year: {hero!r}"
        print(f"  4 headline tiles; hero = {hero.splitlines()[1] if len(hero.splitlines())>1 else hero}")

        # One bar per year that has a result, each with its value written beside it, so
        # the colour is never the only thing telling a reader the sign.
        bars = page.query_selector_all("#liveBody .ybars g.bar")
        annual = {k: v for k, v in (state["best"].get("annual") or {}).items() if v is not None}
        assert len(bars) == len(annual), \
            f"expected one bar per year with a result ({len(annual)}), found {len(bars)}"
        # `text_content`, not `inner_text`: these are SVG <g> nodes, and Playwright's
        # inner_text only speaks HTMLElement.
        labels = [(b.text_content() or "").strip() for b in bars]
        assert all("%" in lbl for lbl in labels), \
            f"every bar must carry its own value as text: {labels}"
        assert any("SEALED" in lbl for lbl in labels), "the sealed year is not marked"
        print(f"  {len(bars)} year bars, all direct-labelled, sealed year marked")

        # TWO headline numbers, never one. Operator, 2026-09-17: "give two figures for
        # the winning system - the largest profit, and the optimal one". A page that
        # shows only the biggest number is the failure mode this asserts against.
        # The tile labels are uppercased by CSS, so compare case-insensitively.
        heads = page.inner_text("#liveBody .kpi").lower()
        assert "max profit" in heads and "optimal" in heads,             f"the dashboard does not carry both headline numbers: {heads[:200]!r}"
        q = state.get("quality") or {}
        if q.get("optimal"):
            assert f"{q['optimal']['eff']:.2f}" in heads,                 "the optimal tile does not state return per unit of drawdown"
        print("  both headlines present: max profit and optimal")

        chips = page.query_selector_all("#liveBody .mstrip .mchip")
        assert len(chips) >= 8, f"the model strip is thin: {len(chips)} chips"
        strip = page.inner_text("#liveBody .mstrip")
        for want in ("params", "reach", "candles", "pairs"):
            assert want in strip, f"the model strip does not state {want!r}"
        print(f"  {len(chips)} model chips: {strip.replace(chr(10), ' ')[:90]}…")

        if state.get("experiment", {}).get("id"):
            flag = page.inner_text("#liveBody .flagx")
            assert state["experiment"]["id"] in flag, \
                f"the flag does not name the running experiment: {flag!r}"
            print(f"  flag: {flag.replace(chr(10), ' ')[:80]}…")

        # The prose did not vanish, it moved. The Plan tab must still carry it.
        page.evaluate("setLiveTab('plan')")
        page.wait_for_timeout(200)
        plan = page.inner_text("#liveBody")
        assert len(plan) > 200, "the Plan tab is empty - the prose was lost, not moved"
        print(f"  Plan tab still carries the words ({len(plan)} chars)")

        # The dashboard itself must be mostly figures rather than sentences.
        page.evaluate("setLiveTab('dashboard')")
        page.wait_for_timeout(200)
        text = page.inner_text("#liveBody")
        words = [w for w in text.split() if any(c.isalpha() for c in w)]
        digits = sum(c.isdigit() for c in text)
        assert digits >= 120, f"only {digits} digits on the dashboard - it is still prose"
        print(f"  dashboard body: {digits} digits, {len(words)} words")

        rail = page.inner_text("#liveRail")
        assert len(rail) < 4000, f"the rail is still a wall of text ({len(rail)} chars)"
        print(f"  rail trimmed to {len(rail)} chars")

        browser.close()
    httpd.shutdown()

    assert not errors, "the page threw:\n  " + "\n  ".join(errors[:6])
    print("  no console errors")
    print("dashboard numbers: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
