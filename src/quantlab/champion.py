"""The persistent public champion: the best strategy the laboratory has produced.

The public "Best strategy" view must never go blank while a new candidate is
running, and it must never be silently rewritten by a later re-evaluation.
This module keeps exactly one champion record, materialises its complete
public evidence (definition, equity curve, asset results, trade ledger) and
writes an auditable decision row every time a candidate is compared.

Ranking is evidence-first and documented in one place:

1. ``FORWARD_2026`` evidence (a completed 2026 forward evaluation that stayed
   under the 25% drawdown limit) always outranks ``HISTORICAL_PHASE_1``
   evidence. A forward run only ever exists for a formally promoted Phase-1
   candidate, so its presence is itself the promotion record.
2. Inside one evidence class the score is ``return_pct - max_drawdown``, the
   same objective the optimizer maximises. Ties break on higher return, then
   lower drawdown, then the more recent evaluation.
3. The stored champion is replaced only when a candidate is strictly better.
   Otherwise it is preserved untouched, including every number already public.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .memory import ExperimentMemory
from .models import utc_now


FORWARD_2026 = "FORWARD_2026"
HISTORICAL_PHASE_1 = "HISTORICAL_PHASE_1"
EVIDENCE_RANK = {HISTORICAL_PHASE_1: 1, FORWARD_2026: 2}

MAXIMUM_DRAWDOWN = 0.25
PUBLIC_TRADES = 500
PUBLIC_EQUITY_POINTS = 1200

# Evaluated at runtime, so it must stay valid on the 3.9 system interpreter the
# LaunchAgent uses: PEP 604 unions are only legal in deferred annotations here.
ViewBuilder = Callable[[Any, str, int, Optional[str]], Optional[dict]]


def _sample(items: list[Any], maximum: int) -> list[Any]:
    """Keep both endpoints and evenly spaced points for a legible curve."""
    if len(items) <= maximum or maximum < 2:
        return items
    step = (len(items) - 1) / (maximum - 1)
    return [items[round(index * step)] for index in range(maximum)]


def bounded_view(view: dict[str, Any]) -> dict[str, Any]:
    """Bound the stored evidence so one record can never grow without limit."""
    result = dict(view)
    result["trades"] = list(result.get("trades") or [])[:PUBLIC_TRADES]
    result["equity_curve"] = _sample(
        list(result.get("equity_curve") or []), PUBLIC_EQUITY_POINTS
    )
    return result


def score_of(row: Any) -> float:
    return (row["return_pct"] or 0.0) - (row["max_drawdown"] or 1.0)


class ChampionRegistry:
    """Reads candidates, compares them with the stored champion, persists one."""

    def __init__(self, memory: ExperimentMemory):
        self.memory = memory

    # -- candidate discovery -------------------------------------------------

    def candidate(self, db: Any) -> dict[str, Any] | None:
        """Best eligible evaluation available right now, forward evidence first."""
        forward = db.execute(
            """SELECT strategy_number,run_id,return_pct,max_drawdown,as_of
               FROM forward_portfolio_runs
               WHERE status='FORWARD_2026' AND max_drawdown<?
               ORDER BY (return_pct-max_drawdown) DESC,return_pct DESC,
                        max_drawdown ASC,as_of DESC LIMIT 1""",
            (MAXIMUM_DRAWDOWN,),
        ).fetchone()
        if forward:
            return {
                "evidence": FORWARD_2026,
                "strategy_number": int(forward["strategy_number"]),
                "run_id": forward["run_id"],
                "score": score_of(forward),
            }
        historical = db.execute(
            """SELECT strategy_number,return_pct,max_drawdown,updated_at
               FROM portfolio_backtest_runs
               WHERE status='COMPLETE' AND max_drawdown<?
                 AND final_equity>initial_capital AND trades>0
               ORDER BY (return_pct-max_drawdown) DESC,return_pct DESC,
                        max_drawdown ASC,updated_at DESC LIMIT 1""",
            (MAXIMUM_DRAWDOWN,),
        ).fetchone()
        if not historical:
            return None
        return {
            "evidence": HISTORICAL_PHASE_1,
            "strategy_number": int(historical["strategy_number"]),
            "run_id": None,
            "score": score_of(historical),
        }

    @staticmethod
    def _considered(db: Any) -> int:
        row = db.execute(
            """SELECT (SELECT count(*) FROM portfolio_backtest_runs
                       WHERE status IN ('COMPLETE','ABORTED_DRAWDOWN'))
                    + (SELECT count(*) FROM forward_portfolio_runs
                       WHERE status IN ('FORWARD_2026','FORWARD_ABORTED_DRAWDOWN')) total"""
        ).fetchone()
        return int(row["total"] or 0)

    @staticmethod
    def _phase1_summary(db: Any, strategy_number: int) -> dict[str, Any] | None:
        row = db.execute(
            """SELECT status,return_pct,max_drawdown,net_profit,final_equity,
                      initial_capital,trades,win_rate,assets_traded,period_start,period_end
               FROM portfolio_backtest_runs WHERE strategy_number=?""",
            (strategy_number,),
        ).fetchone()
        return dict(row) if row else None

    # -- stored record -------------------------------------------------------

    @staticmethod
    def _stored(db: Any) -> dict[str, Any] | None:
        row = db.execute("SELECT * FROM champion_records WHERE singleton=1").fetchone()
        return dict(row) if row else None

    def current(self) -> dict[str, Any] | None:
        """The published champion, or None before the first eligible result."""
        with self.memory.session() as db:
            stored = self._stored(db)
        if not stored:
            return None
        view = json.loads(stored.pop("view_json"))
        stored.pop("singleton", None)
        view["champion"] = stored
        return view

    # -- decision ------------------------------------------------------------

    @staticmethod
    def _metadata(record: dict[str, Any] | None) -> dict[str, Any] | None:
        if not record:
            return None
        return {
            key: value
            for key, value in record.items()
            if key not in {"view_json", "singleton"}
        }

    def refresh(self, build: ViewBuilder) -> dict[str, Any] | None:
        """Compare the best available evaluation with the stored champion."""
        with self.memory.transaction() as db:
            candidate = self.candidate(db)
            stored = self._stored(db)
            if candidate is None:
                return self._metadata(stored)
            better, reason = self._compare(candidate, stored)
            self._record_decision(db, candidate, stored, better, reason)
            if not better:
                return self._metadata(stored)
            view = build(
                db,
                candidate["evidence"],
                candidate["strategy_number"],
                candidate["run_id"],
            )
            if not view:
                return self._metadata(stored)
            view = bounded_view(view)
            view["phase1"] = self._phase1_summary(db, candidate["strategy_number"])
            record = {
                "strategy_number": candidate["strategy_number"],
                "label": f"S{candidate['strategy_number']:05d}",
                "evidence": candidate["evidence"],
                "evidence_rank": EVIDENCE_RANK[candidate["evidence"]],
                "score": candidate["score"],
                "source_run_id": candidate["run_id"],
                "crowned_at": utc_now(),
                "evaluations_considered": self._considered(db),
                "replaced_strategy_number": (
                    stored["strategy_number"] if stored else None
                ),
                "view_json": json.dumps(view, allow_nan=False),
            }
            db.execute(
                """INSERT INTO champion_records
                   VALUES(1,:strategy_number,:label,:evidence,:evidence_rank,:score,
                          :source_run_id,:crowned_at,:evaluations_considered,
                          :replaced_strategy_number,:view_json)
                   ON CONFLICT(singleton) DO UPDATE SET
                     strategy_number=excluded.strategy_number,label=excluded.label,
                     evidence=excluded.evidence,evidence_rank=excluded.evidence_rank,
                     score=excluded.score,source_run_id=excluded.source_run_id,
                     crowned_at=excluded.crowned_at,
                     evaluations_considered=excluded.evaluations_considered,
                     replaced_strategy_number=excluded.replaced_strategy_number,
                     view_json=excluded.view_json""",
                record,
            )
            return self._metadata(record)

    @staticmethod
    def _compare(
        candidate: dict[str, Any], stored: dict[str, Any] | None
    ) -> tuple[bool, str]:
        rank = EVIDENCE_RANK[candidate["evidence"]]
        if stored is None:
            return True, "First eligible evaluation becomes the champion"
        if rank > stored["evidence_rank"]:
            return True, (
                f"{candidate['evidence']} evidence outranks {stored['evidence']}"
            )
        if rank < stored["evidence_rank"]:
            return False, (
                f"Stored {stored['evidence']} evidence outranks {candidate['evidence']}"
            )
        if candidate["strategy_number"] == stored["strategy_number"] and candidate[
            "score"
        ] == float(stored["score"]):
            return False, "The stored champion is still the best evaluation"
        if candidate["score"] > float(stored["score"]):
            return True, (
                f"Score {candidate['score']:.6f} beats "
                f"{float(stored['score']):.6f} on equal evidence"
            )
        return False, (
            f"Score {candidate['score']:.6f} does not beat "
            f"{float(stored['score']):.6f} on equal evidence"
        )

    @staticmethod
    def _record_decision(
        db: Any,
        candidate: dict[str, Any],
        stored: dict[str, Any] | None,
        replaced: bool,
        reason: str,
    ) -> None:
        previous = db.execute(
            "SELECT * FROM champion_decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if (
            previous
            and not replaced
            and previous["strategy_number"] == candidate["strategy_number"]
            and previous["reason"] == reason
        ):
            # A repeated no-change verdict adds no audit value on every cycle.
            return
        db.execute(
            """INSERT INTO champion_decisions(decided_at,strategy_number,evidence,
                 evidence_rank,score,previous_strategy_number,previous_evidence,
                 previous_score,replaced,reason)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                utc_now(),
                candidate["strategy_number"],
                candidate["evidence"],
                EVIDENCE_RANK[candidate["evidence"]],
                candidate["score"],
                stored["strategy_number"] if stored else None,
                stored["evidence"] if stored else None,
                float(stored["score"]) if stored else None,
                int(replaced),
                reason,
            ),
        )

    def decisions(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.memory.session() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM champion_decisions ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
            ]
