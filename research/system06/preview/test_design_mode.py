"""URL routing, and the rule that no design document takes over the Live view.

History: the Live view used to switch to a DESIGN MODE (design head, Theory, Diagram,
Cycles, Lab tabs) whenever the system in development published a design document. On
2026-10-01 the operator had the Live view replaced by System 10's training monitor, one
screen with no inner tabs, and the design mode was removed with it. What this file still
guards, with system 08's design served as a fixture exactly as before:
  - a design document in the state no longer takes the Live view over;
  - the old deep links (#/live/theory, /diagram, /cycles, /lab) open the monitor and the
    URL is normalised to #/live, so links already handed out keep working;
  - #/strategies still opens the strategies view;
  - a closed system is not flagged in development (the python-level rule).
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
    if pg.eval_on_selector("#viewLive", "e=>getComputedStyle(e).display") == "none":
        fails.append("the page does not open on the Live view")
    live = pg.inner_text("#viewLive")
    if "Residual Book" in live:
        fails.append("a design document took the Live view over")
    if not pg.query_selector("#viewLive #tm"):
        fails.append("the Live view lost the training monitor container")
    print("  default view = training monitor, design document ignored")

    for old in ("theory", "diagram", "cycles", "lab", "plan"):
        pg.goto(base + "#/live/" + old); pg.wait_for_timeout(900)
        if pg.eval_on_selector("#viewLive", "e=>getComputedStyle(e).display") == "none":
            fails.append(f"#/live/{old} did not open the Live view")
        if not pg.url.endswith("#/live"):
            fails.append(f"#/live/{old} was not normalised to #/live: {pg.url}")
    print("  old #/live/* deep links open the monitor at #/live")

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
