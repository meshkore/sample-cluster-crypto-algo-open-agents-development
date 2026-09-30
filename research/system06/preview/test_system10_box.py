"""System 10's box in the systems list, its four tabs, its model-card placeholder - and
the proof that system 06's panels did not move. Driven in a real browser (Playwright,
local only, as for the other tests in this folder).

The registry is built by `mock_server._systems()`, the SAME function the pusher publishes,
so this checks what the public page receives rather than a hand-made copy of it. The
model card is exercised both ways: absent (the honest placeholder, which is today's state)
and present (a synthetic card of the documented shape, research/system10/README.md).

06 is checked twice: its systems box keeps exactly its Log and Results tabs with no
training panel, and its Trading area renders the same four tiles and the same book as
test_trading_panel.py asserts.

    python research/system06/preview/test_system10_box.py
"""

from __future__ import annotations

import copy
import functools
import http.server
import json
import pathlib
import socketserver
import sys
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parents[3]
PAGE = REPO / "research/system06/preview/dashboard.html"

CARD = {
    "system": "system10", "family": "system10-conditioned-rl", "system_type": "ai-model",
    "status": "offline-rl", "updated_at": "2026-10-04T12:00:00+00:00",
    "walk_forward": {"current_year": 2024, "trained_through": 2023,
                     "validation_years": [2024, 2025]},
    "region": {"version": "r0-gates", "target_coverage": 0.8,
               "coverage": {"2022": {"best_trades": 0.83, "bars": 0.21},
                            "2023": {"best_trades": 0.81, "bars": 0.24}}},
    "clone": {"status": "done", "validation": {
        "2024": {"return": 0.12, "max_drawdown": 0.08, "q": 0.18, "trades": 140}}},
    "offline_rl": {"algorithm": "IQL", "status": "running", "beats_clone": None,
                   "validation": {}},
    "seeds": {"planned": 4, "done": [0, 1], "spread": {"q": 0.21, "return": 0.05}},
    "gpu_lane": {"state": "held", "holder": "system10 offline-rl",
                 "since": "2026-10-04T09:00:00+00:00",
                 "brake": "research/system06/STOP_AUTOLOOP"},
}


