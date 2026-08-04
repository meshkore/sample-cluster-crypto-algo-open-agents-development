from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from . import benchmark
from .backtest import CostModel
from .config import Settings
from .data import DataManager, FAMILY_DATA_OVERRIDES, FocusedDataset
from .memory import ExperimentMemory
from .models import ENGINE_VERSION, Bar, utc_now
from .portfolio import LongOnlyPortfolioBacktester, MoneyManagement
from .strategies import build_strategy


class ForwardEvaluator:
    """Phase 2: untouched 2026-to-present shared-portfolio evaluation."""

    def __init__(
        self,
        settings: Settings,
        memory: ExperimentMemory,
        activity: Callable[[str, str, dict[str, Any]], None] | None = None,
    ):
        self.settings, self.memory, self.activity = settings, memory, activity

    def qualified_strategy(self) -> dict[str, Any] | None:
        """The best real Phase-1 portfolio result earns Phase 2 (criterion 10).

        This deliberately does NOT gate on `experiments.status='PROMOTE'`. That
        row is produced by `ResearchDirector`, which backtests a single
        synthetic BTCUSDT series and whose critic hardcodes REJECT for
        synthetic evidence — so the gate could never open, and 132 profitable
        real portfolio backtests were locked out of the forward phase while the
        public champion stayed pinned to nine stale, losing runs.

        Criterion 10 defines advancement on the real Phase-1 evidence: positive
        final equity against the shared USD 100,000 portfolio, under the 25%
        drawdown limit, over history that ends with 2025, ranked by
        `return - maximum drawdown`. That is exactly what this selects.
        """
        query = """SELECT e.*,s.family,s.signal_json,s.execution_json,s.money_management_json,
                          p.return_pct phase1_return,p.max_drawdown phase1_drawdown,
                          (p.return_pct-p.max_drawdown) phase1_score
                   FROM portfolio_backtest_runs p
                   JOIN experiments e ON e.strategy_number=p.strategy_number
                   JOIN strategy_definitions s ON s.strategy_number=p.strategy_number
                   WHERE p.status='COMPLETE'
                     AND p.final_equity>p.initial_capital
                     AND p.max_drawdown < 0.25
                     AND p.trades > 0
                     AND p.period_end>='2025-12-31'
                     {unevaluated}
                   ORDER BY phase1_score DESC,p.return_pct DESC,e.created_at DESC LIMIT 1"""
        unevaluated = """AND NOT EXISTS (SELECT 1 FROM forward_portfolio_runs f
                            WHERE f.strategy_number=p.strategy_number
                              AND f.run_id NOT LIKE '%-LIVE')"""
        with self.memory.session() as db:
            # Drain the queue in score order: the best candidate that has never
            # reached 2026 goes first. Without this the selector returns the same
            # record holder forever and the rest of the eligible field — 132
            # profitable backtests when this was found — is never forward-tested.
            row = db.execute(query.format(unevaluated=unevaluated)).fetchone()
            if not row:
                row = db.execute(query.format(unevaluated="")).fetchone()
        return dict(row) if row else None

    def _universe_bars(self, lock: datetime) -> dict[str, list[Bar]]:
        """The shared daily universe: pre-2026 history spliced with 2026 bars."""
        with self.memory.session() as db:
            assets = db.execute(
                """SELECT u.symbol,u.research_path,u.forward_path
                   FROM asset_universe u JOIN asset_liquidity l USING(symbol)
                   WHERE u.forward_path IS NOT NULL AND l.eligible=1 ORDER BY u.symbol"""
            ).fetchall()
        bars_by_symbol: dict[str, list[Bar]] = {}
        for asset in assets:
            historical = (
                DataManager.load_csv(asset["research_path"])
                if asset["research_path"]
                else []
            )
            forward = [
                bar
                for bar in DataManager.load_csv(asset["forward_path"])
                if bar.timestamp >= lock
            ]
            if not forward:
                continue
            combined = {
                bar.timestamp: bar for bar in historical if bar.timestamp < lock
            }
            combined.update({bar.timestamp: bar for bar in forward})
            bars_by_symbol[asset["symbol"]] = [
                combined[key] for key in sorted(combined)
            ]
        return bars_by_symbol

    def _focused_bars(
        self, symbols: list[str], interval: str, lock: datetime
    ) -> dict[str, list[Bar]]:
        """An override family's own symbols and interval, history plus 2026."""

        def on_exclude(symbol: str, reason: str) -> None:
            if self.activity:
                self.activity(
                    "FORWARD_2026",
                    "data",
                    {"symbol": symbol, "excluded": reason[:200]},
                )

        dataset = FocusedDataset(
            self.settings.data_root,
            self.settings.splits["future_lock_start"],
            on_exclude=on_exclude,
        )
        end = datetime.now(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ) + timedelta(hours=1)
        return dataset.combined_bars(symbols, interval, end)

    def evaluate(self, candidate_strategy_number: int | None = None) -> str | None:
        selected = self.qualified_strategy()
        if not selected:
            return None
        if (
            candidate_strategy_number is not None
            and int(selected["strategy_number"]) != candidate_strategy_number
        ):
            return None
        lock = datetime.fromisoformat(
            self.settings.splits["future_lock_start"].replace("Z", "+00:00")
        )
        override = FAMILY_DATA_OVERRIDES.get(selected["family"])
        if override:
            # A family swept on its own timeframe must be forward-tested on
            # that same timeframe and symbol list. Reading `asset_universe`
            # here instead would silently hand it daily candles over 386
            # assets, making the two phases incomparable.
            bars_by_symbol = self._focused_bars(
                override["symbols"], override["interval"], lock
            )
        else:
            bars_by_symbol = self._universe_bars(lock)
        if not bars_by_symbol:
            return None
        forward_ends = [
            bars[-1].timestamp
            for bars in bars_by_symbol.values()
            if bars[-1].timestamp >= lock
        ]
        if not forward_ends:
            return None
        policy_keys = (
            "risk_per_trade",
            "maximum_position_fraction",
            "stop_loss_pct",
            "take_profit_pct",
            "minimum_confidence",
            "long_only",
            "maximum_concurrent_assets",
            "minimum_order_notional",
            "maximum_drawdown",
            "drawdown_safety_buffer",
            "volatility_target",
            "volatility_lookback",
            "minimum_daily_quote_volume",
            "volume_lookback",
            "maximum_volume_participation",
            "drawdown_deleverage_start",
            # QUANT14: the sizing distance, separate from the exit distance.
            # Absent from a stored policy it stays None and falls back to
            # stop_loss_pct, which is exactly the old behaviour.
            "risk_distance_pct",
        )
        stored_policy = json.loads(selected["money_management_json"])
        policy = MoneyManagement(
            **{
                key: stored_policy.get(key, self.settings.portfolio.get(key))
                for key in policy_keys
            }
        )
        capital = float(self.settings.portfolio["initial_capital"])
        params = json.loads(selected["parameters_json"])
        engine = LongOnlyPortfolioBacktester(
            CostModel(
                self.settings.commission_bps,
                self.settings.slippage_bps,
                self.settings.funding_bps_per_bar,
            ),
            policy,
        )
        live_run_id = f"FWD2-S{selected['strategy_number']:05d}-LIVE"
        target_end = max(forward_ends)
        with self.memory.session() as db:
            already_current = db.execute(
                """SELECT 1 FROM forward_portfolio_runs WHERE strategy_number=?
                   AND status!='FORWARD_TESTING' AND COALESCE(target_end,period_end)>=? LIMIT 1""",
                (selected["strategy_number"], target_end.isoformat()),
            ).fetchone()
        if already_current:
            return None
        with self.memory.transaction() as db:
            db.execute(
                "DELETE FROM forward_portfolio_trades WHERE run_id=?", (live_run_id,)
            )
            db.execute(
                "DELETE FROM forward_portfolio_assets WHERE run_id=?", (live_run_id,)
            )
            db.execute(
                "DELETE FROM forward_portfolio_equity WHERE run_id=?", (live_run_id,)
            )
            db.execute(
                "DELETE FROM forward_portfolio_runs WHERE run_id=?", (live_run_id,)
            )
            total_forward_days = len(
                {
                    bar.timestamp
                    for bars in bars_by_symbol.values()
                    for bar in bars
                    if bar.timestamp >= lock
                }
            )
            db.execute(
                """INSERT INTO forward_portfolio_runs(
                       run_id,strategy_number,period_start,period_end,as_of,initial_capital,
                       final_equity,net_profit,return_pct,max_drawdown,score,trades,wins,losses,
                       win_rate,assets_available,assets_traded,cash,status,current_date,target_end,
                       processed_days,total_days,open_positions)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    live_run_id,
                    selected["strategy_number"],
                    lock.isoformat(),
                    lock.isoformat(),
                    utc_now(),
                    capital,
                    capital,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0,
                    0,
                    0,
                    0.0,
                    len(bars_by_symbol),
                    0,
                    capital,
                    "FORWARD_PREPARING",
                    lock.isoformat(),
                    target_end.isoformat(),
                    0,
                    total_forward_days,
                    0,
                ),
            )

        def on_preparation(point: dict[str, Any]) -> None:
            if self.activity:
                self.activity(
                    "FORWARD_PREPARING",
                    f"Preparing forward signals {point['prepared_assets']}/{point['total_assets']} · {point['symbol']}",
                    point,
                )

        def on_progress(point: dict[str, Any]) -> None:
            score = point["equity"] / capital - 1 - point["max_drawdown"]
            with self.memory.transaction() as db:
                db.execute(
                    """INSERT INTO forward_portfolio_runs(
                       run_id,strategy_number,period_start,period_end,as_of,initial_capital,
                       final_equity,net_profit,return_pct,max_drawdown,score,trades,wins,losses,
                       win_rate,assets_available,assets_traded,cash,status,current_date,target_end,
                       processed_days,total_days,open_positions)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(run_id) DO UPDATE SET period_end=excluded.period_end,
                       as_of=excluded.as_of,final_equity=excluded.final_equity,
                       net_profit=excluded.net_profit,return_pct=excluded.return_pct,
                       max_drawdown=excluded.max_drawdown,score=excluded.score,
                       trades=excluded.trades,wins=excluded.wins,losses=excluded.losses,
                       win_rate=excluded.win_rate,cash=excluded.cash,status=excluded.status,
                       current_date=excluded.current_date,target_end=excluded.target_end,
                       processed_days=excluded.processed_days,total_days=excluded.total_days,
                       assets_traded=excluded.assets_traded,
                       open_positions=excluded.open_positions""",
                    (
                        live_run_id,
                        selected["strategy_number"],
                        lock.isoformat(),
                        point["timestamp"],
                        utc_now(),
                        capital,
                        point["equity"],
                        point["equity"] - capital,
                        point["equity"] / capital - 1,
                        point["max_drawdown"],
                        score,
                        point["trades"],
                        point["wins"],
                        point["losses"],
                        point["wins"] / point["trades"] if point["trades"] else 0.0,
                        len(bars_by_symbol),
                        point.get("assets_traded", 0),
                        point["cash"],
                        "FORWARD_TESTING",
                        point["timestamp"],
                        target_end.isoformat(),
                        point["processed_days"],
                        point["total_days"],
                        point["open_positions"],
                    ),
                )
                db.execute(
                    "INSERT OR REPLACE INTO forward_portfolio_equity VALUES(?,?,?,?,?)",
                    (
                        live_run_id,
                        point["timestamp"],
                        point["equity"],
                        point["cash"],
                        point["open_positions"],
                    ),
                )
                for trade in point.get("closed_trades", []):
                    db.execute(
                        "INSERT OR REPLACE INTO forward_portfolio_trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            live_run_id,
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
            if self.activity:
                public = {
                    key: value for key, value in point.items() if key != "closed_trades"
                }
                self.activity(
                    "FORWARD_TESTING", "Phase 2 · forward from 2026-01-01", public
                )

        result = engine.run(
            bars_by_symbol,
            lambda: build_strategy(selected["family"], params),
            capital,
            on_progress,
            trading_start=lock,
            preparation_progress=on_preparation,
        )
        end = datetime.fromisoformat(result.equity_curve[-1]["timestamp"])
        run_id = f"FWD2-S{selected['strategy_number']:05d}-{end.strftime('%Y%m%d')}"
        score = result.return_pct - result.max_drawdown
        # What the same capital would have done over the same window doing
        # nothing clever. Without it a small positive number means nothing.
        marks = benchmark.evaluate(
            bars_by_symbol,
            lock,
            end,
            result.return_pct,
            self.settings.commission_bps,
            self.settings.slippage_bps,
        )
        with self.memory.transaction() as db:
            db.execute(
                "DELETE FROM forward_portfolio_trades WHERE run_id=?", (live_run_id,)
            )
            db.execute(
                "DELETE FROM forward_portfolio_assets WHERE run_id=?", (live_run_id,)
            )
            db.execute(
                "DELETE FROM forward_portfolio_equity WHERE run_id=?", (live_run_id,)
            )
            db.execute(
                "DELETE FROM forward_portfolio_runs WHERE run_id=?", (live_run_id,)
            )
            db.execute("DELETE FROM forward_portfolio_trades WHERE run_id=?", (run_id,))
            db.execute("DELETE FROM forward_portfolio_assets WHERE run_id=?", (run_id,))
            db.execute("DELETE FROM forward_portfolio_equity WHERE run_id=?", (run_id,))
            db.execute("DELETE FROM forward_portfolio_runs WHERE run_id=?", (run_id,))
            db.execute(
                """INSERT INTO forward_portfolio_runs(
                       run_id,strategy_number,period_start,period_end,as_of,initial_capital,
                       final_equity,net_profit,return_pct,max_drawdown,score,trades,wins,losses,
                       win_rate,assets_available,assets_traded,cash,status,current_date,target_end,
                       processed_days,total_days,open_positions,benchmark_buy_and_hold,
                       benchmark_equal_weight,benchmark_reference,benchmark_reference_name,
                       excess_return,engine_version,
                       average_exposure,peak_exposure,time_in_market)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    selected["strategy_number"],
                    lock.isoformat(),
                    end.isoformat(),
                    utc_now(),
                    capital,
                    result.final_equity,
                    result.final_equity - capital,
                    result.return_pct,
                    result.max_drawdown,
                    score,
                    len(result.trades),
                    result.wins,
                    result.losses,
                    result.wins / len(result.trades) if result.trades else 0.0,
                    len(result.assets),
                    sum(bool(item.trades) for item in result.assets),
                    result.cash,
                    "FORWARD_ABORTED_DRAWDOWN" if result.aborted else "FORWARD_2026",
                    result.equity_curve[-1]["timestamp"],
                    target_end.isoformat(),
                    len(result.equity_curve),
                    result.equity_curve[-1]["total_days"],
                    0,
                    marks["buy_and_hold"],
                    marks["equal_weight"],
                    marks["reference"],
                    marks["reference_name"],
                    marks["excess_return"],
                    ENGINE_VERSION,
                    result.average_exposure,
                    result.peak_exposure,
                    result.time_in_market,
                ),
            )
            for item in result.assets:
                count = len(item.trades)
                db.execute(
                    "INSERT INTO forward_portfolio_assets VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
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
                    "INSERT INTO forward_portfolio_trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
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
                    "INSERT INTO forward_portfolio_equity VALUES(?,?,?,?,?)",
                    (
                        run_id,
                        point["timestamp"],
                        point["equity"],
                        point["cash"],
                        point["open_positions"],
                    ),
                )
        return run_id

    def latest(self) -> dict[str, Any] | None:
        """Best Phase-2 result, ranked exclusively on 2026-forward evidence."""
        with self.memory.session() as db:
            run = db.execute(
                """SELECT f.* FROM forward_portfolio_runs f
                   JOIN experiments e ON e.strategy_number=f.strategy_number
                   WHERE f.status='FORWARD_2026' AND e.status IN ('PROMOTE','CHAMPION')
                   AND f.max_drawdown<0.25
                   ORDER BY score DESC,return_pct DESC,as_of DESC LIMIT 1"""
            ).fetchone()
            if not run:
                return None
            assets = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM forward_portfolio_assets WHERE run_id=? ORDER BY pnl DESC,symbol",
                    (run["run_id"],),
                )
            ]
            trades = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM forward_portfolio_trades WHERE run_id=? ORDER BY exit_time DESC,symbol,sequence",
                    (run["run_id"],),
                )
            ]
            equity = [
                dict(row)
                for row in db.execute(
                    "SELECT timestamp,equity,cash,open_positions FROM forward_portfolio_equity WHERE run_id=? ORDER BY timestamp",
                    (run["run_id"],),
                )
            ]
        result = dict(run)
        result["assets"], result["trades_ledger"], result["equity_curve"] = (
            assets,
            trades,
            equity,
        )
        return result

    def active(self) -> dict[str, Any] | None:
        with self.memory.session() as db:
            run = db.execute(
                """SELECT f.* FROM forward_portfolio_runs f
                   JOIN experiments e ON e.strategy_number=f.strategy_number
                   WHERE f.run_id LIKE '%-LIVE' AND e.status IN ('PROMOTE','CHAMPION')
                   AND f.status IN ('FORWARD_PREPARING','FORWARD_TESTING')
                   ORDER BY f.as_of DESC LIMIT 1"""
            ).fetchone()
            if not run:
                return None
            assets = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM forward_portfolio_assets WHERE run_id=? ORDER BY pnl DESC,symbol",
                    (run["run_id"],),
                )
            ]
            trades = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM forward_portfolio_trades WHERE run_id=? ORDER BY exit_time DESC,symbol,sequence",
                    (run["run_id"],),
                )
            ]
            equity = [
                dict(row)
                for row in db.execute(
                    "SELECT timestamp,equity,cash,open_positions FROM forward_portfolio_equity WHERE run_id=? ORDER BY timestamp",
                    (run["run_id"],),
                )
            ]
        result = dict(run)
        result["assets"], result["trades_ledger"], result["equity_curve"] = (
            assets,
            trades,
            equity,
        )
        return result
