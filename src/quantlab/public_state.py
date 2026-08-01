"""Bounded, public-safe state for the optional remote presentation layer."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


PROJECT = {
    "title": "QuantLab · Open Crypto Research",
    "tagline": "Investigación pública y reproducible de estrategias long-only.",
    "disclaimer": "Investigación, no asesoramiento financiero ni ejecución real.",
    "repository_url": "https://github.com/meshkore/sample-cluster-crypto-algo-open-agents-development",
    "cluster_url": "https://meshkore.com/clusters/open-crypto-algo-agents-development",
    "cluster_id": "c_6d80584497f943d29026",
    "source": "local-mac",
}

PRIVATE_KEYS = {"log_path", "traceback", "command", "credentials", "token", "secret"}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _redact(item)
            for key, item in value.items()
            if key.lower() not in PRIVATE_KEYS
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _sample(items: list[Any], maximum: int) -> list[Any]:
    """Keep endpoints and evenly spaced points for legible public charts."""
    if len(items) <= maximum:
        return items
    if maximum < 2:
        return items[-maximum:]
    step = (len(items) - 1) / (maximum - 1)
    return [items[round(index * step)] for index in range(maximum)]


def _strategy(strategy: dict[str, Any] | None) -> dict[str, Any] | None:
    if not strategy:
        return None
    result = deepcopy(strategy)
    result["assets"] = result.get("assets", [])[:500]
    # The most recently closed trades are the useful operational view.
    result["trades"] = result.get("trades", [])[:500]
    result["equity_curve"] = _sample(result.get("equity_curve", []), 720)
    return result


def compact_public_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a size-bounded, credential-free state suitable for public storage."""
    now = datetime.now(timezone.utc).isoformat()
    state = {
        "project": {**PROJECT, "source_updated_at": now},
        "service": snapshot.get("service"),
        "loop": snapshot.get("loop"),
        "current": snapshot.get("current"),
        "champion": snapshot.get("champion"),
        "best_unvalidated_candidate": snapshot.get("best_unvalidated_candidate"),
        "strategy": snapshot.get("strategy"),
        "current_strategy": _strategy(snapshot.get("current_strategy")),
        "best_strategy": _strategy(snapshot.get("best_strategy")),
        "activity": snapshot.get("activity"),
        "forward_2026": snapshot.get("forward_2026"),
        "data_coverage": snapshot.get("data_coverage"),
        "forward_status": snapshot.get("forward_status"),
        "last_event": snapshot.get("last_event"),
        "warning": snapshot.get("warning"),
        "limits": {"assets": 500, "trades": 500, "equity_points": 720},
    }
    return _redact(state)
