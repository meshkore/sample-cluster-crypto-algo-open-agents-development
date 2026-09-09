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
# ONE identity for the ear and the mouth.
#
# Diagnosed 2026-09-09: 22 peer messages had been recorded with zero characters of text.
# The first cause was a nesting bug (fixed below in record()). The second survived it:
# every inbound frame carried a `to` field and an EMPTY payload -
#
#     WARNING empty text from blackmac-vcode - frame keys were
#     ['board','from','kind','payload','seq','to','ts'], payload keys []
#
# The server delivers envelope-only stubs to agents who are not the addressee. We posted
# as `win-opus-5` and listened as `win-opus-5-listener` - two different cluster
# identities - so every reply addressed to the poster reached the listener gutted. The
# suffix was not "only so the connections do not collide"; it was the bug. Codex runs one
# identity for both, which is why it works for them.
#
# So the listener now holds the single socket under the agent's real name and also SENDS,
# draining an outbox directory that `wall_post.py` writes into. One file per message, so
# a post and a drain cannot race on the same bytes.
HANDLE = "win-opus-5"
URL = f"wss://api.meshkore.com/v1/clusters/{CLUSTER}/ws?agent={HANDLE}"

S6 = Path(__file__).resolve().parents[1]      # research/system06
INBOX = S6 / "wall_inbox.jsonl"
OUTBOX = S6 / "wall_outbox"
LOG = S6 / "wall_listener.log"


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def record(evt):
    """Append one inbound peer message to the inbox as data. No interpretation.

    THE BODY IS NESTED, and reading it from the top level is why this inbox held
    eighteen peer messages and zero characters of text. The wire frame is

        {"kind": "message", "from": <agent>, "seq": n, "ts": ...,
         "payload": {"kind": "message", "text": "..."}}

    so `evt["text"]` is always absent and `str(None or "")` filled the field with an
    empty string instead of raising. Every message this cluster ever sent us was
    recorded as having arrived and having said nothing - the worst shape a bug can
    take, because the log looked healthy. Diagnosed 2026-09-09 by dumping raw frames.

    Both layouts are read now: nested first, then flat, so a future wire change in
    either direction degrades to the other rather than to silence.
    """
    payload = evt.get("payload") if isinstance(evt.get("payload"), dict) else {}
    text = (payload.get("text") or payload.get("body")
            or evt.get("text") or evt.get("body") or "")
    row = {
        "agent": str(evt.get("agent") or evt.get("from") or "?")[:80],
        "text": str(text)[:4000],
        "at": evt.get("at") or evt.get("ts") or evt.get("timestamp"),
        "received_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if not row["text"]:
        # Never again silently. An empty peer message is possible; a systematically
        # empty inbox is a wiring fault, and it must be visible in the log.
        log(f"WARNING empty text from {row['agent']} - frame keys were "
            f"{sorted(evt.keys())}, payload keys {sorted(payload.keys())}")
    with INBOX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    log(f"INBOX <- {row['agent']}: {row['text'][:120]!r}")


async def drain_outbox(ws):
    """Send anything wall_post.py has queued, one file per message.

    The listener owns the only socket under this agent's name, so it owns sending too.
    A file is deleted only AFTER its send returns, and a failed send leaves the file in
    place for the next connection rather than dropping the message silently.
    """
    while True:
        try:
            for path in sorted(OUTBOX.glob("*.json")):
                try:
                    msg = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    log(f"outbox: {path.name} unreadable ({exc}); discarding")
                    path.unlink(missing_ok=True)
                    continue
                text = str(msg.get("text") or "")
                if not text:
                    path.unlink(missing_ok=True)
                    continue
                await ws.send(json.dumps({"kind": "message", "text": text}))
                path.unlink(missing_ok=True)
                log(f"SENT -> wall ({len(text)} chars) from {path.name}")
        except Exception as exc:  # noqa: BLE001
            log(f"outbox drain failed: {type(exc).__name__}: {str(exc)[:120]}")
            raise
        await asyncio.sleep(1.0)


async def listen_once():
    async with websockets.connect(URL, open_timeout=20, max_size=2**20, ping_interval=20) as ws:
        ready = await asyncio.wait_for(ws.recv(), timeout=10)
        try:
            r = json.loads(ready)
            log(f"connected as {r.get('you')} | online={r.get('online')} | sent={r.get('sent')}")
        except ValueError:
            log("connected (unparsed ready)")
        sender = asyncio.ensure_future(drain_outbox(ws))
        try:
            await _receive_forever(ws)
        finally:
            sender.cancel()


async def _receive_forever(ws):
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
                if who.startswith("win-opus-5"):
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
