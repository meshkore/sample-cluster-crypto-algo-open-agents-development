"""Bounded, substantive strategy deliberation for the public cluster Wall.

Lifecycle pings ("a turn started", "a turn finished") are not collaboration.
This module turns the evidence the laboratory already produces into the Wall
sequence required by QUANT7: research brief, red-team review, decision record,
implementation handoff, and result with retrospective.

Every message is built from local records only. Peer replies are never read
back into a shell, a tool or a model prompt — the Wall stays observational, so
a hostile public message cannot steer the laboratory.
"""

from __future__ import annotations

import json
from typing import Any, Optional


CODEX = "codex-lead"
CLAUDE = "claude-code-validator"
ORCHESTRATOR = "quantlab-orchestrator"

MAXIMUM_MESSAGE = 3500


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def _round(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _bullets(items: Any, limit: int = 3) -> str:
    if not isinstance(items, list) or not items:
        return "  - none recorded\n"
    return "".join(f"  - {str(item)[:220]}\n" for item in items[:limit])


def _clip(message: str) -> str:
    return message[:MAXIMUM_MESSAGE]


def research_brief(
    label: str,
    definition: dict[str, Any],
    parameters: dict[str, Any],
    prior: dict[str, Any],
) -> str:
    """What is being proposed, why it could work, and what history already says."""
    hypothesis = (definition.get("signal") or {}).get("hypothesis") or {}
    execution = definition.get("execution") or {}
    money = definition.get("money_management") or {}
    return _clip(
        f"#research **Research brief · {label}**\n"
        f"Hypothesis `{hypothesis.get('id', 'n/a')}` — {hypothesis.get('title', 'untitled')}\n"
        f"Family: `{definition.get('family')}` · horizon: {hypothesis.get('time_horizon', 'n/a')} "
        f"· regime: {hypothesis.get('regime', 'n/a')}\n\n"
        f"**Mechanism.** {str(hypothesis.get('market_mechanism', 'not stated'))[:420]}\n"
        f"**Why it should persist.** {str(hypothesis.get('economic_or_behavioral_story', 'not stated'))[:300]}\n"
        f"**Trigger.** `{str(hypothesis.get('trigger', 'n/a'))[:200]}`\n"
        f"**Entry / exit.** {hypothesis.get('entry_logic', 'n/a')} → {hypothesis.get('exit_logic', 'n/a')}\n"
        f"**Signal parameters.** `{json.dumps(parameters, sort_keys=True)[:320]}`\n"
        f"**Execution.** next-bar-open fill, {execution.get('commission_bps')} bps commission, "
        f"{execution.get('slippage_bps')} bps slippage, long-only.\n"
        f"**Money management.** risk/trade {_pct(money.get('risk_per_trade'))}, stop "
        f"{_pct(money.get('stop_loss_pct'))}, target {_pct(money.get('take_profit_pct'))}, "
        f"max {money.get('maximum_concurrent_assets')} concurrent assets, hard 25% drawdown abort.\n\n"
        f"**Prior evidence in this family.** {prior['family_experiments']} experiments, "
        f"{prior['family_promoted']} promoted, best prior score {_round(prior['family_best_score'])}. "
        f"Laboratory total: {prior['total_experiments']} experiments.\n"
        f"**Expected failure modes.**\n{_bullets(hypothesis.get('expected_failure_modes'))}"
        f"**Invalidators.**\n{_bullets(hypothesis.get('invalidators'))}"
    )


def red_team_review(label: str, experiment: dict[str, Any]) -> str:
    """The adversarial position: what would have to be true for this to be real."""
    critic = experiment.get("critic") or {}
    robustness = experiment.get("robustness") or {}
    checks = robustness.get("checks") or {}
    failed = [name for name, passed in checks.items() if not passed]
    return _clip(
        f"#research **Red-team review · {label}**\n"
        f"Verdict `{critic.get('verdict', 'n/a')}` at confidence {_round(critic.get('confidence'), 2)}.\n\n"
        f"**Measured on the development partition.** net return {_pct(experiment.get('net_return'))}, "
        f"drawdown {_pct(experiment.get('drawdown'))}, Sharpe {_round(experiment.get('sharpe'))}, "
        f"profit factor {_round(experiment.get('profit_factor'))}, {experiment.get('trades')} trades, "
        f"exposure {_pct(experiment.get('exposure'))}.\n"
        f"**Cost stress.** doubled costs give {_pct(robustness.get('double_cost_net_return'))}; "
        f"half-period returns {[_pct(x) for x in (robustness.get('half_returns') or [])]}.\n"
        f"**Failed robustness checks.** {', '.join(failed) if failed else 'none'}\n\n"
        f"**Critical failures.**\n{_bullets(critic.get('critical_failures'))}"
        f"**Suspected biases.**\n{_bullets(critic.get('suspected_biases'))}"
        f"**Tests that would falsify it.**\n{_bullets(critic.get('required_tests'), 4)}"
        "\nPublic peers: objections are welcome as replies here or as issues; they are read "
        "by humans and never executed by the local runner."
    )


def decision_record(
    label: str, experiment: dict[str, Any], phase1: dict[str, Any]
) -> str:
    """Accept, reject or revise, with the exact numbers behind the call."""
    status = experiment.get("status")
    reason = experiment.get("failure_reason") or "No blocking reason recorded."
    score = None
    if phase1.get("return_pct") is not None and phase1.get("max_drawdown") is not None:
        score = phase1["return_pct"] - phase1["max_drawdown"]
    return _clip(
        f"#research **Decision record · {label}** → `{status}`\n"
        f"Reason: {str(reason)[:400]}\n\n"
        f"**Phase 1 (all history before 2026).** status `{phase1.get('status', 'n/a')}`, "
        f"return {_pct(phase1.get('return_pct'))}, max drawdown {_pct(phase1.get('max_drawdown'))}, "
        f"{phase1.get('trades', 'n/a')} trades across {phase1.get('assets_traded', 'n/a')} assets, "
        f"win rate {_pct(phase1.get('win_rate'))}, score {_round(score, 4)}.\n"
        f"**Next bounded step.** "
        + (
            "Promote to the untouched 2026 forward phase."
            if status in {"PROMOTE", "CHAMPION"}
            else "Keep the mechanism, retire this parameterisation, and mutate the "
            "execution variant. 2026 data stays locked and is never used to repair it."
        )
    )


def implementation_handoff(role: str, advisory: str) -> str:
    """What an independent critic actually said, handed to the builder."""
    return _clip(
        f"#research **Implementation handoff · {role} advisory**\n"
        f"{advisory.strip()[:2600]}\n\n"
        "The local builder receives this together with the peer critique. Only the "
        "local maintainer commits; external contributions arrive as fork + pull request."
    )


def result_retrospective(
    label: str, phase1: dict[str, Any], champion: Optional[dict[str, Any]]
) -> str:
    """Outcome, what it changed for the public champion, and the next question."""
    if champion:
        crown = (
            f"Public champion is now `{champion['label']}` on "
            f"{champion['evidence']} evidence (score {_round(champion['score'], 4)}, "
            f"{champion.get('evaluations_considered', 0)} evaluations considered)."
        )
    else:
        crown = "No evaluation is eligible to be published as champion yet."
    return _clip(
        f"#research **Result · {label}**\n"
        f"Phase 1 finished `{phase1.get('status', 'n/a')}` with return "
        f"{_pct(phase1.get('return_pct'))} and max drawdown {_pct(phase1.get('max_drawdown'))} "
        f"over {phase1.get('trades', 'n/a')} trades.\n"
        f"{crown}\n"
        "**Open question for the room.** Which of the failed robustness checks above is the "
        "cheapest to falsify next, and which asset universe or regime would break this "
        "mechanism fastest?"
    )


def prior_evidence(db: Any, family: str) -> dict[str, Any]:
    """Cheap history lookup so a brief can never claim novelty it does not have."""
    row = db.execute(
        """SELECT count(*) total,
                  sum(CASE WHEN e.status IN ('PROMOTE','CHAMPION') THEN 1 ELSE 0 END) promoted,
                  max(e.net_return - e.drawdown) best
           FROM experiments e JOIN strategy_definitions s
             ON s.strategy_number = e.strategy_number
           WHERE s.family = ?""",
        (family,),
    ).fetchone()
    total = db.execute("SELECT count(*) c FROM experiments").fetchone()
    return {
        "family_experiments": int((row["total"] if row else 0) or 0),
        "family_promoted": int((row["promoted"] if row else 0) or 0),
        "family_best_score": (row["best"] if row else None),
        "total_experiments": int(total["c"] or 0),
    }
