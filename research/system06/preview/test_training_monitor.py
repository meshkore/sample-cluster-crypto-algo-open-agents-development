"""The Live view is System 10's mission-control monitor - rendered from real data shapes.

Operator, 2026-10-10: "remove the text and the long explanations... I glance at it whenever
I pass by and know the state of all this work". The view (renderMonitor in dashboard.html)
is four bands of instruments fed by two sources:

  - state.s10_live (polled): fixtures/training_monitor/live_status.sample.json is a real
    sample of research/system10/rnd/live_status.json
  - the system-10 model card from the registry: fixtures/training_monitor/system10/ is a
    COPY of the real card, read through `mock_server._system_model_card`

Asserted, in a real browser:
  - NOW: headline, phase lamps, one chip per job (+ RL) with `doing` in the tooltip, and a
    freshness lamp that ticks every second: LIVE < 60 s, LAGGING < 5 min, STALE beyond
  - MACHINE: CPU (+ 12 core bars), GPU, memory, network, disk, temperature, sparklines
  - RESULTS: best backtest (worst year, 4 year bars, max-profit row) and 2026 forward
    (return, release, hourly sparkline)
  - PROGRESS: counters, success rate over time (one dot per trial), event track
  - s10_live = null renders a clear "no live data" state; [?] shows a tooltip
  - 390 px: no horizontal scroll; old deep links land on the monitor; no console errors

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
LIVE_SAMPLE = FIXTURES / "live_status.sample.json"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def _serve(directory: pathlib.Path):
    handler = functools.partial(_Quiet, directory=str(directory))
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
    assert {r["best_win_rate"] for r in long} <= {r["best_win_rate"] for r in thin}, \
        "thinning dropped a step of the best line"

    live = json.loads(LIVE_SAMPLE.read_text(encoding="utf-8"))
    assert len(json.dumps(live)) < 60_000, "the live status payload is too large"
    now = dt.datetime.now(dt.timezone.utc)
    live["at"] = _iso(now)

    systems = mock_server._systems()
    for s in systems:
        if s.get("id") == "system10":
            s["model_card"] = card
    state = mock_server._state()
    state["s10_live"] = live
    feed = {"state": state}

    errors: list[str] = []
    httpd, port = _serve(PAGE.parent)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda m: errors.append(m.text)
                if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/api/state", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(feed["state"], default=str)))
        page.route("**/api/detail**", lambda r: r.fulfill(
            status=200, content_type="application/json", body="{}"))
        page.route("**/api/systems", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(systems, default=str)))
        for route in ("**/api/knowledge", "**/api/iterations"):
            page.route(route, lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))

        def set_live(obj):
            st = copy.deepcopy(state)
            st["s10_live"] = obj
            feed["state"] = st
            page.evaluate("poll()")
            page.wait_for_timeout(400)

        page.goto(f"http://127.0.0.1:{port}/{PAGE.name}#/live")
        page.wait_for_selector("#tm #tmHeroSvg", timeout=10000)
        page.wait_for_selector("#tmJobs", timeout=10000)
        assert page.eval_on_selector("#viewLive", "e=>getComputedStyle(e).display") != "none"

        # -- NOW -----------------------------------------------------------------------
        assert page.inner_text("#tmHeadline") == live["headline"]
        assert "LIVE" in page.inner_text("#tmLampTxt")
        assert "live" in page.get_attribute("#tmLamp", "class")
        age1 = page.inner_text("#tmLampAge")
        assert age1.startswith("updated") and "s ago" in age1, age1
        page.wait_for_timeout(2200)
        assert page.inner_text("#tmLampAge") != age1, "the freshness clock does not tick"
        chips = page.query_selector_all("#tmJobs .tm-job[data-job]")
        assert [c.get_attribute("data-job") for c in chips] == [j["job"] for j in live["jobs"]]
        w3 = page.get_attribute("#tmJobs .tm-job[data-job='w3']", "data-tip")
        assert "testing config fdec994d8c" in w3, w3
        assert "running" in page.get_attribute("#tmJobs .tm-job[data-job='w3']", "class")
        assert "loading" in page.get_attribute("#tmJobs .tm-job[data-job='w1']", "class")
        assert "ON HOLD" in page.inner_text("#tmRl")
        phases = page.inner_text("#tmPhases")
        for want in ("TRAIN", "RL", "BACKTEST", "EVALUATE", "FORWARD 2026", "2/4 workers"):
            assert want in phases, f"phase lamps lack {want!r}: {phases!r}"
        print(f"  NOW: headline, LIVE lamp ticking ({age1!r}), {len(chips)} job chips + RL, phase lamps")

        # -- MACHINE -------------------------------------------------------------------
        assert "59" in page.inner_text("#tmCpu")
        assert len(page.query_selector_all("#tmCores b")) == 12
        assert "42" in page.inner_text("#tmGpu")
        assert "4.7" in page.inner_text("#tmGpuMem") and "8.0 GB" in page.inner_text("#tmGpuMem")
        assert "27.7" in page.inner_text("#tmRam")
        assert "62.8" in page.inner_text("#tmNetDn") and "6.9" in page.inner_text("#tmNetUp")
        assert "1.6" in page.inner_text("#tmDisk") and "48" in page.inner_text("#tmTemp")
        sparks = page.query_selector_all("#tmMachine .tm-spark path.ln")
        assert len(sparks) == 6, f"{len(sparks)} machine sparklines (want 6)"
        print("  MACHINE: CPU + 12 cores, GPU, GPU mem, RAM, net, disk, temp; 6 sparklines")

        # -- RESULTS -------------------------------------------------------------------
        assert page.inner_text("#tmBestWorst").startswith("+2.3%")
        assert "CHAMPION" in page.inner_text("#tmBest")
        assert len(page.query_selector_all("#tmYears rect.tm-bar")) == 4
        for y in ("2022", "2023", "2024", "2025"):
            assert y in page.inner_text("#tmBest")
        mp = page.inner_text("#tmMaxProfit")
        assert "+12.7%" in mp and "−18.4%" in mp, mp
        assert page.inner_text("#tmFwdRet").startswith("+27.2%")
        assert "RELEASE #27" in page.inner_text("#tmForward")
        assert page.query_selector("#tmFwdSpark path.ln"), "no 2026 sparkline"
        assert "+68.8%" in page.inner_text("#tmFwdBest")
        assert "01/10/2026" in page.inner_text("#tmFwdSpark"), "dates must read dd/mm/yyyy"
        print("  RESULTS: best backtest + 4 year bars + max profit; 2026 forward + series + best reading")

        # -- PROGRESS ------------------------------------------------------------------
        cnt = page.inner_text("#tmCounters")
        for want in ("5,982", "369", "166", "317", "27"):
            assert want in cnt, f"counters lack {want!r}: {cnt!r}"
        n_trials = len([r for r in card["trial_series"] if r.get("win_rate") is not None])
        page.click("#tmProgress .tm-seg:has-text('All')")
        page.wait_for_selector("#tmHeroSvg", timeout=4000)
        dots = page.query_selector_all("#tmHeroSvg circle.tm-trial")
        assert len(dots) == n_trials, f"{len(dots)} trial dots for {n_trials} trials"
        assert page.query_selector("#tmHeroSvg line.tm-ref") and page.query_selector("#tmHeroSvg path.tm-fwd")
        n_ev = len(card["events"])
        assert len(page.query_selector_all("#tmHeroSvg circle.tm-hit[data-ev]")) == n_ev
        labels = page.query_selector_all("#tmHeroSvg text.tm-evlbl")
        assert labels, "no event labelled"
        rects = page.eval_on_selector_all("#tmHeroSvg text.tm-evlbl",
                                          "es=>es.map(e=>{const b=e.getBBox();return [b.x,b.y,b.width,b.height]})")
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                if abs(a[1] - b[1]) < 1 and a[0] < b[0] + b[2] and b[0] < a[0] + a[2]:
                    raise AssertionError(f"event labels collide: {a} {b}")
        page.hover(f"#tmHeroSvg circle.tm-hit[data-ev='{n_ev - 1}']", force=True)
        page.wait_for_selector("#tmTip", state="visible", timeout=2000)
        assert card["events"][-1]["text"] in page.inner_text("#tmTip")
        page.mouse.move(2, 2)
        print(f"  PROGRESS: counters, {len(dots)} trial dots, {n_ev} events, {len(labels)} labels, tooltip")

        # -- [?] tooltip ---------------------------------------------------------------
        page.hover("#tmBest .tm-q")
        page.wait_for_selector("#tmTip", state="visible", timeout=2000)
        assert "never trained on" in page.inner_text("#tmTip")
        page.mouse.move(2, 2)
        assert "how training is measured" not in page.inner_text("#tm").lower()
        print("  [?] tooltips carry the explanations; no prose panel")

        if shots:
            shots.mkdir(parents=True, exist_ok=True)
            page.click("#tmProgress .tm-seg:has-text('Search')")
            page.wait_for_timeout(300)
            page.screenshot(path=str(shots / "monitor_desktop_1440.png"), full_page=True)

        # -- phone width ---------------------------------------------------------------
        page.set_viewport_size({"width": 390, "height": 900})
        page.wait_for_timeout(600)
        sw = page.evaluate("document.documentElement.scrollWidth")
        assert sw <= 392, f"horizontal scroll at phone width: {sw}px"
        if shots:
            page.screenshot(path=str(shots / "monitor_phone_390.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.wait_for_timeout(300)
        print("  390 px: no horizontal scroll")

        # -- freshness states ----------------------------------------------------------
        lag = copy.deepcopy(live); lag["at"] = _iso(now - dt.timedelta(minutes=2))
        set_live(lag)
        assert "LAGGING" in page.inner_text("#tmLampTxt")
        assert "lag" in page.get_attribute("#tmLamp", "class")
        old = copy.deepcopy(live); old["at"] = _iso(now - dt.timedelta(minutes=12))
        set_live(old)
        assert "STALE" in page.inner_text("#tmLampTxt"), page.inner_text("#tmLampTxt")
        assert "stale" in page.get_attribute("#tmLamp", "class")
        assert "min" in page.inner_text("#tmLampAge")
        print("  freshness: LAGGING at 2 min, STALE at 12 min")

        # -- no live data --------------------------------------------------------------
        set_live(None)
        assert page.inner_text("#tmHeadline") == "No live data"
        assert "NO DATA" in page.inner_text("#tmLampTxt")
        assert "No machine reading" in page.inner_text("#tmMachine")
        assert page.query_selector("#tmHeroSvg"), "the progress chart must survive without live data"
        if shots:
            page.screenshot(path=str(shots / "monitor_no_live_1440.png"), full_page=False)
        print("  s10_live = null: 'No live data', NO DATA lamp, progress chart still drawn")

        # -- old deep links land on the monitor ----------------------------------------
        for link in ("#/live/theory", "#/live/diagram", "#/live/cycles"):
            page.goto(f"http://127.0.0.1:{port}/{PAGE.name}{link}")
            page.wait_for_selector("#tm #tmNow", timeout=10000)
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
