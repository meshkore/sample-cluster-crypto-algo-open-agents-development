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
2. Inside one evidence class a profitable evaluation always outranks an
   unprofitable one. This is a class, not a tie-break: no strategy that lost
   money is ever published as "best" while one that made money exists.
3. Inside one profitability class the score is risk-adjusted **excess** return:
   the return over the benchmark, divided by the maximum drawdown. Beating the
   market is the claim; returning less than buying and holding is not an edge
   however pretty the equity curve. Evaluations with no excess rank on excess
   alone, since dividing a negative number by a small drawdown would rank the
   worst result first.
4. Evidence produced by a superseded engine is never eligible. It stays in the
   database and remains readable, but it cannot be crowned.
5. The stored champion is replaced only when a candidate is strictly better.
   Otherwise it is preserved untouched, including every number already public.

Rule 2 exists because of a real regression. The score used to be
``return_pct - max_drawdown``, which looks risk-adjusted but is not: it is a
difference between two quantities that do not trade off linearly, and while
every strategy loses money its maximum is at *not trading at all*. On
2026-08-02 it replaced a champion returning +0.21% with one returning -0.13%,
purely because the loser's drawdown was 0.91 points smaller. Measured across
216 forward runs, the old score correlated -0.58 with the number of trades: it
was paying strategies to stay in cash. A ranking that can prefer a loss to a
profit is not ranking trading strategies.

Rule 3 exists because the laboratory ran for months with no benchmark anywhere
in it. A long-only crypto strategy returning +0.24% has said nothing until you
know what holding the same assets returned over the same window, and with
nothing to compare against the ranking could not separate an edge from the
market carrying the position.

Rule 4 exists because until 2026-08-02 the engine sized positions using the
volatility of the day it was trading into, so every stored result before
``ENGINE_VERSION`` 2 is inflated by information the strategy could not have
had.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .memory import ExperimentMemory
from .models import ENGINE_VERSION, utc_now


FORWARD_2026 = "FORWARD_2026"
HISTORICAL_PHASE_1 = "HISTORICAL_PHASE_1"
EVIDENCE_RANK = {HISTORICAL_PHASE_1: 1, FORWARD_2026: 2}

MAXIMUM_DRAWDOWN = 0.25
# A drawdown this small is indistinguishable from luck over a few months, so it
# is the floor of the Calmar denominator. Without it a run that dipped 0.01%
# would report a ratio in the thousands and be unbeatable forever.
MINIMUM_DRAWDOWN = 0.01
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


def _number(row: Any, column: str, missing: float) -> float:
    """Read a numeric column treating only NULL as missing.

    ``row[column] or default`` reads a legitimate 0.0 as missing, which turned
    a flawless zero-drawdown run into a full 100% drawdown penalty.
    """
    value = row[column]
    return missing if value is None else float(value)


def _optional(row: Any, column: str) -> Optional[float]:
    try:
        value = row[column]
    except (KeyError, IndexError):
        return None
    return None if value is None else float(value)


def _optional_text(row: Any, column: str) -> Optional[str]:
    try:
        value = row[column]
    except (KeyError, IndexError):
        return None
    return None if value is None else str(value)


def is_profitable(row: Any) -> bool:
    return _number(row, "return_pct", 0.0) > 0.0


def edge_of(row: Any) -> float:
    """Return over the benchmark, or plain return when none was recorded.

    The benchmark is what the same capital did over the same window doing
    nothing clever. Ranking on raw return cannot tell a strategy that found an
    edge from one that was carried by the market, and in crypto the market
    carries almost everything.
    """
    profit = _number(row, "return_pct", 0.0)
    try:
        reference = row["benchmark_reference"]
    except (KeyError, IndexError):
        return profit
    return profit if reference is None else profit - float(reference)


def score_of(row: Any) -> float:
    """Risk-adjusted excess for a profitable run, plain excess otherwise.

    Dividing by the drawdown only means something once there is something to
    divide: for a negative number it would rank the worst result with the
    smallest dip highest. Unprofitable runs are a strictly lower class anyway,
    so ranking them on excess alone keeps "least bad" honest.
    """
    edge = edge_of(row)
    if _number(row, "return_pct", 0.0) <= 0.0 or edge <= 0.0:
        return edge
    drawdown = _number(row, "max_drawdown", 1.0)
    return edge / max(drawdown, MINIMUM_DRAWDOWN)


