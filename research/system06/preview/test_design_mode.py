"""Design mode renders, and every section is addressable by URL.

The design view belongs to whichever system is IN DEVELOPMENT (2026-09-16). System 08
closed on 2026-09-14 and the live page kept opening with its closure notice for two
days, so `_design()` now reads that flag from the registry instead of naming 08 in code.

That makes the payload here a FIXTURE rather than a snapshot of the live lab: the view
is still a real capability and still has to render, but it must be driven by a system
declared in development, not by whatever happens to be on the front page today. The
last check in this file is the new rule itself - a closed system may not take the live
view over.
"""
import json, sys, threading, http.server, functools, socket
from pathlib import Path
sys.path.insert(0, "research/system06/preview")
sys.path.insert(0, "trading-system")
import mock_server as ms

PREV = Path("research/system06/preview")
live_state = ms._state()
know = ms._knowledge()

# The fixture: system 08's design document, served as though 08 were the system in
# development. Read from disk so the assertions below still test the real content.
_home = Path("research/system08")
_design = json.loads((_home / "design.json").read_text(encoding="utf-8"))
_theory = _home / "THEORY.md"
_design["theory_md"] = _theory.read_text(encoding="utf-8") if _theory.is_file() else ""
_design["iterations"] = ms._system08_cycles()
_design["lab"] = ms._system08_lab()
state = {**live_state, "design": _design}

class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith("/api/state"): return self._j(state)
        if self.path.startswith("/api/knowledge"): return self._j(know)
        if self.path.startswith("/api/"): return self._j({})
        self.path = "/dashboard.html"
        return super().do_GET()
    def _j(self, o):
        b = json.dumps(o, default=str).encode()
        self.send_response(200); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

s = socket.socket(); s.bind(("127.0.0.1",0)); port = s.getsockname()[1]; s.close()
srv = http.server.ThreadingHTTPServer(("127.0.0.1",port),
        functools.partial(H, directory=str(PREV)))
threading.Thread(target=srv.serve_forever, daemon=True).start()

