"""Optional non-blocking publisher for a public, read-only state mirror."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.request import Request, urlopen

from .config import Settings
from .public_state import compact_public_snapshot

LOG = logging.getLogger(__name__)


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
        body = json.dumps(
            {
                "version": 1,
                "published_at": datetime.now(timezone.utc).isoformat(),
                "state": compact_public_snapshot(self.snapshot()),
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

    def run(self) -> None:
        interval = max(1.0, float(self.options.get("interval_seconds", 5)))
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
            self.stop_event.wait(interval)
