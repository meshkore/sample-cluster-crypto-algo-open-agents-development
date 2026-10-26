"""Publish the built pages as one static Cloudflare Worker, uploaded under each public name.

Credentials are read from ~/.cf_deploy_env (CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, WORKERS_SUBDOMAIN), outside the
repository, and are never printed.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = "https://api.cloudflare.com/client/v4"
WORKERS = ("quantlab-public-mirror", "quantlab-architecture")
ENV_FILE = Path.home() / ".cf_deploy_env"

WORKER_JS = """const PAGES = __PAGES__;
export default {
  async fetch(req) {
    let path = new URL(req.url).pathname.replace(/\\/+$/, "") || "/";
    if (path === "/live") path = "/";
    const page = PAGES[path];
    if (!page) return new Response("not found", {status: 404});
    return new Response(page[1], {headers: {"content-type": page[0], "cache-control": "public, max-age=120"}});
  }
};
"""


def _credentials() -> dict[str, str]:
    out = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def _request(method: str, url: str, token: str, body: bytes, content_type: str) -> None:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": content_type}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, method=method, headers=headers), timeout=120):
            pass
    except urllib.error.HTTPError as e:
        errors = json.loads(e.read().decode("utf-8", "replace") or "{}").get("errors", [])
        raise SystemExit(f"{method} {url.rsplit('/', 2)[-2:]} failed ({e.code}): {errors}") from None


def _script_upload(source: str) -> tuple[bytes, str]:
    boundary = "----system12" + uuid.uuid4().hex
    meta = json.dumps({"main_module": "worker.js", "compatibility_date": "2024-11-01"})
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n{meta}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n'
        f"Content-Type: application/javascript+module\r\n\r\n{source}\r\n--{boundary}--\r\n"
    )
    return body.encode("utf-8"), f"multipart/form-data; boundary={boundary}"


def deploy(pages: dict[str, tuple[str, str]]) -> list[str]:
    """`pages`: {path: (content type, body)}. Returns the public URLs."""
    env = _credentials()
    token, account = env["CLOUDFLARE_API_TOKEN"], env["CLOUDFLARE_ACCOUNT_ID"]
    body, content_type = _script_upload(WORKER_JS.replace("__PAGES__", json.dumps(pages)))
    enable = json.dumps({"enabled": True, "previews_enabled": False}).encode()
    urls = []
    for name in WORKERS:
        script = f"{API}/accounts/{account}/workers/scripts/{name}"
        _request("PUT", script, token, body, content_type)
        _request("POST", f"{script}/subdomain", token, enable, "application/json")
        urls.append(f"https://{name}.{env.get('WORKERS_SUBDOMAIN', '')}.workers.dev")
    return urls
