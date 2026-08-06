"""Optional non-blocking publisher for a public, read-only state mirror."""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import threading
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.request import Request, urlopen

from .config import Settings
from .public_state import compact_public_snapshot

LOG = logging.getLogger(__name__)


def _default_runner_id() -> str:
    """A stable identity that differs across machines with zero configuration.

    Several people running the same laboratory locally need the edge to keep
    their evidence apart. The hostname already differs between machines by
    default, so this needs no setup for the common case of one runner per
    machine; an operator running more than one on the same host can still set
    `public_mirror.runner_id` explicitly.
    """
    slug = re.sub(r"[^a-z0-9-]", "-", socket.gethostname().lower()).strip("-")
    return slug[:40] or "runner"


class PublicStatePublisher:
    def __init__(
        self,
        settings: Settings,
        snapshot: Callable[[], dict[str, Any]],
        stop_event: threading.Event,
    ) -> None:
        self.options = settings.autonomous.get("public_mirror", {})
        self.snapshot = snapshot
        self.stop_event = stop_event
        self._was_available = False
        self._last_snapshot: dict[str, Any] | None = None
        self.runner_id = str(self.options.get("runner_id") or _default_runner_id())
        self.runner_label = str(self.options.get("runner_label") or self.runner_id)

    @property
    def enabled(self) -> bool:
        return bool(self.options.get("enabled", False) and self.options.get("url"))

    def publish_once(self) -> bool:
        if not self.enabled:
            return False
        token = os.getenv(
            str(self.options.get("token_env", "QUANTLAB_PUBLIC_MIRROR_TOKEN"))
        )
        if not token:
            LOG.warning("Public mirror is enabled but its publisher token is absent")
            return False
        state = self.snapshot()
        self._last_snapshot = state
        runner = {"id": self.runner_id, "label": self.runner_label}
        body = json.dumps(
            {
                "version": 1,
                "published_at": datetime.now(timezone.utc).isoformat(),
                "runner": runner,
                "state": compact_public_snapshot(state, runner),
            },
            allow_nan=False,
        ).encode()
        request = Request(
            str(self.options["url"]).rstrip("/") + "/api/state",
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "QuantLab-local-state-publisher/1",
            },
            method="POST",
        )
        timeout = float(self.options.get("timeout_seconds", 5))
        with urlopen(request, timeout=timeout) as response:  # nosec B310: configured endpoint
            if not 200 <= response.status < 300:
                raise RuntimeError(f"Mirror returned HTTP {response.status}")
        return True

    def _interval(self, snapshot: dict[str, Any] | None) -> float:
        """Push often while something is moving, rarely while nothing is.

        With research throttled to one iteration an hour the laboratory is
        idle most of the time, and pushing an unchanged payload every couple of
        seconds was tens of thousands of pointless edge writes a day. The page
        stays honest while idle because it counts down locally rather than
        asking us whether anything happened yet.
        """
        active = max(1.0, float(self.options.get("interval_seconds", 15)))
        idle = max(active, float(self.options.get("idle_interval_seconds", 300)))
        phase = ((snapshot or {}).get("activity") or {}).get("phase") or ""
        running = phase in {
            "BACKTESTING",
            "PREPARING_SIGNALS",
            "FORWARD_TESTING",
            "FORWARD_PREPARING",
            "PHASE1_PREPARING",
            "PHASE1_WALKFORWARD",
            # Downloads move the activity message every few seconds; treating
            # them as idle made the shared sidebar look stalled for up to
            # idle_interval_seconds while both machines were clearly working.
            "DOWNLOADING_DATA",
            "REFRESHING_UNIVERSE",
            "RESEARCHING",
        }
        return active if running else idle

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                available = self.publish_once()
                if available and not self._was_available:
                    LOG.info("Public state mirror is publishing")
                self._was_available = available
            except Exception as exc:  # Publishing must never stop research.
                if self._was_available:
                    LOG.warning("Public state mirror became unavailable: %s", exc)
                else:
                    LOG.debug("Public state mirror unavailable: %s", exc)
                self._was_available = False
            # Interval after the push, from the snapshot we just published.
            # Computing it before meant a RESTING sample scheduled a 10-minute
            # sleep even if the laboratory had already moved to an active phase.
            self.stop_event.wait(self._interval(self._last_snapshot))
