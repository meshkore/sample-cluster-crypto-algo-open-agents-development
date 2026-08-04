"""Public, versioned research artifacts and an opt-in Git publisher."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any


LOG = logging.getLogger(__name__)


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _summary(context: dict[str, Any]) -> dict[str, Any]:
    hypothesis, result = context["hypothesis"], context["result"]
    return {
        "iteration_id": context["iteration_id"],
        "experiment_id": context["experiment_id"],
        "strategy": f"S{int(context['strategy_number']):05d}",
        "family": hypothesis["family"],
        "side": "LONG_ONLY",
        "historical_partition": context["spec"]["training_period"],
        "forward_period": "LOCKED:2026-01-01 onward",
        "decision": context["decision"],
        "decision_reason": context["decision_reason"],
        "metrics": {
            key: result.get(key)
            for key in (
                "net_return",
                "drawdown",
                "sharpe",
                "sortino",
                "profit_factor",
                "trades",
            )
        },
        "signal_parameters": context["spec"]["parameters"],
        "execution": context["execution_policy"],
        "money_management": context["money_management"],
    }


class PublicResearchLedger:
    """Creates committed-friendly records without database or raw logs."""

    def __init__(self, research_root: Path | str):
        override = os.environ.get("QUANTLAB_PUBLIC_LEDGER_ROOT")
        self.fallback = Path(research_root) / "public"
        self.root = Path(override) if override else self.fallback
        self.degraded = False

    def write(self, context: dict[str, Any]) -> Path:
        """Write the ledger, degrading to the runtime root if the repo is denied.

        A LaunchAgent has no TCC grant for the operator's Documents folder, so a
        repository ledger root raises EPERM. Publication must never abort a
        research cycle, and the evidence must still land somewhere durable.
        """
        try:
            return self._write(context)
        except OSError as exc:
            if self.degraded or self.root == self.fallback:
                raise
            LOG.warning(
                "Public ledger root %s is not writable (%s); using %s instead",
                self.root,
                exc,
                self.fallback,
            )
            self.root, self.degraded = self.fallback, True
            return self._write(context)

    def _write(self, context: dict[str, Any]) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        record = _summary(context)
        history_path = self.root / "iterations.json"
        history = json.loads(history_path.read_text()) if history_path.exists() else []
        if not any(item["iteration_id"] == record["iteration_id"] for item in history):
            history.append(record)
            _write_json(history_path, history)
        best = max(
            history,
            key=lambda item: (
                (item["metrics"]["net_return"] or -1.0)
                - (item["metrics"]["drawdown"] or 1.0)
                + 0.05 * (item["metrics"]["sharpe"] or 0.0)
            ),
        )
        promoted = [item for item in history if item["decision"] == "PROMOTE"]
        _write_json(self.root / "current.json", record)
        _write_json(
            self.root / "best-strategy.json",
            {
                "generated_from_iterations": len(history),
                "best_provisional": best,
                "best_promoted": promoted[-1] if promoted else None,
                "forward_2026_authorized": bool(promoted),
                # This file ranks the SYNTHETIC ResearchDirector iterations
                # only -- `iterations.json` is written from that loop, whose own
                # report says it "is not evidence of tradable profit". It was
                # being read as the laboratory's best strategy, while the real
                # portfolio evidence (hundreds of runs on downloaded Binance
                # candles, walk-forward, a locked 2026 window) lives in the
                # database and is served by the dashboard API. Saying so here
                # is the honest minimum until the two are unified.
                "evidence_class": "SYNTHETIC_INFRASTRUCTURE_RUN",
                "evidence_warning": (
                    "best_provisional ranks synthetic single-series infrastructure "
                    "runs, not the real multi-asset portfolio backtests. It is not "
                    "the laboratory's best strategy and must not be read as one."
                ),
                "selection_note": "No strategy is promoted yet; the provisional score is historical research only."
                if not promoted
                else "Only the promoted strategy may be shown as a 2026 forward evaluation.",
            },
        )
        (self.root / "README.md").write_text(
            "# Public research ledger\n\nThis is a public-safe, versioned digest of completed QuantLab iterations. It excludes databases, market downloads, raw agent logs, credentials and MeshKore runtime logs.\n\n**`best_provisional` ranks SYNTHETIC infrastructure runs only** — single-series runs whose own report states they are not evidence of tradable profit. It is not this laboratory's best strategy. The real evidence is the multi-asset portfolio backtests on downloaded Binance candles, with walk-forward folds and a locked 2026 forward window, published on the dashboard.\n"
        )
        return self.root


class GitLedgerPublisher:
    """Commit only the public ledger; never let publication stop research."""

    def __init__(self, branch: str = "main", remote: str = "origin"):
        configured_root = os.environ.get("QUANTLAB_REPOSITORY_ROOT")
        self.root = Path(configured_root) if configured_root else None
        self.branch, self.remote = branch, remote

    @property
    def enabled(self) -> bool:
        return self.root is not None and (self.root / ".git").exists()

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=check,
            text=True,
            capture_output=True,
            timeout=60,
        )

    def publish(self, iteration_id: str) -> bool:
        if not self.enabled:
            return False
        artifact = "research/public"
        self._git("add", "--", artifact)
        staged = self._git("diff", "--cached", "--quiet", "--", artifact, check=False)
        if staged.returncode == 0:
            return False
        if staged.returncode != 1:
            raise RuntimeError(
                staged.stderr.strip() or "Unable to inspect ledger changes"
            )
        message = f"research: publish iteration {iteration_id}\n\nPublic-safe state only; no runtime data or credentials.\n\nAgent: master\nModel: gpt-5.6-sol\nMeshKore: py-1.32.2"
        self._git("commit", "--only", "-m", message, "--", artifact)
        self._git("push", self.remote, f"HEAD:{self.branch}")
        return True
