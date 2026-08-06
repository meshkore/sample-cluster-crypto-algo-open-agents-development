"""Bounded, public-safe state for the optional remote presentation layer."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


PROJECT = {
    "title": "QuantLab · Open Crypto Research",
    "tagline": "Public, reproducible research into long-only strategies.",
    "disclaimer": "Research only. Not financial advice and not live execution.",
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
    # The most recently closed trades are the useful operational view. Kept
    # tight because this payload is pushed to the edge every couple of seconds
    # and re-fetched by every viewer: 500 trades made it a third of a megabyte
    # per strategy, which is latency the live view pays for on every frame.
    result["trades"] = result.get("trades", [])[:150]
    result["equity_curve"] = _sample(result.get("equity_curve", []), 480)
    return result


def compact_public_snapshot(
    snapshot: dict[str, Any], runner: dict[str, str] | None = None
) -> dict[str, Any]:
    """Return a size-bounded, credential-free state suitable for public storage.

    `runner` identifies which machine published this snapshot. Several people
    can run the same laboratory locally at once; the edge keeps one document
    per runner rather than one shared document, and this is the tag that
    keeps their evidence from overwriting each other's.
    """
    now = datetime.now(timezone.utc).isoformat()
    state = {
        "project": {**PROJECT, "source_updated_at": now},
        "runner": runner or {"id": "default", "label": "local runner"},
        "service": snapshot.get("service"),
        "loop": snapshot.get("loop"),
        "current": snapshot.get("current"),
        "champion": snapshot.get("champion"),
        "best_unvalidated_candidate": snapshot.get("best_unvalidated_candidate"),
        "strategy": snapshot.get("strategy"),
        "current_strategy": _strategy(snapshot.get("current_strategy")),
        # The active view falls back to this while the next strategy prepares
        # signals; without it the public page blanks out between strategies.
        "last_completed_strategy": _strategy(snapshot.get("last_completed_strategy")),
        "best_strategy": _strategy(snapshot.get("best_strategy")),
        "champion_record": snapshot.get("champion_record"),
        # The research high-water mark. The champion is ranked on 2026 forward
        # evidence, so it correctly does not move when a strategy wins Phase 1
        # and then loses forward -- which means the champion alone shows no
        # research progress whatever. This was computed by the dashboard and
        # then dropped both here and in the page's own renderer, so the best
        # backtest the laboratory has produced reached no surface at all.
        "best_phase1": snapshot.get("best_phase1"),
        # The public page states the bar resolution, costs and liquidity floor
        # rather than leaving a reader to infer them from the charts.
        "market": snapshot.get("market"),
        "cluster_inbox": snapshot.get("cluster_inbox"),
        "contributions": snapshot.get("contributions"),
        "agent_pause": snapshot.get("agent_pause"),
        "activity": snapshot.get("activity"),
        "forward_2026": snapshot.get("forward_2026"),
        "data_coverage": snapshot.get("data_coverage"),
        "forward_status": snapshot.get("forward_status"),
        "last_event": snapshot.get("last_event"),
        "warning": snapshot.get("warning"),
        # Runs launched by agents, keyed by backtest_id. The champion pipeline
        # publishes exactly one strategy; this is everything anybody launched,
        # which is what a visualiser needs in order to show more than the single
        # winner. Bounded like everything else here -- the public document has a
        # size budget and an unbounded list of runs would eventually blow it.
        "backtests": _sample(snapshot.get("backtests") or [], 50),
        "limits": {
            "assets": 500,
            "trades": 150,
            "equity_points": 480,
            "backtests": 50,
        },
    }
    return _redact(state)