from playwright.sync_api import sync_playwright
fails = []
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page()
    base = f"http://127.0.0.1:{port}/"

    pg.goto(base); pg.wait_for_timeout(1400)
    body = pg.inner_text("#liveBody")
    up = body.upper()   # .h3 is text-transform:uppercase, so innerText is upper-cased
    if "Residual Book" not in body: fails.append("design head missing on default view")
    if "Loop idle" in body or "autonomous R&D loop" in body:
        fails.append("archived loop still rendered in Live")
    for must in ["The design this evidence justifies", "Who is on the other side"]:
        if must.upper() not in up: fails.append(f"dashboard section missing: {must}")
    print(f"  default view OK ({len(body)} chars)")

    # DESIGN PHASE GUARD (operator, 2026-09-10). The Live view carries an ARGUMENT, not a
    # result. Two things this asserts, and both have already gone wrong once:
    #   - no per-year result table of our own may render here;
    #   - every claim on the page must be traceable to a source the reader can open.
    if pg.eval_on_selector_all("table.cy tr", "r=>r.length"):
        fails.append("a per-year result table is rendering in the design view")
    # Target the removed BLOCKS, not the vocabulary — "residual" is the design's subject
    # and belongs on the page; a per-year container table and homework cards do not.
    for gone in ["container, measured with nothing", "Reject line",
                 "Who is working on what"]:
        if gone.upper() in up: fails.append(f"measured-phase block still on page: {gone}")
    links = pg.eval_on_selector_all(".est-src a", "a=>a.map(x=>x.href)")
    if len(links) < 5:
        fails.append(f"only {len(links)} sourced findings render, expected the full set")
    if not all(l.startswith("http") for l in links):
        fails.append("a source link is not a resolvable URL")
    for must in ["The question", "What the literature establishes", "How this design dies",
                 "Already ruled out"]:
        if must.upper() not in up: fails.append(f"design section missing: {must}")

    # The design is concluded, so the page must carry its CONCLUSION, not just its argument:
    # the adopted signal, the verdict on every candidate it beat, and the weakest claim on
    # the page stated as such. A design page that hides its weak link is a sales page.
    if "ADOPTED" not in up: fails.append("adopted signal not shown")
    if not pg.eval_on_selector_all(".adopted .ad-text", "e=>e.length"):
        fails.append("the adopted-signal panel does not render")
    if pg.eval_on_selector_all(".vchip.rejected", "e=>e.length") < 3:
        fails.append("rejected candidates are not shown with their verdict")
    if not pg.eval_on_selector_all(".weaklink", "e=>e.length"):
        fails.append("the design's weakest claim is not stated on the page")
    closed_cards = pg.eval_on_selector_all(".frontcard.done", "e=>e.length")
    if closed_cards < 4: fails.append(f"only {closed_cards} answered fronts render, expected 4")
    print(f"  conclusion OK (signal adopted, {closed_cards} fronts closed, weak link stated)")
    print(f"  design-phase view OK ({len(links)} sourced findings, no result tables)")

    # URL is written when a tab is chosen
    pg.click("#lt-theory"); pg.wait_for_timeout(500)
    if not pg.url.endswith("#/live/theory"): fails.append(f"theory url not written: {pg.url}")
    t = pg.inner_text("#liveBody")
    if "beta_i,t" not in t: fails.append("formula missing on theory tab")
    print(f"  theory tab -> {pg.url.split('/')[-1]}")

    pg.click("#lt-diagram"); pg.wait_for_timeout(500)
    if not pg.url.endswith("#/live/diagram"): fails.append(f"diagram url not written: {pg.url}")
    d = pg.inner_text("#liveBody")
    if "THE RESIDUAL" not in d: fails.append("residual node missing on diagram")
    if "cancels the factor" not in d: fails.append("hedge edge missing on diagram")
    print(f"  diagram tab -> {pg.url.split('/')[-1]}")

    # A link handed to another agent must OPEN on that section
    pg.goto(base + "#/live/theory"); pg.wait_for_timeout(1400)
    if "beta_i,t" not in pg.inner_text("#liveBody"):
        fails.append("deep link #/live/theory did not open theory")
    print("  deep link #/live/theory opens theory")

    pg.goto(base + "#/live/diagram"); pg.wait_for_timeout(1400)
    if "THE RESIDUAL" not in pg.inner_text("#liveBody"):
        fails.append("deep link #/live/diagram did not open diagram")
    print("  deep link #/live/diagram opens diagram")

    # CYCLES. The operator asked to open the page and see how each attempt went — the
    # backtest up to 2025 beside the sealed 2026 read — "whether the results are good or
    # bad". So the guard is that BOTH eras render for every recorded cycle, and that a
    # cycle is never dropped for being a bad one.
    pg.goto(base + "#/live/cycles"); pg.wait_for_timeout(1400)
    body = pg.inner_text("#liveBody")
    if "CYCLES" not in body.upper():
        fails.append("deep link #/live/cycles did not open the cycles view")
    cycles = pg.eval_on_selector_all(".cycle", "e=>e.length")
    recorded = len(json.loads(json.dumps(state)).get("design", {}).get("iterations", []))
    if cycles != recorded:
        fails.append(f"{cycles} cycles rendered but {recorded} are recorded — a run was "
                     f"dropped from the page")
    if cycles:
        if pg.eval_on_selector_all(".era.research", "e=>e.length") != cycles:
            fails.append("a cycle is missing its research backtest")
        if pg.eval_on_selector_all(".era.forward", "e=>e.length") != cycles:
            fails.append("a cycle is missing its sealed 2026 forward read")
        if "2026" not in body:
            fails.append("the forward year is not labelled on the cycles view")
    print(f"  cycles view OK ({cycles} recorded, both eras shown for each)")

    # THE LAB TAB. The loop records a result every few minutes and the page showed none of
    # them until 2026-09-13. Two properties are asserted because both have a way of
    # quietly regressing: every arm renders including the losers, and the DEFLATED verdict
    # travels with the t-statistic. A raw t of 3.45 has already been produced here by a
    # configuration the deflated Sharpe refuses, so a page that shows t without the
    # deflated column is how this laboratory would talk itself into adopting it.
    pg.goto(base + "#/live/lab"); pg.wait_for_timeout(1400)
    body = pg.inner_text("#liveBody")
    if "cumulative trials declared" not in body:
        fails.append("deep link #/live/lab did not open the lab view")
    exps = pg.eval_on_selector_all(".lab-exp", "e=>e.length")
    recorded = len((state.get("design", {}).get("lab", {}) or {}).get("experiments", []))
    if exps != recorded:
        fails.append(f"{exps} experiments rendered but {recorded} are recorded")
    if recorded:
        arms = pg.eval_on_selector_all(".lab-arm", "e=>e.length")
        if arms < recorded:
            fails.append(f"only {arms} arms rendered across {recorded} experiments")
        heads = pg.eval_on_selector_all(".lab-tbl th", "e=>e.map(x=>x.innerText.trim().toLowerCase())")
        if "deflated" not in heads:
            fails.append("the deflated verdict column is missing from the lab table")
        if "t" not in heads:
            fails.append("the t-statistic column is missing from the lab table")
    print(f"  lab view OK ({exps} experiments, deflated verdict shown)")

    pg.goto(base + "#/strategies"); pg.wait_for_timeout(1400)
    if pg.eval_on_selector("#viewStrategies", "e=>getComputedStyle(e).display") == "none":
        fails.append("deep link #/strategies did not open strategies")
    print("  deep link #/strategies opens strategies")
    b.close()
srv.shutdown()
if fails:
    print("\nFAIL:"); [print("  -", f) for f in fails]; sys.exit(1)
# THE RULE ITSELF: with no system flagged in development, or with the flag on a system
# that has no design document, the live view must fall through to the dashboard rather
# than to a closed system's write-up.
assert ms._system_in_development() == "system06", \
    f"expected system06 in development, got {ms._system_in_development()!r}"
assert not live_state.get("design"), \
    "a system with no design document is taking over the live view"
print("  a closed system no longer owns the live view")

print("\ndesign mode + URL routing OK")
