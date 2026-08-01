from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .public_ledger import GitLedgerPublisher, PublicResearchLedger


def _yaml_like(data: dict[str, Any]) -> str:
    return "```json\n" + json.dumps(data, indent=2, sort_keys=True) + "\n```\n"


class Reporter:
    def __init__(self, research_root: Path | str):
        self.root = Path(research_root)
        self.ledger = PublicResearchLedger(research_root)
        self.publisher = GitLedgerPublisher()

    def write_iteration(self, iteration_id: str, context: dict[str, Any]) -> Path:
        final = self.root / "iterations" / iteration_id
        temporary = self.root / "iterations" / f".{iteration_id}.tmp"
        if final.exists():
            return final
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(parents=True, exist_ok=False)
        hypothesis, result = context["hypothesis"], context["result"]
        strategy_label = f"S{int(context['strategy_number']):05d}"
        (temporary / "strategy.md").write_text(
            f"# Strategy {strategy_label}\n\n"
            "## Signal criteria\n\n"
            + _yaml_like(
                {
                    "family": hypothesis["family"],
                    "features": hypothesis["features"],
                    "trigger": hypothesis["trigger"],
                    "entry_logic": hypothesis["entry_logic"],
                    "exit_logic": hypothesis["exit_logic"],
                    "parameters": context["spec"]["parameters"],
                }
            )
            + "\n## Execution\n\n"
            + _yaml_like(context["execution_policy"])
            + "\n## Money management\n\n"
            + _yaml_like(context["money_management"])
        )
        (temporary / "hypothesis.md").write_text(
            "# Hypothesis\n\n" + _yaml_like(hypothesis)
        )
        (temporary / "sources.md").write_text(
            "# Sources\n\nNo external source was used in this offline infrastructure cycle.\n"
        )
        (temporary / "design.md").write_text(
            "# Design\n\nSignal is calculated at bar close and filled at the next bar open. "
            "This run uses the development partition only.\n\n"
            + _yaml_like(context["spec"])
        )
        (temporary / "implementation.md").write_text(
            "# Implementation\n\nDeterministic built-in strategy family and next-open engine v1. "
            "Costs are engine-owned and applied on every position change.\n"
        )
        (temporary / "results.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
        (temporary / "critique.md").write_text(
            "# Adversarial critique\n\n" + _yaml_like(context["critic"])
        )
        decision = context["decision"]
        (temporary / "decision.md").write_text(
            f"# Decision: {decision}\n\n{context['decision_reason']}\n"
        )
        (temporary / "report.md").write_text(
            f"# Iteration {iteration_id} · Strategy {strategy_label}\n\n"
            f"Family: `{hypothesis['family']}`  \nDataset: `{context['dataset_version']}`  \n"
            f"Net return: `{result['net_return']:.6f}`  \nSharpe: `{result['sharpe']:.3f}`  \n"
            f"Max drawdown: `{result['drawdown']:.3f}`  \nTrades: `{result['trades']}`  \n\n"
            "This is a synthetic infrastructure run and is not evidence of tradable profit.\n"
        )
        temporary.replace(final)
        self._update_global_memory(iteration_id, context)
        self.ledger.write(context)
        try:
            self.publisher.publish(iteration_id)
        except (OSError, subprocess.SubprocessError, RuntimeError):
            # A network or Git credential failure must not invalidate research.
            pass
        return final

    def _update_global_memory(self, iteration_id: str, context: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        strategy_label = f"S{int(context['strategy_number']):05d}"
        (self.root / "STATE.md").write_text(
            "# State\n\n"
            f"Last completed iteration: `{iteration_id}`\n"
            f"Last decision: `{context['decision']}`\n"
            f"Last experiment: `{context['experiment_id']}`\n\n"
            "Runtime checkpoint remains authoritative in `research/quantlab.db`.\n"
        )
        failure_path = self.root / "FAILURES.md"
        existing = failure_path.read_text() if failure_path.exists() else "# Failures\n"
        marker = f"`{context['experiment_id']}`"
        if context["decision"] == "REJECT" and marker not in existing:
            existing += f"\n- {marker}: {context['decision_reason']}\n"
            failure_path.write_text(existing)
        (self.root / "NEXT_EXPERIMENTS.md").write_text(
            "# Next experiments\n\n"
            f"1. Retest `{context['hypothesis']['family']}` on audited point-in-time exchange data.\n"
            "2. Run cost, delay, parameter-surface and best-trade-removal stresses.\n"
            "3. Validate on assets and regimes excluded from design.\n"
        )
        strategies_path = self.root / "STRATEGIES.md"
        strategies = (
            strategies_path.read_text()
            if strategies_path.exists()
            else "# Strategy registry\n"
        )
        marker = f"## {strategy_label}"
        if marker not in strategies:
            strategies += (
                f"\n{marker}\n\n- Family: `{context['hypothesis']['family']}`\n"
                f"- Experiment: `{context['experiment_id']}`\n- Side: `LONG_ONLY`\n"
                f"- Decision: `{context['decision']}`\n"
                f"- Parameters: `{json.dumps(context['spec']['parameters'], sort_keys=True)}`\n"
            )
            strategies_path.write_text(strategies)