def _serve(directory: pathlib.Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def main() -> int:
    sys.path.insert(0, str(PAGE.parent))
    import mock_server
    from test_trading_panel import LIVE
    from playwright.sync_api import sync_playwright

    systems = mock_server._systems()
    ten = next((s for s in systems if s.get("id") == "system10"), None)
    six = next((s for s in systems if s.get("id") == "system06"), None)
    assert ten and six, "system06 and system10 must both be in the registry"
    assert ten.get("status") == "workshop", f"010 status is {ten.get('status')!r}"
    assert ten.get("theory_md", "").startswith("## 0."), "Theory must be the design's section 0 onward"
    for sec in ("## 0.", "## 1.", "## 2.", "## 3."):
        assert sec in ten["theory_md"], f"Theory lacks {sec}"
    assert "## 4." not in ten["theory_md"], "Theory must stop at section 3"
    assert ten.get("diagram", {}).get("nodes"), "010 has no diagram"
    assert "model_card" in ten, "an ai-model system must carry the model_card key"
    for key in ("theory_md", "diagram", "model_card"):
        assert key not in six, f"06's box gained {key!r} - its panels must not change"
    print(f"  registry: {len(systems)} systems; 010 workshop with theory, diagram, card key")

    state = mock_server._state()
    state["live"] = LIVE
    # The placeholder is what the page must show until the trainer writes a card, so the
    # test forces that state rather than depending on whether the file exists today.
    absent = copy.deepcopy(systems)
    next(s for s in absent if s["id"] == "system10")["model_card"] = None
    present = copy.deepcopy(systems)
    next(s for s in present if s["id"] == "system10")["model_card"] = CARD
    feed = {"systems": absent}

    errors: list[str] = []
    httpd, port = _serve(PAGE.parent)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        # The deliberate /api/systems 404 (and a favicon) log "Failed to load resource";
        # those are the fallback working, not the page breaking.
        page.on("console", lambda m: errors.append(m.text)
                if m.type == "error" and not m.text.startswith("Failed to load resource")
                else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/api/state", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(state, default=str)))
        # Every other detail answers empty; routes registered later take precedence.
        page.route("**/api/detail**", lambda r: r.fulfill(
            status=200, content_type="application/json", body="{}"))
        # /api/systems dark, as on the deployed Worker: the registry arrives through the
        # details-map fallback, which is the no-deploy route the pusher uses.
        page.route("**/api/systems", lambda r: r.fulfill(status=404, body="not found"))
        page.route("**/api/detail?id=__systems__", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(feed["systems"], default=str)))
        for route in ("**/api/knowledge", "**/api/iterations"):
            page.route(route, lambda r: r.fulfill(status=200,
                                                  content_type="application/json", body="{}"))
        page.goto(f"http://127.0.0.1:{port}/{PAGE.name}")
        page.wait_for_function("typeof SYSTEMS !== 'undefined' && SYSTEMS.length > 0",
                               timeout=10000)

        # -- the box ------------------------------------------------------------------
        page.evaluate("setView('strategies')")
        page.wait_for_selector("#sysbox .syscard", timeout=8000)
        boxes = [c.inner_text() for c in page.query_selector_all("#sysbox .syscard")]
        box10 = [b for b in boxes if "system10" in b]
        assert len(box10) == 1, f"expected exactly one 010 box, got {len(box10)}"
        assert "workshop" in box10[0], f"010's box does not say workshop: {box10[0]!r}"
        print("  010 box renders, status workshop")

        # -- four tabs ----------------------------------------------------------------
        page.evaluate("select('__sys__:system10')")
        page.evaluate("setSysTab('log')")
        page.wait_for_selector("#detail .innertabs", timeout=8000)
        tabs = [t.inner_text().strip() for t in page.query_selector_all("#detail .itab")]
        assert sorted(tabs) == sorted(["Results", "Theory", "Diagram", "Log"]), tabs
        print(f"  010 tabs: {tabs}")

        assert "Hypothesis" in page.inner_text("#detail"), "010's Log is not its SUMMARY"

        page.evaluate("setSysTab('teo')")
        teo = page.inner_text("#detail")
        assert "The operator's ask" in teo and "The architecture" in teo, "Theory is not sections 0-3"
        assert "Default design choices" not in teo, "Theory leaked section 4"
        print("  Theory = design sections 0-3")

        page.evaluate("setSysTab('dia')")
        page.wait_for_selector("#sysDiagram svg", timeout=4000)
        n_boxes = len(page.query_selector_all("#sysDiagram svg g.node"))
        n_links = len(page.query_selector_all("#sysDiagram svg polyline.edge"))
        assert n_boxes == len(ten["diagram"]["nodes"]), f"{n_boxes} boxes drawn"
        assert n_links == len(ten["diagram"]["edges"]), f"{n_links} links drawn"
        assert "POLICY" in page.inner_text("#sysDiagram"), "the policy box is missing"
        print(f"  Diagram: inline SVG, {n_boxes} boxes, {n_links} links")

        # -- the training area: placeholder, then a published card ---------------------
        page.evaluate("setSysTab('res')")
        page.wait_for_selector("#sysModelCard", timeout=4000)
        card_txt = page.inner_text("#sysModelCard")
        assert "not published yet" in card_txt.lower(), f"placeholder missing: {card_txt!r}"
        assert "research/system10/model_card.json" in card_txt
        assert "SEALED" in page.inner_text("#detail").upper(), "Results lost its sealed era"
        print("  training area: 'not published yet' placeholder")

        feed["systems"] = present
        page.evaluate("fetchSystems()")
        page.wait_for_function(
            "document.querySelector('#sysModelCard') && "
            "!/not published yet/i.test(document.querySelector('#sysModelCard').innerText)",
            timeout=6000)
        card_txt = page.inner_text("#sysModelCard")
        for want in ("2024", "held", "2/4", "IQL", "+83%", "clone validation"):
            assert want in card_txt.lower() or want in card_txt, f"the published card does not show {want!r}"
        print("  training area: a published card renders its fields")

        # -- 06 is unchanged ------------------------------------------------------------
        page.evaluate("select('__sys__:system06')")
        page.evaluate("setSysTab('teo')")     # sticky tab 06 does not have -> its Log
        tabs6 = [t.inner_text().strip() for t in page.query_selector_all("#detail .itab")]
        assert tabs6 == ["Log", "Results"], f"06's systems tabs changed: {tabs6}"
        assert "Hypothesis" in page.inner_text("#detail"), "06 did not fall back to its Log"
        page.evaluate("setSysTab('res')")
        assert page.query_selector("#sysModelCard") is None, "06 gained a training panel"
        print("  06 box: still Log + Results, no training panel")

        page.evaluate("setView('trading')")
        page.wait_for_selector("#tradingBody .kpi .kt", timeout=8000)
        tiles = page.query_selector_all("#tradingBody .kpi .kt")
        assert len(tiles) == 4, f"06's Trading area: expected four tiles, found {len(tiles)}"
        assert "$100,842.11" in page.inner_text("#tradingBody .kpi .kt.hero")
        body = page.inner_text("#tradingBody")
        for want in ("BTCUSDT", "76425", "190.22", "v1-champion-192x3"):
            assert want in body, f"06's Trading area lost {want!r}"
        assert "system10" not in body.lower(), "010 leaked into the Trading area"
        print("  06 Trading area: unchanged (four tiles, book, orders)")

        browser.close()
    httpd.shutdown()

    assert not errors, "the page threw:\n  " + "\n  ".join(errors[:6])
    print("\nsystem 10 box: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
