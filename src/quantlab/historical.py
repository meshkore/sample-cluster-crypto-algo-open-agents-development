from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from .backtest import CostModel
from .config import Settings
from .data import DataManager
from .memory import ExperimentMemory
from .models import utc_now
from .portfolio import LongOnlyPortfolioBacktester, MoneyManagement
from .strategies import build_strategy


class HistoricalUniverseEvaluator:
    """One chronological, shared-capital portfolio over the complete ready universe."""

    def __init__(
        self,
        settings: Settings,
        memory: ExperimentMemory,
        activity: Callable[[str, str], None] | None = None,
    ):
        self.settings, self.memory, self.activity = settings, memory, activity

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
        if not selected or not assets:
            return None
        strategy_number = int(selected["strategy_number"])
        # Phase 1 always uses all information strictly before 2026. Phase 2 is
        # physically separate and can never feed strategy generation.
        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
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
        policy_keys = (
            "risk_per_trade",
            "maximum_position_fraction",
            "stop_loss_pct",
            "take_profit_pct",
            "minimum_confidence",
            "long_only",
            "maximum_concurrent_assets",
            "minimum_order_notional",
            "minimum_position_fraction",
            "maximum_drawdown",
            "drawdown_safety_buffer",
            "volatility_target",
            "volatility_lookback",
            "minimum_daily_quote_volume",
            "volume_lookback",
            "maximum_volume_participation",
            "drawdown_deleverage_start",
        )
        stored_policy = json.loads(selected["money_management_json"])
        policy = MoneyManagement(
            **{
                key: stored_policy.get(key, self.settings.portfolio[key])
                for key in policy_keys
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
                        0,
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

        result = engine.run(
            bars_by_symbol,
            lambda: build_strategy(selected["family"], params),
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
            db.execute(
                """UPDATE portfolio_backtest_runs SET status=?,current_date=?,
                   current_equity=?,final_equity=?,net_profit=?,return_pct=?,max_drawdown=?,
                   processed_days=?,assets_traded=?,trades=?,wins=?,losses=?,win_rate=?,
                   open_positions=0,cash=?,updated_at=? WHERE strategy_number=?""",
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
        }
        target = (
            self.settings.research_root
            / "strategy_reports"
            / f"S{strategy_number:05d}.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return report
