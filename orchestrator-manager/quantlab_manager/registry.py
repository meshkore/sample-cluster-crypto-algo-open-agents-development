"""One-command audit of every strategy's result, the forward runs and the champion.

The public champion is only trustworthy if it is cheap to check. This produces
the whole picture in one payload: how many Phase-1 backtests finished, how many
were profitable within the drawdown limit, the best of them by final equity,
every 2026 forward run, what the stored champion is, and — the check that
matters — whether the published champion really is the best eligible evidence.
"""

from __future__ import annotations

from typing import Any

from .champion import MAXIMUM_DRAWDOWN, ChampionRegistry
from .config import Settings
from .loop import ResearchDirector


def strategy_registry(settings: Settings, top: int = 15) -> dict[str, Any]:
    memory = ResearchDirector(settings).memory
    with memory.session() as db:
        phase1 = {
            row["status"]: row["c"]
            for row in db.execute(
                "SELECT status,count(*) c FROM portfolio_backtest_runs GROUP BY status"
            )
        }
        eligible = db.execute(
            """SELECT count(*) c FROM portfolio_backtest_runs
               WHERE status='COMPLETE' AND final_equity>initial_capital
                 AND max_drawdown<? AND trades>0""",
            (MAXIMUM_DRAWDOWN,),
        ).fetchone()["c"]
        best = [
            {
                "strategy": f"S{row['strategy_number']:05d}",
                "final_equity": round(row["final_equity"], 2),
                "return_pct": round(row["return_pct"], 4),
                "max_drawdown": round(row["max_drawdown"], 4),
                "score": round(row["return_pct"] - row["max_drawdown"], 4),
                "trades": row["trades"],
                "assets_traded": row["assets_traded"],
                "eligible_for_forward": bool(
                    row["final_equity"] > row["initial_capital"]
                    and row["max_drawdown"] < MAXIMUM_DRAWDOWN
                    and row["trades"] > 0
                ),
                "forward_run": row["forward_run"],
                "forward_status": row["forward_status"],
            }
            for row in db.execute(
                """SELECT p.*, f.run_id forward_run, f.status forward_status
                   FROM portfolio_backtest_runs p
                   LEFT JOIN forward_portfolio_runs f
                     ON f.strategy_number = p.strategy_number
                    AND f.run_id NOT LIKE '%-LIVE'
                   WHERE p.status='COMPLETE'
                   ORDER BY p.final_equity DESC LIMIT ?""",
                (top,),
            )
        ]
        forward = [
            {
                "run_id": row["run_id"],
                "strategy": f"S{row['strategy_number']:05d}",
                "status": row["status"],
                "return_pct": round(row["return_pct"], 4),
                "max_drawdown": round(row["max_drawdown"], 4),
                "score": round(row["return_pct"] - row["max_drawdown"], 4),
                "trades": row["trades"],
            }
            for row in db.execute(
                """SELECT * FROM forward_portfolio_runs
                   ORDER BY (return_pct-max_drawdown) DESC"""
            )
        ]
        decisions = [
            {
                "decided_at": row["decided_at"],
                "strategy": f"S{row['strategy_number']:05d}",
                "evidence": row["evidence"],
                "score": round(row["score"], 4),
                "replaced": bool(row["replaced"]),
                "reason": row["reason"],
            }
            for row in db.execute(
                "SELECT * FROM champion_decisions WHERE replaced=1 ORDER BY id DESC LIMIT 10"
            )
        ]
        experiments = {
            row["status"]: row["c"]
            for row in db.execute(
                "SELECT status,count(*) c FROM experiments GROUP BY status"
            )
        }
    stored = ChampionRegistry(memory).current()
    champion = (stored or {}).get("champion")
    return {
        "phase1_runs": phase1,
        "phase1_eligible_for_forward": eligible,
        "synthetic_experiment_verdicts": experiments,
        "best_phase1_by_final_equity": best,
        "forward_2026_runs": forward,
        "champion": champion,
        "champion_replacements": decisions,
        "consistency": _consistency(champion, best, forward),
    }


def _consistency(
    champion: dict[str, Any] | None,
    best: list[dict[str, Any]],
    forward: list[dict[str, Any]],
) -> dict[str, Any]:
    """The fast go/no-go: is the published champion the best eligible evidence?"""
    eligible_forward = [
        run
        for run in forward
        if run["status"] == "FORWARD_2026" and run["max_drawdown"] < MAXIMUM_DRAWDOWN
    ]
    eligible_phase1 = [row for row in best if row["eligible_for_forward"]]
    expected = None
    if eligible_forward:
        expected = {
            "evidence": "FORWARD_2026",
            "strategy": eligible_forward[0]["strategy"],
        }
    elif eligible_phase1:
        expected = {
            "evidence": "HISTORICAL_PHASE_1",
            "strategy": max(eligible_phase1, key=lambda row: row["score"])["strategy"],
        }
    published = (
        {"evidence": champion["evidence"], "strategy": champion["label"]}
        if champion
        else None
    )
    return {
        "expected_champion": expected,
        "published_champion": published,
        "matches": expected == published,
        "eligible_forward_runs": len(eligible_forward),
        "note": "Forward evidence outranks Phase-1 evidence, so a profitable "
        "Phase-1 backtest is not published while any completed 2026 forward run "
        "is eligible, even a losing one.",
    }
