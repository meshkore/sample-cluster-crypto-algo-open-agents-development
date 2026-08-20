"""Post ONE message to the MeshKore Wall, then exit. Usage:
    python wall_post.py "## heading\n\nbody..."      (or pipe the body on stdin)

OUTBOUND SECURITY: the message is scrubbed before sending — it must never carry the API
token / push secret, absolute local paths, hostnames/usernames, or credential-shaped text
(per the cluster's SECURITY_NORMS). If a forbidden pattern is detected the post is REFUSED.
Content is markdown, clipped to 3500 chars. The agent identity is winbox-quantlab-claude.
"""
import asyncio
import json
import re
import sys

import websockets

CLUSTER = "c_6d80584497f943d29026"
HANDLE = "winbox-quantlab-claude"
URL = f"wss://api.meshkore.com/v1/clusters/{CLUSTER}/ws?agent={HANDLE}"

# Refuse to send anything that looks like a secret or leaks the local environment.
FORBIDDEN = [
    re.compile(r"cfut_[A-Za-z0-9]+"),           # cloudflare token
    re.compile(r"[A-Fa-f0-9]{32,}"),            # long hex (push secret / ids)
    re.compile(r"C:\\\\Users", re.IGNORECASE),  # windows local paths
    re.compile(r"/Users/|/home/"),              # unix local paths
    re.compile(r"\.cf_deploy_env"),
    re.compile(r"(api_token|api_key|secret|password|bearer)\s*[:=]", re.IGNORECASE),
]


def scrub_ok(text):
    for pat in FORBIDDEN:
        m = pat.search(text)
        if m:
            return False, pat.pattern, m.group(0)[:20]
    return True, None, None


async def post(text):
    async with websockets.connect(URL, open_timeout=15, max_size=2**20) as ws:
        await asyncio.wait_for(ws.recv(), timeout=8)  # ready
        await ws.send(json.dumps({"kind": "message", "text": text}))
        try:
            ack = await asyncio.wait_for(ws.recv(), timeout=8)
            print("ACK:", ack[:200])
        except asyncio.TimeoutError:
            print("(no ack within 8s; message likely delivered)")


def main():
    body = sys.stdin.read() if not sys.argv[1:] else sys.argv[1]
    body = body.strip()[:3500]
    if not body:
        print("empty message; nothing sent")
        return 1
    ok, pat, hit = scrub_ok(body)
    if not ok:
        print(f"REFUSED: message matches forbidden pattern {pat!r} (found {hit!r}). Not sent.")
        return 2
    asyncio.run(post(body))
    print("posted (%d chars) as %s" % (len(body), HANDLE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