class ChampionRegistry:
    """Reads candidates, compares them with the stored champion, persists one."""

    def __init__(self, memory: ExperimentMemory):
        self.memory = memory

    # -- candidate discovery -------------------------------------------------

    def candidate(self, db: Any) -> dict[str, Any] | None:
        """Best eligible evaluation available right now, forward evidence first."""
        # Profit first, then risk-adjusted profit. Expressed in SQL so the
        # database and _compare agree on the order; keep the two in step.
        # `engine_version` is the QUANT8 quarantine: results produced before the
        # sizing lookahead was removed are inflated, so they stay readable for
        # audit but can never be crowned. `edge` is return over the benchmark.
        edge = """(return_pct - coalesce(benchmark_reference,0))"""
        forward = db.execute(
            f"""SELECT strategy_number,run_id,return_pct,max_drawdown,as_of,
                      benchmark_reference,benchmark_reference_name,excess_return
               FROM forward_portfolio_runs
               WHERE status='FORWARD_2026' AND max_drawdown<? AND engine_version>=?
               ORDER BY (return_pct>0) DESC,
                        CASE WHEN return_pct>0 AND {edge}>0
                             THEN {edge}/max(max_drawdown,?)
                             ELSE {edge} END DESC,
                        return_pct DESC,max_drawdown ASC,as_of DESC LIMIT 1""",
            (MAXIMUM_DRAWDOWN, ENGINE_VERSION, MINIMUM_DRAWDOWN),
        ).fetchone()
        if forward:
            return self._candidate(FORWARD_2026, forward, forward["run_id"])
        historical = db.execute(
            f"""SELECT strategy_number,return_pct,max_drawdown,updated_at,
                      benchmark_reference,benchmark_reference_name,excess_return
               FROM portfolio_backtest_runs
               WHERE status='COMPLETE' AND max_drawdown<? AND engine_version>=?
                 AND final_equity>initial_capital AND trades>0
               ORDER BY CASE WHEN {edge}>0 THEN {edge}/max(max_drawdown,?)
                             ELSE {edge} END DESC,
                        return_pct DESC,max_drawdown ASC,updated_at DESC LIMIT 1""",
            (MAXIMUM_DRAWDOWN, ENGINE_VERSION, MINIMUM_DRAWDOWN),
        ).fetchone()
        if not historical:
            return None
        return self._candidate(HISTORICAL_PHASE_1, historical, None)

    @staticmethod
    def _candidate(evidence: str, row: Any, run_id: Optional[str]) -> dict[str, Any]:
        return {
            "evidence": evidence,
            "strategy_number": int(row["strategy_number"]),
            "run_id": run_id,
            "score": score_of(row),
            "profitable": is_profitable(row),
            "return_pct": _number(row, "return_pct", 0.0),
            "max_drawdown": _number(row, "max_drawdown", 0.0),
            "benchmark": _optional(row, "benchmark_reference"),
            "benchmark_name": _optional_text(row, "benchmark_reference_name"),
            "excess_return": edge_of(row),
            "engine_version": ENGINE_VERSION,
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

    def _withdraw_superseded(
        self, db: Any, stored: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Retire a champion that a superseded engine crowned.

        Refusing to *crown* stale evidence is not enough on its own: a champion
        already published under the old engine would otherwise stay on the
        public page indefinitely, because no candidate exists to displace it.
        Withdrawing leaves the view empty until an honest evaluation finishes,
        which is the truthful state — the laboratory does not currently know
        which strategy is best.
        """
        if not stored:
            return None
        try:
            version = int(stored.get("engine_version") or 1)
        except (TypeError, ValueError):
            version = 1
        if version >= ENGINE_VERSION:
            return stored
        db.execute("DELETE FROM champion_records WHERE singleton=1")
        db.execute(
            """INSERT INTO champion_decisions(decided_at,strategy_number,evidence,
                 evidence_rank,score,previous_strategy_number,previous_evidence,
                 previous_score,replaced,reason,profitable)
               VALUES(?,?,?,?,?,?,?,?,0,?,?)""",
            (
                utc_now(),
                stored["strategy_number"],
                stored["evidence"],
                stored["evidence_rank"],
                float(stored["score"]),
                stored["strategy_number"],
                stored["evidence"],
                float(stored["score"]),
                f"Withdrawn: measured by engine {version}, superseded by "
                f"{ENGINE_VERSION}. The result is inflated and cannot stand as "
                "the published best.",
                int(bool(stored.get("profitable"))),
            ),
        )
        return None

    def refresh(self, build: ViewBuilder) -> dict[str, Any] | None:
        """Compare the best available evaluation with the stored champion."""
        with self.memory.transaction() as db:
            candidate = self.candidate(db)
            stored = self._withdraw_superseded(db, self._stored(db))
            if candidate is None:
                return self._metadata(stored)
            better, reason = self._compare(candidate, stored)
            if not better:
                self._record_decision(db, candidate, stored, False, reason)
                return self._metadata(stored)
            view = build(
                db,
                candidate["evidence"],
                candidate["strategy_number"],
                candidate["run_id"],
            )
            # The ledger records what happened, not what was about to happen: a
            # crowning that dies here because the evidence could not be
            # materialised must not leave a "replaced" row behind.
            if not view:
                self._record_decision(
                    db,
                    candidate,
                    stored,
                    False,
                    f"{reason}, but its evidence could not be materialised",
                )
                return self._metadata(stored)
            self._record_decision(db, candidate, stored, True, reason)
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
                "profitable": int(candidate["profitable"]),
                "return_pct": candidate["return_pct"],
                "max_drawdown": candidate["max_drawdown"],
                "benchmark": candidate["benchmark"],
                "benchmark_name": candidate["benchmark_name"],
                "excess_return": candidate["excess_return"],
                "engine_version": candidate["engine_version"],
            }
            db.execute(
                """INSERT INTO champion_records
                   VALUES(1,:strategy_number,:label,:evidence,:evidence_rank,:score,
                          :source_run_id,:crowned_at,:evaluations_considered,
                          :replaced_strategy_number,:view_json,:profitable,
                          :return_pct,:max_drawdown,:benchmark,:benchmark_name,
                          :excess_return,:engine_version)
                   ON CONFLICT(singleton) DO UPDATE SET
                     strategy_number=excluded.strategy_number,label=excluded.label,
                     evidence=excluded.evidence,evidence_rank=excluded.evidence_rank,
                     score=excluded.score,source_run_id=excluded.source_run_id,
                     crowned_at=excluded.crowned_at,
                     evaluations_considered=excluded.evaluations_considered,
                     replaced_strategy_number=excluded.replaced_strategy_number,
                     view_json=excluded.view_json,profitable=excluded.profitable,
                     return_pct=excluded.return_pct,
                     max_drawdown=excluded.max_drawdown,
                     benchmark=excluded.benchmark,
                     benchmark_name=excluded.benchmark_name,
                     excess_return=excluded.excess_return,
                     engine_version=excluded.engine_version""",
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
        # A profitable candidate takes the crown from a losing champion however
        # smooth that champion's equity curve was, and never the other way
        # round. This is the rule the old single score silently violated.
        stored_profitable = bool(stored["profitable"])
        if candidate["profitable"] and not stored_profitable:
            return True, (
                f"Return {candidate['return_pct']:+.2%} is profitable and the "
                f"stored champion's {float(stored['return_pct']):+.2%} is not"
            )
        if stored_profitable and not candidate["profitable"]:
            return False, (
                f"Return {candidate['return_pct']:+.2%} is a loss and the stored "
                f"champion's {float(stored['return_pct']):+.2%} is a profit"
            )
        if candidate["strategy_number"] == stored["strategy_number"] and candidate[
            "score"
        ] == float(stored["score"]):
            return False, "The stored champion is still the best evaluation"
        measure = "Calmar" if candidate["profitable"] else "Return"
        if candidate["score"] > float(stored["score"]):
            return True, (
                f"{measure} {candidate['score']:.6f} beats "
                f"{float(stored['score']):.6f} on equal evidence"
            )
        return False, (
            f"{measure} {candidate['score']:.6f} does not beat "
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
                 previous_score,replaced,reason,profitable)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
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
                int(candidate["profitable"]),
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
