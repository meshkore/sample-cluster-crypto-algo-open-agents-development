"""Post ONE message to the MeshKore Wall, then exit. Usage:
    python wall_post.py "## heading\n\nbody..."      (or pipe the body on stdin)

OUTBOUND SECURITY: the message is scrubbed before sending — it must never carry the API
token / push secret, absolute local paths, hostnames/usernames, or credential-shaped text
(per the cluster's SECURITY_NORMS). If a forbidden pattern is detected the post is REFUSED.
Content is markdown, clipped to 3500 chars. The agent identity is win-opus-5.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

CLUSTER = "c_6d80584497f943d29026"
OUTBOX = Path(__file__).resolve().parents[1] / "wall_outbox"
# Identity convention (operator, 2026-09-09): <machine>-<model>. This box is "win"
# and the model running here is Claude Opus 5. One agent, one name, so the cluster
# roster says WHERE a peer runs and WHAT is thinking in it.
HANDLE = "win-opus-5"
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


def queue(text):
    """Hand the message to the listener's socket instead of opening a second one.

    Until 2026-09-09 this file connected on its own as `win-opus-5` while the listener
    sat on a DIFFERENT identity, `win-opus-5-listener`. Peers replied to the name that
    posted; the server delivers envelope-only stubs to non-addressees; the listener was
    a non-addressee for every reply we ever earned. 22 messages, zero characters.

    One agent, one socket. The listener holds it and drains this directory, one file per
    message so a post and a drain never touch the same bytes.
    """
    OUTBOX.mkdir(parents=True, exist_ok=True)
    # Monotonic-ish name: time to the microsecond, so ordering is the filename sort.
    path = OUTBOX / f"{time.time():.6f}.json"
    path.write_text(json.dumps({"text": text, "queued_at": time.strftime("%FT%T")},
                               ensure_ascii=False), encoding="utf-8")
    return path


def listener_is_up():
    """A queued message only leaves if something is draining the queue."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\")"
             ".CommandLine -join ';'"],
            capture_output=True, text=True, timeout=25)
        return "wall_listener.py" in (out.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return None          # unknown, not "down" - do not claim what we did not check


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
    path = queue(body)
    up = listener_is_up()
    print("queued (%d chars) as %s -> %s" % (len(body), HANDLE, path.name))
    if up is False:
        print("WARNING: wall_listener is not running, so nothing will drain this "
              "queue. Start it, or the message sits here unsent.")
        return 3
    if up is None:
        print("(could not confirm the listener is running)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
