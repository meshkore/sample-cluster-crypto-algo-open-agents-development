"""Bridge the LOCAL autoloop's live state to the public Cloudflare Worker.

The dashboard is served by the `system06-lab` Worker from KV; this pusher runs on the
machine with the autoloop and POSTs the SAME JSON that `mock_server` serves locally
(state, knowledge, per-card detail, and the page HTML) to the Worker's /api/push with a
bearer secret. It publishes ONLY the curated public surface — never tokens, raw datasets
or logs. Read-only on the loop's files.

Run detached (PowerShell Start-Process). Reads the push secret from the local env file.
"""
import hashlib
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

PREVIEW = Path(__file__).resolve().parent
sys.path.insert(0, str(PREVIEW))
import mock_server as ms  # noqa: E402

ENV_FILE = Path.home() / ".cf_deploy_env"
env = {}
for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k] = v

SUB = env.get("WORKERS_SUBDOMAIN", "rjj")
# PUSH_WORKER lets the pusher target the operator's canonical shared URL
# (quantlab-public-mirror) directly, independent of WORKER_NAME (which the
# deploy script uses for the system06-lab worker). Both workers bind the same
# KV namespace, so either target updates both URLs; we push to the canonical one.
WORKER = env.get("PUSH_WORKER", env.get("WORKER_NAME", "system06-lab"))
PUSH_URL = f"https://{WORKER}.{SUB}.workers.dev/api/push"
SECRET = env["PUSH_SECRET"]

STATE_EVERY = 8.0      # seconds between state pushes (live freshness vs KV write budget)
LOG = ms.S6 / "cf_pusher.log"


def _hash(obj):
    return hashlib.md5(json.dumps(obj, default=str, sort_keys=True).encode()).hexdigest()


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def build_details(state):
    ids = []
    if state.get("best"):
        ids.append("best")
    for c in state.get("history", []):
        if c.get("id"):
            ids.append(c["id"])
    details = {}
    for cid in ids:
        try:
            d = ms._detail(cid)
            if d:
                details[cid] = d
        except Exception as exc:  # noqa: BLE001
            log(f"detail {cid} failed: {exc}")
    return details


def push(payload):
    data = json.dumps(payload, default=str).encode("utf-8")
    req = urllib.request.Request(PUSH_URL, data=data, method="POST")
    req.add_header("Authorization", "Bearer " + SECRET)
    req.add_header("Content-Type", "application/json")
    # Cloudflare's edge 403s the default Python-urllib UA; use a normal one.
    req.add_header("User-Agent", "Mozilla/5.0 (system06-cf-pusher)")
    r = urllib.request.urlopen(req, timeout=25)
    return json.load(r), len(data)


def read_page():
    try:
        return ms.DASH.read_text(encoding="utf-8")
    except OSError:
        return None


def main():
    log(f"cf_pusher starting -> {PUSH_URL}")
    # Only `state` is written every cycle (it genuinely changes with the live loop);
    # knowledge / details / page are written ONLY when their content changes, to keep
    # KV writes modest. Hashes seed as None so the first cycle publishes everything.
    h_know = h_det = h_page = None
    page_mtime = 0
    n = 0
    while True:
        n += 1
        try:
            state = ms._state()
            payload = {"state": state}
            changed = ["state"]

            know = ms._knowledge()
            hk = _hash(know)
            if hk != h_know:
                payload["knowledge"] = know; h_know = hk; changed.append("knowledge")

            # details recompute is a bit heavier; only every 3rd cycle, and only push on change
            if n % 3 == 1:
                det = build_details(state)
                hd = _hash(det)
                if hd != h_det:
                    payload["details"] = det; h_det = hd; changed.append("details")

            if ms.DASH.is_file():
                mt = ms.DASH.stat().st_mtime
                if mt != page_mtime:
                    page = read_page()
                    hp = _hash(page)
                    if hp != h_page:
                        payload["page"] = page; h_page = hp; changed.append("page")
                    page_mtime = mt

            res, nbytes = push(payload)
            if len(changed) > 1 or n == 1:
                log(f"pushed {changed} ({nbytes} bytes) ok={res.get('ok')}")
        except urllib.error.HTTPError as e:
            log(f"push HTTPError {e.code}: {e.read()[:200]}")
        except Exception as exc:  # noqa: BLE001
            log(f"push failed: {type(exc).__name__} {exc}")
        time.sleep(STATE_EVERY)


if __name__ == "__main__":
    main()
