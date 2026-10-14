"""Deploy cf_worker.js to the public Workers over the Cloudflare REST API (no Node on this box).

Keeps the existing KV and secret bindings (`keep_bindings`), and makes sure the Worker has
the operator's control PIN (secret CONTROL_PIN) for the execution switch. The PIN lives in
~/.quantlab_control_pin, outside the repository; it is generated once if missing and is
never printed. Credentials come from ~/.cf_deploy_env, never from the command line.

    python research/system06/preview/cf_deploy.py
"""

from __future__ import annotations

import json
import secrets
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://api.cloudflare.com/client/v4"
PIN_FILE = Path.home() / ".quantlab_control_pin"


def env() -> dict[str, str]:
    out = {}
    for line in (Path.home() / ".cf_deploy_env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def call(method: str, url: str, token: str, body: bytes | None = None, ctype: str | None = None) -> dict:
    req = urllib.request.Request(url, data=body, method=method, headers={"Authorization": f"Bearer {token}"})
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        errs = json.loads(e.read().decode("utf-8", "replace") or "{}").get("errors", [])
        sys.exit(f"  {method} failed ({e.code}): " + "; ".join(f"[{x.get('code')}] {x.get('message')}" for x in errs))


def multipart(source: str) -> tuple[bytes, str]:
    boundary = "----quantlab" + uuid.uuid4().hex
    meta = json.dumps({"main_module": "worker.js", "compatibility_date": "2024-11-01",
                       "keep_bindings": ["kv_namespace", "secret_text"]})
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n{meta}\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n'
        f"Content-Type: application/javascript+module\r\n\r\n{source}\r\n",
        f"--{boundary}--\r\n",
    ]
    return "".join(parts).encode("utf-8"), f"multipart/form-data; boundary={boundary}"


def pin() -> str:
    if not PIN_FILE.exists():
        PIN_FILE.write_text(f"{secrets.randbelow(10**8):08d}\n", encoding="utf-8")
        print(f"  new control PIN written to {PIN_FILE} (not printed)")
    return PIN_FILE.read_text(encoding="utf-8").strip()


def main() -> None:
    e = env()
    token, acct = e["CLOUDFLARE_API_TOKEN"], e["CLOUDFLARE_ACCOUNT_ID"]
    body, ctype = multipart((HERE / "cf_worker.js").read_text(encoding="utf-8"))
    code = pin()
    for name in dict.fromkeys([e.get("PUSH_WORKER", "quantlab-public-mirror"), e.get("WORKER_NAME", "system06-lab")]):
        call("PUT", f"{API}/accounts/{acct}/workers/scripts/{name}", token, body, ctype)
        call("PUT", f"{API}/accounts/{acct}/workers/scripts/{name}/secrets", token,
             json.dumps({"name": "CONTROL_PIN", "text": code, "type": "secret_text"}).encode(), "application/json")
        print(f"  deployed {name}")


if __name__ == "__main__":
    main()
