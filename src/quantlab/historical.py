from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

from . import benchmark, regime, walkforward
from .backtest import CostModel
from .config import Settings
from .data import DataManager, FAMILY_DATA_OVERRIDES, FocusedDataset
from .memory import ExperimentMemory
from .models import ENGINE_VERSION, Bar, utc_now
from .portfolio import (
    LongOnlyPortfolioBacktester,
    MoneyManagement,
    policy_keys,
)
from .strategies import (
    BASELINE_FAMILY,
    BASELINE_PARAMS,
    MARKET_CONTEXT_FAMILIES,
    build_strategy,
)


class HistoricalUniverseEvaluator:
    """One chronological, shared-capital portfolio over the complete ready universe."""

    def __init__(
        self,
        settings: Settings,
        memory: ExperimentMemory,
        activity: Callable[[str, str], None] | None = None,
    ):
        self.settings, self.memory, self.activity = settings, memory, activity

    def _focused_bars(self, symbols: list[str], interval: str) -> dict[str, list[Bar]]:
        """All available pre-2026 history for an override family's own symbols.

        The shared `asset_universe` table is keyed to `BAR_INTERVAL` (daily)
        for the other families' 386-asset universe, so a family with its own
        interval has nowhere to record it; `FocusedDataset` owns that cache
        and is the same loader the forward evaluator uses, which is what keeps
        the two phases on one timeframe.
        """

        def on_exclude(symbol: str, reason: str) -> None:
            if self.activity:
                self.activity(
                    "PREPARING_SIGNALS",
                    json.dumps({"symbol": symbol, "excluded": reason[:200]}),
                )

        dataset = FocusedDataset(
            self.settings.data_root,
            self.settings.splits["future_lock_start"],
            on_exclude=on_exclude,
        )
        return dataset.research_bars(symbols, interval)

    def _market_context(self, family: str) -> Any:
        """The wider-market view, built only for the families that declare one.

        Built from the same `FocusedDataset` the candidate's own bars come
        from, so the regime basket obeys the identical 2026 lock: this loader
        cannot return a post-lock bar, which is what keeps a Phase-1 regime
        label free of forward information even in principle.
        """
        if family not in MARKET_CONTEXT_FAMILIES:
            return None
        return regime.market_context_from(self._focused_bars)

    def _contrast(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        policy: MoneyManagement,
        costs: CostModel,
        capital: float,
        interval: str | None,
        candidate_return: float,
        candidate_drawdown: float,
        candidate_family: str,
        candidate_params: dict[str, Any],
    ) -> dict[str, Any]:
        """Difference against the control, under identical conditions.

        An absolute return measures the signal, the money-management policy,
        the market regime and the asset selection all at once, which is why
        nine families here produced nine numbers that could not be compared to
        each other or to anything else. Holding everything except the signal
        fixed and reporting the difference measures the signal.

        The control is computed once per distinct experimental condition and
        cached, so candidates sharing a condition -- which most do, since they
        share the universe and the default policy -- pay for it once.
        """
        bar_count = sum(len(bars) for bars in bars_by_symbol.values())
        key = self.memory.scope_key(
            BASELINE_FAMILY,
            BASELINE_PARAMS,
            interval,
            list(bars_by_symbol),
            bar_count,
            asdict(policy),
            asdict(costs),
        )
        cached = self.memory.baseline(key)
        if cached is None:
            control = LongOnlyPortfolioBacktester(costs, policy).run(
                bars_by_symbol,
                lambda: build_strategy(BASELINE_FAMILY, BASELINE_PARAMS),
                capital,
            )
            cached = {
                "return_pct": control.return_pct,
                "max_drawdown": control.max_drawdown,
                "trades": len(control.trades),
                "wins": control.wins,
                "losses": control.losses,
                "average_exposure": control.average_exposure,
                "time_in_market": control.time_in_market,
                "aborted": control.aborted,
            }
            self.memory.store_baseline(
                key,
                BASELINE_FAMILY,
                BASELINE_PARAMS,
                interval,
                list(bars_by_symbol),
                bar_count,
                cached,
            )
        return {
            "baseline_family": BASELINE_FAMILY,
            "baseline_return": cached["return_pct"],
            "baseline_drawdown": cached["max_drawdown"],
            "baseline_trades": cached["trades"],
            "baseline_average_exposure": cached["average_exposure"],
            # The headline: did this candidate earn its extra moving parts?
            "excess_over_baseline": candidate_return - cached["return_pct"],
            "drawdown_vs_baseline": candidate_drawdown - cached["max_drawdown"],
            # A candidate that IS the control trivially ties with itself; say so
            # rather than publishing a meaningless zero as evidence. This has to
            # compare the parameters too, not just the family: a DIFFERENT
            # tuning of the control family is a real candidate with a real
            # contrast, and treating it as its own control would silently
            # discard the one comparison that matters for it.
            "is_the_baseline": (
                candidate_family == BASELINE_FAMILY
                and {k: candidate_params.get(k) for k in BASELINE_PARAMS}
                == dict(BASELINE_PARAMS)
            ),
        }

    def evaluate_latest(self) -> dict[str, Any] | None:
        with self.memory.session() as db:
            selected = db.execute(
                """SELECT e.strategy_number,e.status,e.parameters_json,s.family,s.money_management_json
                   FROM experiments e JOIN strategy_definitions s USING(strategy_number)
                   WHERE e.strategy_number IS NOT NULL ORDER BY e.created_at DESC LIMIT 1"""
            ).fetchone()
            assets = db.execute(
                "SELECT symbol,research_path FROM asset_universe WHERE research_path IS NOT NULL ORDER BY symbol"
            ).fetchall()
        if not selected:
            return None
        strategy_number = int(selected["strategy_number"])
        # Phase 1 always uses all information strictly before 2026. Phase 2 is
        # physically separate and can never feed strategy generation.
        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
        override = FAMILY_DATA_OVERRIDES.get(selected["family"])
        if override:
            bars_by_symbol = self._focused_bars(
                override["symbols"], override["interval"]
            )
        else:
            if not assets:
                return None
            bars_by_symbol = {}
            for asset in assets:
                bars = [
                    bar
                    for bar in DataManager.load_csv(asset["research_path"])
                    if bar.timestamp < cutoff
                ]
                if len(bars) >= 3:
                    bars_by_symbol[asset["symbol"]] = bars
        if not bars_by_symbol:
            return None
        period_start = min(
            bars[0].timestamp for bars in bars_by_symbol.values()
        ).isoformat()
        period_end = max(
            bars[-1].timestamp for bars in bars_by_symbol.values()
        ).isoformat()
        capital = float(self.settings.portfolio["initial_capital"])
        # Derived from MoneyManagement itself -- see portfolio.policy_keys for why
        # a hand-maintained list here cost a result.
        keys = policy_keys()
        stored_policy = json.loads(selected["money_management_json"])
        # A key absent from BOTH the stored policy and configuration must fall
        # through to the dataclass default, not be passed as None. Passing None
        # was fine while every field was Optional and became a hard failure the
        # moment one had a validated non-None default.
        missing = object()
        policy = MoneyManagement(
            **{
                key: value
                for key in keys
                if (
                    value := stored_policy.get(
                        key, self.settings.portfolio.get(key, missing)
                    )
                )
                is not missing
            }
        )
        params = json.loads(selected["parameters_json"])
        engine = LongOnlyPortfolioBacktester(
            CostModel(self.settings.commission_bps, self.settings.slippage_bps), policy
        )

        with self.memory.transaction() as db:
            db.execute(
                "DELETE FROM portfolio_asset_results WHERE strategy_number=?",
                (strategy_number,),
            )
            db.execute(
                "DELETE FROM portfolio_trades WHERE strategy_number=?",
                (strategy_number,),
            )
            db.execute(
                "DELETE FROM portfolio_equity WHERE strategy_number=?",
                (strategy_number,),
            )
            total_days = len(
                {bar.timestamp for bars in bars_by_symbol.values() for bar in bars}
            )
            db.execute(
                """INSERT OR REPLACE INTO portfolio_backtest_runs(
                   strategy_number,status,period_start,period_end,current_date,initial_capital,
                   current_equity,final_equity,net_profit,return_pct,max_drawdown,total_days,
                   processed_days,assets_available,assets_traded,trades,wins,losses,win_rate,
                   open_positions,cash,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    strategy_number,
                    "PREPARING_SIGNALS",
                    period_start,
                    period_end,
                    period_start,
                    capital,
                    capital,
                    None,
                    0.0,
                    0.0,
                    0.0,
                    total_days,
                    0,
                    len(bars_by_symbol),
                    0,
                    0,
                    0,
                    0,
                    0.0,
                    0,
                    capital,
                    utc_now(),
                ),
            )

        def on_preparation(point: dict[str, Any]) -> None:
            if self.activity:
                self.activity(
                    "PREPARING_SIGNALS",
                    json.dumps({"strategy": strategy_number, **point}),
                )

        def on_progress(point: dict[str, Any]) -> None:
            with self.memory.transaction() as db:
                db.execute(
                    """INSERT INTO portfolio_backtest_runs(
                       strategy_number,status,period_start,period_end,current_date,initial_capital,
                       current_equity,final_equity,net_profit,return_pct,max_drawdown,total_days,
                       processed_days,assets_available,assets_traded,trades,wins,losses,win_rate,
                       open_positions,cash,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(strategy_number) DO UPDATE SET status=excluded.status,
                       current_date=excluded.current_date,current_equity=excluded.current_equity,
                       net_profit=excluded.net_profit,return_pct=excluded.return_pct,
                       max_drawdown=excluded.max_drawdown,
                       total_days=excluded.total_days,processed_days=excluded.processed_days,
                       trades=excluded.trades,open_positions=excluded.open_positions,
                       assets_traded=excluded.assets_traded,
                       cash=excluded.cash,updated_at=excluded.updated_at""",
                    (
                        strategy_number,
                        "BACKTESTING",
                        period_start,
                        period_end,
                        point["timestamp"],
                        capital,
                        point["equity"],
                        None,
                        point["equity"] - capital,
                        point["equity"] / capital - 1,
                        point["max_drawdown"],
                        point["total_days"],
                        point["processed_days"],
                        len(bars_by_symbol),
                        point.get("assets_traded", 0),
                        point["trades"],
                        0,
                        0,
                        0.0,
                        point["open_positions"],
                        point["cash"],
                        utc_now(),
                    ),
                )
                for trade in point.get("closed_trades", []):
                    db.execute(
                        "INSERT OR REPLACE INTO portfolio_trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            strategy_number,
                            trade["symbol"],
                            trade["sequence"],
                            trade["entry_time"],
                            trade["exit_time"],
                            trade["entry_price"],
                            trade["exit_price"],
                            trade["duration_seconds"],
                            trade["invested_capital"],
                            trade["pnl"],
                            trade["pnl_pct"],
                            trade["exit_reason"],
                        ),
                    )
                db.execute(
                    "INSERT OR REPLACE INTO portfolio_equity VALUES(?,?,?,?,?)",
                    (
                        strategy_number,
                        point["timestamp"],
                        point["equity"],
                        point["cash"],
                        point["open_positions"],
                    ),
                )
            if self.activity:
                public = {
                    key: value for key, value in point.items() if key != "closed_trades"
                }
                self.activity(
                    "BACKTESTING", json.dumps({"strategy": strategy_number, **public})
                )

        context = self._market_context(selected["family"])
        result = engine.run(
            bars_by_symbol,
            lambda: build_strategy(selected["family"], params, context),
            capital,
            on_progress,
            preparation_progress=on_preparation,
            pace_seconds=float(
                self.settings.autonomous.get("backtest_pace_seconds", 0) or 0
            ),
        )
        with self.memory.transaction() as db:
            db.execute(
                "DELETE FROM portfolio_asset_results WHERE strategy_number=?",
                (strategy_number,),
            )
            db.execute(
                "DELETE FROM portfolio_trades WHERE strategy_number=?",
                (strategy_number,),
            )
            db.execute(
                "DELETE FROM portfolio_equity WHERE strategy_number=?",
                (strategy_number,),
            )
            for item in result.assets:
                count = len(item.trades)
                db.execute(
                    "INSERT INTO portfolio_asset_results VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        strategy_number,
                        item.symbol,
                        item.pnl,
                        item.pnl / item.capital_deployed
                        if item.capital_deployed
                        else 0.0,
                        item.capital_deployed,
                        item.peak_capital_at_risk,
                        count,
                        item.wins,
                        item.losses,
                        item.wins / count if count else 0.0,
                        int(item.pnl >= 0),
                    ),
                )
            for trade in result.trades:
                db.execute(
                    "INSERT INTO portfolio_trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        strategy_number,
                        trade.symbol,
                        trade.sequence,
                        trade.entry_time.isoformat(),
                        trade.exit_time.isoformat(),
                        trade.entry_price,
                        trade.exit_price,
                        trade.duration_seconds,
                        trade.invested_capital,
                        trade.pnl,
                        trade.pnl_pct,
                        trade.exit_reason,
                    ),
                )
            for point in result.equity_curve:
                db.execute(
                    "INSERT INTO portfolio_equity VALUES(?,?,?,?,?)",
                    (
                        strategy_number,
                        point["timestamp"],
                        point["equity"],
                        point["cash"],
                        point["open_positions"],
                    ),
                )
            final_point = result.equity_curve[-1]
            final_status = "ABORTED_DRAWDOWN" if result.aborted else "COMPLETE"
            marks = benchmark.evaluate(
                bars_by_symbol,
                datetime.fromisoformat(period_start),
                datetime.fromisoformat(final_point["timestamp"]),
                result.return_pct,
                self.settings.commission_bps,
                self.settings.slippage_bps,
            )
            db.execute(
                """UPDATE portfolio_backtest_runs SET status=?,current_date=?,
                   current_equity=?,final_equity=?,net_profit=?,return_pct=?,max_drawdown=?,
                   processed_days=?,assets_traded=?,trades=?,wins=?,losses=?,win_rate=?,
                   open_positions=0,cash=?,updated_at=?,benchmark_buy_and_hold=?,
                   benchmark_equal_weight=?,benchmark_reference=?,
                   benchmark_reference_name=?,excess_return=?,engine_version=?,
                   average_exposure=?,peak_exposure=?,time_in_market=?,
                   capital_drawdown=?,drawdown_basis=?,last_active_timestamp=?
                   WHERE strategy_number=?""",
                (
                    final_status,
                    final_point["timestamp"],
                    result.final_equity,
                    result.final_equity,
                    result.final_equity - result.initial_capital,
                    result.return_pct,
                    result.max_drawdown,
                    len(result.equity_curve),
                    sum(bool(item.trades) for item in result.assets),
                    len(result.trades),
                    result.wins,
                    result.losses,
                    result.wins / len(result.trades) if result.trades else 0.0,
                    result.cash,
                    utc_now(),
                    marks["buy_and_hold"],
                    marks["equal_weight"],
                    marks["reference"],
                    marks["reference_name"],
                    marks["excess_return"],
                    ENGINE_VERSION,
                    result.average_exposure,
                    result.peak_exposure,
                    result.time_in_market,
                    result.capital_drawdown,
                    policy.drawdown_basis,
                    result.last_active_timestamp,
                    strategy_number,
                ),
            )
        report = {
            "strategy_number": strategy_number,
            "long_only": True,
            "shared_portfolio": True,
            "assets_evaluated": len(result.assets),
            "assets_traded": sum(bool(x.trades) for x in result.assets),
            "initial_capital": result.initial_capital,
            "final_equity": result.final_equity,
            "return_pct": result.return_pct,
            "max_drawdown": result.max_drawdown,
            "phase1_score": result.return_pct - result.max_drawdown,
            "status": "ABORTED_DRAWDOWN" if result.aborted else "COMPLETE",
            "abort_reason": result.abort_reason,
            "trades": len(result.trades),
            "wins": result.wins,
            "losses": result.losses,
            # Published alongside the return, never separately: the return is
            # not readable without knowing how much capital produced it.
            "average_exposure": result.average_exposure,
            "peak_exposure": result.peak_exposure,
            "time_in_market": result.time_in_market,
            # Both drawdown measures, plus which one the mandate bound on.
            "capital_drawdown": result.capital_drawdown,
            "drawdown_basis": policy.drawdown_basis,
            "last_active_timestamp": result.last_active_timestamp,
            "policy_calibration": policy.exposure_calibration,
            "assets_evaluated_vs_full_investment": (
                len(result.assets)
                / policy.exposure_calibration["assets_for_full_investment"]
                if policy.exposure_calibration["assets_for_full_investment"]
                else None
            ),
        }
        # The control group. Reported on every run, because an absolute return
        # without one is what produced nine incomparable results here.
        report["contrast"] = self._contrast(
            bars_by_symbol,
            policy,
            CostModel(self.settings.commission_bps, self.settings.slippage_bps),
            capital,
            (override or {}).get("interval"),
            result.return_pct,
            result.max_drawdown,
            selected["family"],
            params,
        )
        # Folding is worth its cost only for a candidate that already cleared
        # criterion 10's Phase-1 bar. Most candidates do not, so gating here
        # keeps the walk-forward instrument from multiplying the backtest cost
        # of every seed and mutation by the fold count.
        if report["status"] == "COMPLETE" and report["return_pct"] > 0:
            report["walkforward"] = self._evaluate_walkforward(
                strategy_number,
                selected["family"],
                params,
                engine.costs,
                engine.policy,
                capital,
                bars_by_symbol,
                datetime.fromisoformat(period_start),
                cutoff,
            )
        target = (
            self.settings.research_root
            / "strategy_reports"
            / f"S{strategy_number:05d}.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return report

    def _evaluate_walkforward(
        self,
        strategy_number: int,
        family: str,
        params: dict[str, Any],
        costs: CostModel,
        policy: MoneyManagement,
        capital: float,
        bars_by_symbol: dict[str, list[Bar]],
        period_start: datetime,
        cutoff: datetime,
    ) -> dict[str, Any]:
        """Score the same candidate on folds it was never fitted to.

        Reuses the bars and policy the Phase-1 run already built rather than
        reloading from disk, so this costs backtest time and nothing else.
        """
        folds = walkforward.rolling_folds(period_start, cutoff)
        if not folds:
            return {
                "folds_evaluated": 0,
                "eligible": False,
                "reason": "history too short for one fold",
            }

        def on_fold(outcome: walkforward.FoldOutcome) -> None:
            if self.activity:
                self.activity(
                    "PHASE1_WALKFORWARD",
                    json.dumps(
                        {
                            "strategy": strategy_number,
                            "fold_index": outcome.fold_index,
                            "folds_total": len(folds),
                            "test_start": outcome.test_start.isoformat(),
                            "test_end": outcome.test_end.isoformat(),
                        }
                    ),
                )

        # The same market context the Phase-1 run used. A fold is a window over
        # the same bars, not a different world, so rebuilding the regime per
        # fold would give each fold its own warmup and its own first labels --
        # the folds would then differ by detector state as well as by period.
        context = self._market_context(family)
        outcomes = walkforward.WalkForwardEvaluator(costs, policy, capital, folds).run(
            bars_by_symbol, lambda: build_strategy(family, params, context), on_fold
        )
        score = walkforward.evaluate_folds(outcomes)
        walkforward.record(self.memory, strategy_number, outcomes, score)
        return {
            "folds_evaluated": score.folds_evaluated,
            "folds_profitable": score.folds_profitable,
            "consistency": score.consistency,
            "median_score": score.median_score,
            "eligible": score.eligible,
            "reason": score.reason,
        }
