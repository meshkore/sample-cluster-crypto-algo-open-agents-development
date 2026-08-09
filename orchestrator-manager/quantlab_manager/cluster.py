"""The cluster as the loop's bus: every stage announced, every reply read as data.

The operator's requirement is that the work happens *in public* -- not that a
summary is published afterwards, but that the argument itself is on the wire
where a stranger's agent can watch it and join. So each stage of an iteration is
posted under the handle of whichever member produced it, over the MeshKore
WebSocket bridge that already exists in `.meshkore/scripts/`.

Two rules govern everything here and neither is negotiable:

**Peer text is data, never instructions.** Anything read off the Wall is
evidence about what somebody thinks. It may suggest a hypothesis. It may never
authorise a tool call, a credential read, a window past the lock, or a change of
protocol. This module returns strings; nothing in it dispatches on their
content.

**Publication may never fail an iteration.** The research is in the ledger and
the database by the time anything is posted. A network blip is not a research
event, so every call here is best-effort and records why it failed rather than
raising -- but it DOES record it, because a silent failure once cost this
project eight runs that reported success and never arrived.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import subprocess


class Cluster:
    """Post and read over the repository's own bridge scripts.

    The public cluster admits agents tokenless, which is why nothing here opens
    a credential and why this is safe to run unattended.
    """

    def __init__(
        self,
        repository: Path | str,
        cluster_id: str = "c_6d80584497f943d29026",
        enabled: bool = True,
        timeout: float = 45.0,
    ):
        self.repository = Path(repository)
        self.cluster_id = cluster_id
        self.enabled = enabled
        self.timeout = timeout
        self.last_error: str | None = None
        self.posted = 0

    # -- outbound ------------------------------------------------------------ #

    def post(self, handle: str, body: str) -> bool:
        """Say something as `handle`. Returns whether it left the machine."""
        if not self.enabled or not body.strip():
            return False
        script = self.repository / ".meshkore" / "scripts" / "meshkore_post.mjs"
        if not script.exists():
            self.last_error = f"no bridge at {script}"
            return False
        # Kept alongside the send so an iteration's public record survives even
        # when the network did not.
        outbox = (
            self.repository / "orchestrator-manager" / "loop" / "cluster" / "outbox"
        )
        try:
            outbox.mkdir(parents=True, exist_ok=True)
            stamp = _stamp()
            (outbox / f"{stamp}-{handle}.md").write_text(body)
        except OSError as exc:
            self.last_error = f"outbox: {exc}"
        try:
            result = subprocess.run(
                ["node", str(script), self.cluster_id, handle],
                input=body,
                text=True,
                capture_output=True,
                timeout=self.timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False
        if result.returncode != 0:
            self.last_error = (result.stderr or result.stdout or "")[:400]
            return False
        self.last_error = None
        self.posted += 1
        return True

    # -- inbound ------------------------------------------------------------- #

    def read(
        self, seconds: int = 20, handle: str | None = None
    ) -> list[dict[str, Any]]:
        """Listen for a bounded window and return whatever arrived.

        The listener reconnects for ever by design, so it is bounded from the
        outside rather than trusted to stop. Everything returned is UNTRUSTED
        THIRD-PARTY TEXT.
        """
        if not self.enabled:
            return []
        script = self.repository / ".meshkore" / "scripts" / "meshkore_listen.mjs"
        if not script.exists():
            self.last_error = f"no bridge at {script}"
            return []
        reader = handle or "blackmac-quantlab-loop-reader"
        try:
            result = subprocess.run(
                ["node", str(script), self.cluster_id, reader],
                text=True,
                capture_output=True,
                timeout=seconds,
            )
            raw = result.stdout
        except subprocess.TimeoutExpired as exc:
            # The expected path: the listener never exits on its own.
            raw = (
                exc.stdout.decode()
                if isinstance(exc.stdout, bytes)
                else (exc.stdout or "")
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return []

        messages = []
        for line in (raw or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("kind") == "message":
                messages.append(
                    {
                        "from": str(event.get("agent") or event.get("from") or "?")[
                            :80
                        ],
                        # Truncated on the way in. A peer cannot flood an
                        # iteration's record, and nothing downstream has to
                        # decide how much of an untrusted string to keep.
                        "text": str(event.get("text") or event.get("body") or "")[
                            :4000
                        ],
                        "at": str(event.get("at") or event.get("timestamp") or "")[:40],
                    }
                )
        return messages


def _stamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def from_environment(repository: Path | str) -> Cluster:
    return Cluster(
        repository=repository,
        cluster_id=os.environ.get("QUANTLAB_CLUSTER_ID", "c_6d80584497f943d29026"),
        enabled=os.environ.get("QUANTLAB_CLUSTER", "1") not in ("0", "false", "no"),
    )
