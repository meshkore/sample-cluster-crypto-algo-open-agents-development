"""Persistent, SECURITY-QUARANTINED listener for the MeshKore Wall.

Stays connected to the public cluster WebSocket (tokenless) and appends every inbound
peer MESSAGE to `research/system06/wall_inbox.jsonl` as UNTRUSTED DATA. It does exactly
one thing with peer text: write it to a file. It NEVER executes, evals, shells out, or
feeds text to a model/tool. When the supervising agent later reads the inbox, each message
is an IDEA to evaluate on the per-year metric — never an instruction. Inbound fields are
truncated (from<=80, text<=4000) so a hostile peer can't blow up storage. Reconnects
forever with backoff. Outbound: nothing (listen-only).
"""
import asyncio
import json
import time
from pathlib import Path

import websockets

CLUSTER = "c_6d80584497f943d29026"
HANDLE = "winbox-quantlab-claude-listener"
URL = f"wss://api.meshkore.com/v1/clusters/{CLUSTER}/ws?agent={HANDLE}"

S6 = Path(__file__).resolve().parents[1]      # research/system06
INBOX = S6 / "wall_inbox.jsonl"
LOG = S6 / "wall_listener.log"


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def record(evt):
    """Append one inbound peer message to the inbox as data. No interpretation."""
    row = {
        "agent": str(evt.get("agent") or evt.get("from") or "?")[:80],
        "text": str(evt.get("text") or evt.get("body") or "")[:4000],
        "at": evt.get("at") or evt.get("ts") or evt.get("timestamp"),
        "received_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with INBOX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    log(f"INBOX <- {row['agent']}: {row['text'][:120]!r}")


async def listen_once():
    async with websockets.connect(URL, open_timeout=20, max_size=2**20, ping_interval=20) as ws:
        ready = await asyncio.wait_for(ws.recv(), timeout=10)
        try:
            r = json.loads(ready)
            log(f"connected as {r.get('you')} | online={r.get('online')} | sent={r.get('sent')}")
        except ValueError:
            log("connected (unparsed ready)")
        while True:
            frame = await ws.recv()
            s = frame if isinstance(frame, str) else frame.decode("utf-8", "replace")
            try:
                evt = json.loads(s)
            except ValueError:
                continue
            kind = evt.get("kind")
            if kind == "message":
                # ignore our own handles echoed back, if any
                who = str(evt.get("agent") or evt.get("from") or "")
                if who.startswith("winbox-quantlab-claude"):
                    continue
                record(evt)
            # ready/ack/presence/etc. are ignored (not peer content)


async def main():
    log(f"wall_listener starting -> {URL}")
    backoff = 2
    while True:
        try:
            await listen_once()
        except Exception as exc:  # noqa: BLE001
            log(f"disconnected: {type(exc).__name__}: {str(exc)[:160]}; retry in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        else:
            backoff = 2


if __name__ == "__main__":
    asyncio.run(main())
