"""The Live view is System 10's training monitor - and it renders from the real card.

Operator, 2026-10-01: the Live view had become too complex; it should read like a
mission-control screen. The view is now one instrument panel (renderMonitor in
dashboard.html) fed by research/system10/model_card.json, which reaches the page as
`model_card` on system10 in the registry (`mock_server._systems()`, the same function the
pusher publishes).

The fixture is a COPY of the real card (fixtures/training_monitor/system10/), read through
`_system_model_card`, so this checks the shape the trainer actually writes. Asserted, in a
real browser:
  - the status strip: GPU, utilisation, memory, temperature, LIVE/STALE lamp, search, data
  - the hero chart: one dot per trial, the 50% coin-flip line, the big number
  - the event track: one marker per event on the same axis, with labels and tooltips
  - the 2026 forward charts: empty state today; lines once hourly readings exist
  - counters, the plain-words panel, the champion's four unseen years as bars
  - old deep links (#/live/theory ...) land on the monitor; no console errors

    python research/system06/preview/test_training_monitor.py [screenshot-dir]
"""

from __future__ import annotations

import copy
import datetime as dt
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
FIXTURES = PAGE.parent / "fixtures" / "training_monitor"


def _serve(directory: pathlib.Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    shots = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.path.insert(0, str(PAGE.parent))
    import mock_server
    from playwright.sync_api import sync_playwright

    card = mock_server._system_model_card({"id": "system10"}, FIXTURES)
    assert card, "fixture card did not load"
    for key in ("monitor", "champion", "trial_series", "events", "timeline"):
        assert key in card, f"the card lost {key!r} on its way through _system_model_card"
    assert len(json.dumps(card)) < 200_000, "the card payload is too large"

    # Thinning: a long search keeps its step-line corners and stays small.
    long = [{"at": f"2026-10-0{1 + i // 1000}T00:00:00", "n": i, "win_rate": 0.5,
             "best_win_rate": (0.5 + (i // 500) * 0.01) if i > 10 else None,
             "eligible": False} for i in range(3000)]
    thin = mock_server._thin_rows(long, mock_server.TM_MAX_TRIALS)
    assert len(thin) <= mock_server.TM_MAX_TRIALS + 20, len(thin)
    assert thin[-1] is long[-1] and thin[0] is long[0]
    corners = {r["best_win_rate"] for r in long}
    assert corners <= {r["best_win_rate"] for r in thin}, "thinning dropped a step of the best line"
    print(f"  card: {len(json.dumps(card))} bytes; 3000 trials thin to {len(thin)}, corners kept")

    now = dt.datetime.now(dt.timezone.utc)
    fresh = copy.deepcopy(card)
    fresh["monitor"]["gpu"]["at"] = _iso(now - dt.timedelta(minutes=2))
    fresh["monitor"]["last_trial"]["at"] = _iso(now - dt.timedelta(minutes=1))
    fresh["updated_at"] = _iso(now - dt.timedelta(minutes=2))

    systems = mock_server._systems()
    feed = {"systems": None}

    def with_card(c):
        out = copy.deepcopy(systems)
        ten = next(s for s in out if s.get("id") == "system10")
        ten["model_card"] = c
        return out

    feed["systems"] = with_card(fresh)
    state = mock_server._state()

    errors: list[str] = []
    httpd, port = _serve(PAGE.parent)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.on("console", lambda m: errors.append(m.text)
                if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/api/state", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(state, default=str)))
        page.route("**/api/detail**", lambda r: r.fulfill(
            status=200, content_type="application/json", body="{}"))
        page.route("**/api/systems", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(feed["systems"], default=str)))
        for route in ("**/api/knowledge", "**/api/iterations"):
            page.route(route, lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))

        page.goto(f"http://127.0.0.1:{port}/{PAGE.name}#/live")
        page.wait_for_selector("#tm #tmHeroSvg", timeout=10000)
        assert page.eval_on_selector("#viewLive", "e=>getComputedStyle(e).display") != "none"

        # -- status strip ------------------------------------------------------------
        strip = page.inner_text("#tmStatus")
        for want in ("RTX 4060", "3%", "6.1 / 8.0 GB", "41 °C", "LIVE", "RUNNING", "updated"):
            assert want in strip, f"status strip lacks {want!r}: {strip!r}"
        assert "live" in page.get_attribute("#tmLamp", "class")
        print("  status strip: GPU, util, memory, temp, LIVE lamp, search running, data age")

        # -- hero chart --------------------------------------------------------------
        n_trials = len([r for r in card["trial_series"] if r.get("win_rate") is not None])
        dots = page.query_selector_all("#tmHeroSvg circle.tm-trial")
        assert len(dots) == n_trials, f"{len(dots)} trial dots for {n_trials} trials"
        assert page.query_selector("#tmHeroSvg line.tm-ref"), "no coin-flip line"
        assert "coin flip" in (page.text_content("#tmHeroSvg") or "")
        assert page.query_selector("#tmHeroSvg path.tm-best"), "no best-so-far line"
        big = page.inner_text("#tmBig")
        assert "49% of trades win" in big, f"hero number: {big!r}"
        assert "2026 forward test (never used for training)" in page.inner_text("#tm .tm-hero")
        box = page.query_selector("#tmHeroSvg").bounding_box()
        assert box["width"] > 900 and box["height"] > 300, box
        print(f"  hero: {len(dots)} trial dots, coin flip, best line, big number {big.splitlines()[0]!r}")

        # The default window is the search; the whole history is one click away.
        page.click("text=Everything")
        page.wait_for_selector("#tmHeroSvg", timeout=4000)
        n_ev = len(card["events"])
        hits = page.query_selector_all("#tmHeroSvg circle.tm-hit[data-ev]")
        assert len(hits) == n_ev, f"{len(hits)} event markers for {n_ev} events"
        labels = page.query_selector_all("#tmHeroSvg text.tm-evlbl")
        assert len(labels) >= n_ev // 2, f"only {len(labels)} of {n_ev} events labelled"
        # labels on the same lane never overlap
        rects = page.eval_on_selector_all("#tmHeroSvg text.tm-evlbl",
                                          "es=>es.map(e=>{const b=e.getBBox();return [b.x,b.y,b.width,b.height]})")
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                if abs(a[1] - b[1]) < 1 and a[0] < b[0] + b[2] and b[0] < a[0] + a[2]:
                    raise AssertionError(f"event labels collide: {a} {b}")
        page.hover(f"#tmHeroSvg circle.tm-hit[data-ev='{n_ev - 1}']", force=True)
        page.wait_for_selector("#tmTip", state="visible", timeout=2000)
        assert card["events"][-1]["text"] in page.inner_text("#tmTip"), "event tooltip lacks the full text"
        print(f"  event track: {len(hits)} markers, {len(labels)} labels, no collisions, tooltip OK")

        # crosshair tooltip on the hero
        hb = page.query_selector("#tmHeroHit").bounding_box()
        page.mouse.move(hb["x"] + hb["width"] - 3, hb["y"] + hb["height"] / 2)
        page.wait_for_selector("#tmTip", state="visible", timeout=2000)
        tip = page.inner_text("#tmTip")
        assert "Trial" in tip and "success rate" in tip, f"crosshair tooltip: {tip!r}"
        page.mouse.move(2, 2)
        print("  crosshair tooltip: trial, its success rate, best so far")

        # -- forward charts: empty today ----------------------------------------------
        assert "No hourly reading yet" in (page.text_content("#tmFwdRet") or "")
        assert page.query_selector("#tmFwdDd svg"), "drawdown chart missing"

        # -- counters, how, champion -------------------------------------------------
        cnt = page.inner_text("#tmCounters").lower()
        k = card["monitor"]["counters"]
        for want in (str(k["trials"]), str(k["eligible"]), f"{k['models_fitted']:,}", "hours of search"):
            assert want in cnt, f"counters lack {want!r}"
        how = page.inner_text("#tmHow").lower()
        for want in ("trial", "seeds", "3 of 4", "walk-forward", "2022", "70%", "40 days", "never seen"):
            assert want in how, f"'how training is measured' lacks {want!r}"
        champ = page.inner_text("#tmChampion")
        assert card["monitor"]["champion_label"] in champ
        bars = page.query_selector_all("#tmChampion rect.tm-bar")
        assert len(bars) == 8, f"champion bars: {len(bars)} (want 4 years x 2)"
        for y in ("2022", "2023", "2024", "2025"):
            assert y in champ
        print("  counters, plain-words panel, champion with 4 years x 2 bars")

        if shots:
            page.click("text=Since search started")
            page.wait_for_timeout(300)
            page.screenshot(path=str(shots / "monitor_desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 900})
            page.wait_for_timeout(500)
            page.screenshot(path=str(shots / "monitor_phone.png"), full_page=True)
            page.query_selector("#tm .tm-hero").screenshot(path=str(shots / "monitor_phone_hero.png"))
            page.query_selector("#tmChampion").screenshot(path=str(shots / "monitor_phone_champion.png"))
            page.set_viewport_size({"width": 1400, "height": 1000})
            page.wait_for_timeout(400)

        # -- phone width: no horizontal page scroll ----------------------------------
        page.set_viewport_size({"width": 390, "height": 900})
        page.wait_for_timeout(500)
        sw = page.evaluate("document.documentElement.scrollWidth")
        assert sw <= 392, f"horizontal scroll at phone width: {sw}px"
        page.set_viewport_size({"width": 1400, "height": 1000})
        print("  phone width: no horizontal scroll")

        # -- with hourly readings: forward lines + stale lamp -------------------------
        withfwd = copy.deepcopy(card)
        withfwd["monitor"]["gpu"]["at"] = _iso(now - dt.timedelta(hours=3))   # -> STALE
        t0 = dt.datetime.fromisoformat(card["trial_series"][0]["at"])
        withfwd["timeline"] = [{"at": _iso(t0 + dt.timedelta(minutes=15 * i)), "trials": 10 * i,
                                "forward_2026": {"return": 0.02 * i - 0.03, "max_dd": 0.05 + 0.01 * i,
                                                 "q": 0.1, "trades": 40 + i, "win_rate": 0.48 + 0.01 * i}}
                               for i in range(4)]       # synthetic readings, test only
        feed["systems"] = with_card(withfwd)
        page.evaluate("fetchSystems()")
        page.wait_for_selector("#tmHeroSvg path.tm-fwd", timeout=6000)
        assert len(page.query_selector_all("#tmFwdRet circle.tm-fwdpt")) == 4
        assert len(page.query_selector_all("#tmFwdDd circle.tm-fwdpt")) == 4
        assert page.inner_text("#tmLampTxt") == "STALE", "an old GPU reading must read STALE"
        assert "2026 forward test: 51% win" in page.inner_text("#tmBig")
        page.hover("#tmFwdRet circle.tm-hit[data-i='3']", force=True)
        assert "Return" in page.inner_text("#tmTip")
        print("  hourly readings: 2026 line on the hero, return + drawdown charts, STALE lamp")

        # -- old deep links land on the monitor ---------------------------------------
        for old in ("#/live/theory", "#/live/diagram", "#/live/cycles"):
            page.goto(f"http://127.0.0.1:{port}/{PAGE.name}{old}")
            page.wait_for_selector("#tm #tmHeroSvg", timeout=10000)
        print("  old #/live/* links open the monitor")

        page.goto(f"http://127.0.0.1:{port}/{PAGE.name}#/strategies")
        page.wait_for_timeout(1200)
        assert page.eval_on_selector("#viewStrategies", "e=>getComputedStyle(e).display") != "none"
        browser.close()
    httpd.shutdown()

    assert not errors, "the page threw:\n  " + "\n  ".join(errors[:6])
    print("\ntraining monitor: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
