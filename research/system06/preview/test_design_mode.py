"""Design mode renders, and every section is addressable by URL."""
import json, sys, threading, http.server, functools, socket
from pathlib import Path
sys.path.insert(0, "research/system06/preview")
sys.path.insert(0, "trading-system")
import mock_server as ms

PREV = Path("research/system06/preview")
state = ms._state(); know = ms._knowledge()

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
    for must in ["The claim", "Who is on the other side", "How this dies",
                 "Who is working on what"]:
        if must.upper() not in up: fails.append(f"dashboard section missing: {must}")
    for who in ["blackmac-gpt6", "blackmac-fable5", "PWMAC-GROC-4.6"]:
        if who not in body: fails.append(f"homework agent missing: {who}")
    print(f"  default view OK ({len(body)} chars)")

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

    pg.goto(base + "#/strategies"); pg.wait_for_timeout(1400)
    if pg.eval_on_selector("#viewStrategies", "e=>getComputedStyle(e).display") == "none":
        fails.append("deep link #/strategies did not open strategies")
    print("  deep link #/strategies opens strategies")
    b.close()
srv.shutdown()
if fails:
    print("\nFAIL:"); [print("  -", f) for f in fails]; sys.exit(1)
print("\ndesign mode + URL routing OK")
