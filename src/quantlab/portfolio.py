from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import math
import time
from typing import Any, Callable

from .backtest import CostModel
from .models import Bar


@dataclass(frozen=True)
class MoneyManagement:
    risk_per_trade: float = 0.01
    maximum_position_fraction: float = 0.25
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    minimum_confidence: float = 0.25
    long_only: bool = True
    maximum_concurrent_assets: int = 100
    minimum_order_notional: float = 10.0
    maximum_drawdown: float = 0.25
    drawdown_safety_buffer: float = 0.05
    volatility_target: float = 0.025
    volatility_lookback: int = 20


@dataclass(frozen=True)
class CompletedTrade:
    sequence: int
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    invested_capital: float
    duration_seconds: float
    pnl: float
    pnl_pct: float
    exit_reason: str

    def document(self) -> dict[str, Any]:
        result = asdict(self)
        result["entry_time"] = self.entry_time.isoformat()
        result["exit_time"] = self.exit_time.isoformat()
        return result


@dataclass
class AssetEvaluation:
    symbol: str
    initial_capital: float
    final_equity: float
    return_pct: float
    survived: bool
    wins: int
    losses: int
    win_rate: float
    trades: list[CompletedTrade]


@dataclass
class PortfolioAssetEvaluation:
    symbol: str
    pnl: float
    capital_deployed: float
    peak_capital_at_risk: float
    wins: int
    losses: int
    trades: list[CompletedTrade]


@dataclass
class PortfolioEvaluation:
    initial_capital: float
    final_equity: float
    cash: float
    return_pct: float
    max_drawdown: float
    wins: int
    losses: int
    trades: list[CompletedTrade]
    assets: list[PortfolioAssetEvaluation]
    equity_curve: list[dict[str, Any]]
    aborted: bool = False
    abort_reason: str | None = None


@dataclass
class _Position:
    symbol: str
    quantity: float
    entry_time: datetime
    entry_price: float
    invested: float


class LongOnlyPortfolioBacktester:
    """Chronological shared-capital simulation across every available asset."""

    def __init__(self, costs: CostModel, policy: MoneyManagement):
        if not policy.long_only:
            raise ValueError("this laboratory only permits long-only policies")
        if not 0 < policy.risk_per_trade <= 1 or not 0 < policy.stop_loss_pct < 1:
            raise ValueError("invalid risk policy")
        self.costs, self.policy = costs, policy

    def run(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        strategy_factory: Callable[[], Any],
        initial_capital: float,
        progress: Callable[[dict[str, Any]], None] | None = None,
        trading_start: datetime | None = None,
        preparation_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> PortfolioEvaluation:
        prepared = {
            symbol: sorted(bars, key=lambda x: x.timestamp)
            for symbol, bars in bars_by_symbol.items()
            if len(bars) >= 3
        }
        if initial_capital <= 0 or not prepared:
            raise ValueError(
                "positive capital and at least one usable asset are required"
            )
        indexes = {
            symbol: {bar.timestamp: bar for bar in bars}
            for symbol, bars in prepared.items()
        }
        signals: dict[str, dict[datetime, float]] = {}
        volatilities: dict[str, dict[datetime, float]] = {}
        for symbol_index, (symbol, bars) in enumerate(prepared.items(), 1):
            strategy = strategy_factory()
            if hasattr(strategy, "reset"):
                strategy.reset()
            series: dict[datetime, float] = {}
            vol_series: dict[datetime, float] = {}
            observed: list[Bar] = []
            for end, bar in enumerate(bars, 1):
                if end % 250 == 0:
                    time.sleep(0.001)
                observed.append(bar)
                raw = (
                    strategy.on_bar(observed)
                    if hasattr(strategy, "on_bar")
                    else strategy(observed)
                )
                series[bar.timestamp] = max(0.0, min(1.0, float(raw)))
                start = max(1, end - self.policy.volatility_lookback)
                returns = [
                    math.log(bars[i].close / bars[i - 1].close)
                    for i in range(start, end)
                ]
                if len(returns) >= 2:
                    mean = sum(returns) / len(returns)
                    vol_series[bar.timestamp] = math.sqrt(
                        sum((value - mean) ** 2 for value in returns)
                        / (len(returns) - 1)
                    )
                else:
                    vol_series[bar.timestamp] = self.policy.volatility_target
            signals[symbol] = series
            volatilities[symbol] = vol_series
            if preparation_progress:
                preparation_progress(
                    {
                        "symbol": symbol,
                        "prepared_assets": symbol_index,
                        "total_assets": len(prepared),
                    }
                )
            time.sleep(0)
        full_timeline = sorted(
            {stamp for series in indexes.values() for stamp in series}
        )
        timeline = [
            stamp
            for stamp in full_timeline
            if trading_start is None or stamp >= trading_start
        ]
        if not timeline:
            raise ValueError("no bars exist inside the requested trading period")
        cash, peak_equity, max_drawdown = initial_capital, initial_capital, 0.0
        positions: dict[str, _Position] = {}
        trades: list[CompletedTrade] = []
        last_signal = {}
        first_trade_stamp = timeline[0]
        for symbol in prepared:
            warmup = [stamp for stamp in signals[symbol] if stamp < first_trade_stamp]
            last_signal[symbol] = signals[symbol][max(warmup)] if warmup else 0.0
        deployed = {symbol: 0.0 for symbol in prepared}
        peak_risk = {symbol: 0.0 for symbol in prepared}
        equity_curve: list[dict[str, Any]] = []
        progress_trade_cursor = 0

        def close(symbol: str, bar: Bar, raw_price: float, reason: str) -> None:
            nonlocal cash
            position = positions.pop(symbol)
            fill = raw_price * (1 - self.costs.slippage_bps / 10_000)
            proceeds = position.quantity * fill
            cash += proceeds - proceeds * self.costs.commission_bps / 10_000
            pnl = (
                proceeds
                - proceeds * self.costs.commission_bps / 10_000
                - position.invested
            )
            sequence = 1 + sum(item.symbol == symbol for item in trades)
            trades.append(
                CompletedTrade(
                    sequence,
                    symbol,
                    position.entry_time,
                    bar.timestamp,
                    position.entry_price,
                    fill,
                    position.invested,
                    (bar.timestamp - position.entry_time).total_seconds(),
                    pnl,
                    pnl / position.invested if position.invested else 0.0,
                    reason,
                )
            )

        aborted, abort_reason = False, None
        last_processed_stamp = timeline[0]
        for day_index, stamp in enumerate(timeline):
            last_processed_stamp = stamp
            if day_index % 25 == 0:
                time.sleep(0)
            todays = {
                symbol: series[stamp]
                for symbol, series in indexes.items()
                if stamp in series
            }
            for symbol, position in list(positions.items()):
                bar = todays.get(symbol)
                if not bar:
                    continue
                stop = position.entry_price * (1 - self.policy.stop_loss_pct)
                take = position.entry_price * (1 + self.policy.take_profit_pct)
                if bar.low <= stop:
                    close(symbol, bar, stop, "STOP_LOSS")
                elif bar.high >= take:
                    close(symbol, bar, take, "TAKE_PROFIT")
                elif last_signal[symbol] < self.policy.minimum_confidence:
                    close(symbol, bar, bar.open, "SIGNAL_EXIT")
            candidates = sorted(
                (
                    (last_signal[s], s)
                    for s in todays
                    if s not in positions
                    and last_signal[s] >= self.policy.minimum_confidence
                ),
                reverse=True,
            )
            for confidence, symbol in candidates:
                if len(positions) >= self.policy.maximum_concurrent_assets:
                    break
                equity = cash + sum(
                    p.quantity
                    * todays.get(
                        s, indexes[s][max(t for t in indexes[s] if t <= stamp)]
                    ).open
                    for s, p in positions.items()
                )
                observed_vol = volatilities[symbol].get(
                    stamp, self.policy.volatility_target
                )
                volatility_scale = min(
                    1.0, self.policy.volatility_target / max(observed_vol, 1e-9)
                )
                risk_budget = (
                    equity * self.policy.risk_per_trade * confidence * volatility_scale
                )
                notional = min(
                    cash,
                    equity * self.policy.maximum_position_fraction,
                    risk_budget / self.policy.stop_loss_pct,
                )
                if notional < self.policy.minimum_order_notional:
                    continue
                bar = todays[symbol]
                fill = bar.open * (1 + self.costs.slippage_bps / 10_000)
                fee = notional * self.costs.commission_bps / 10_000
                quantity = (notional - fee) / fill
                cash -= notional
                positions[symbol] = _Position(symbol, quantity, stamp, fill, notional)
                deployed[symbol] += notional
                peak_risk[symbol] = max(peak_risk[symbol], notional)
            for symbol, bar in todays.items():
                last_signal[symbol] = signals[symbol][stamp]
            marked = cash + sum(
                position.quantity * todays[symbol].close
                for symbol, position in positions.items()
                if symbol in todays
            )
            # Assets without a bar today retain their latest available close.
            for symbol, position in positions.items():
                if symbol not in todays:
                    prior = max(t for t in indexes[symbol] if t <= stamp)
                    marked += position.quantity * indexes[symbol][prior].close
            peak_equity = max(peak_equity, marked)
            max_drawdown = max(
                max_drawdown, 1 - marked / peak_equity if peak_equity else 0.0
            )
            drawdown_trigger = (
                self.policy.maximum_drawdown - self.policy.drawdown_safety_buffer
            )
            if max_drawdown >= drawdown_trigger:
                for symbol in list(positions):
                    bar = todays.get(symbol)
                    if bar is None:
                        prior = max(t for t in indexes[symbol] if t <= stamp)
                        bar = indexes[symbol][prior]
                    close(symbol, bar, bar.close, "MAX_DRAWDOWN_ABORT")
                marked = cash
                max_drawdown = max(
                    max_drawdown, 1 - marked / peak_equity if peak_equity else 0.0
                )
                aborted, abort_reason = True, "DRAWDOWN_SAFETY_TRIGGER"
            point = {
                "timestamp": stamp.isoformat(),
                "equity": marked,
                "cash": cash,
                "open_positions": len(positions),
                "processed_days": day_index + 1,
                "total_days": len(timeline),
                "trades": len(trades),
                "wins": sum(trade.pnl > 0 for trade in trades),
                "losses": sum(trade.pnl <= 0 for trade in trades),
                "max_drawdown": max_drawdown,
                "aborted": aborted,
                "abort_reason": abort_reason,
            }
            equity_curve.append(point)
            if progress and (
                day_index % 10 == 0 or day_index == len(timeline) - 1 or aborted
            ):
                progress_point = {
                    **point,
                    "closed_trades": [
                        trade.document() for trade in trades[progress_trade_cursor:]
                    ],
                }
                progress(progress_point)
                progress_trade_cursor = len(trades)
            if aborted:
                break
        final_stamp = last_processed_stamp
        for symbol in list(positions):
            bar = indexes[symbol][max(t for t in indexes[symbol] if t <= final_stamp)]
            close(symbol, bar, bar.close, "MARK_TO_MARKET")
        final_equity = cash
        by_asset = []
        for symbol in sorted(prepared):
            symbol_trades = [trade for trade in trades if trade.symbol == symbol]
            wins = sum(trade.pnl > 0 for trade in symbol_trades)
            by_asset.append(
                PortfolioAssetEvaluation(
                    symbol,
                    sum(t.pnl for t in symbol_trades),
                    deployed[symbol],
                    peak_risk[symbol],
                    wins,
                    len(symbol_trades) - wins,
                    symbol_trades,
                )
            )
        wins = sum(trade.pnl > 0 for trade in trades)
        return PortfolioEvaluation(
            initial_capital,
            final_equity,
            cash,
            final_equity / initial_capital - 1,
            max_drawdown,
            wins,
            len(trades) - wins,
            trades,
            by_asset,
            equity_curve,
            aborted,
            abort_reason,
        )


class LongOnlyExecutionBacktester:
    """Signal-independent execution, risk sizing and protective-exit simulator."""

    def __init__(self, costs: CostModel, policy: MoneyManagement):
        if not policy.long_only:
            raise ValueError("this laboratory only permits long-only policies")
        if not 0 < policy.risk_per_trade <= 1 or not 0 < policy.stop_loss_pct < 1:
            raise ValueError("invalid risk policy")
        self.costs, self.policy = costs, policy

    def run(
        self, symbol: str, bars: list[Bar], strategy: Any, initial_capital: float
    ) -> AssetEvaluation:
        if initial_capital <= 0 or len(bars) < 3:
            raise ValueError("positive capital and at least three bars are required")
        if hasattr(strategy, "reset"):
            strategy.reset()
        signals = []
        for end in range(1, len(bars) + 1):
            observed = bars[:end]
            raw = (
                strategy.on_bar(observed)
                if hasattr(strategy, "on_bar")
                else strategy(observed)
            )
            signals.append(max(0.0, min(1.0, float(raw))))
        cash, quantity = initial_capital, 0.0
        entry_time = None
        entry_price = invested = entry_fee = 0.0
        trades: list[CompletedTrade] = []
        for i in range(1, len(bars)):
            bar, signal = bars[i], signals[i - 1]
            if quantity == 0 and signal >= self.policy.minimum_confidence:
                risk_budget = cash * self.policy.risk_per_trade * signal
                notional = min(
                    cash,
                    cash * self.policy.maximum_position_fraction,
                    risk_budget / self.policy.stop_loss_pct,
                )
                fill = bar.open * (1 + self.costs.slippage_bps / 10_000)
                entry_fee = notional * self.costs.commission_bps / 10_000
                quantity = max(0.0, (notional - entry_fee) / fill)
                cash -= notional
                entry_time, entry_price, invested = bar.timestamp, fill, notional
            if quantity == 0:
                continue
            stop = entry_price * (1 - self.policy.stop_loss_pct)
            take = entry_price * (1 + self.policy.take_profit_pct)
            reason, raw_exit = None, None
            if bar.low <= stop:
                reason, raw_exit = "STOP_LOSS", stop
            elif bar.high >= take:
                reason, raw_exit = "TAKE_PROFIT", take
            elif signal < self.policy.minimum_confidence:
                reason, raw_exit = "SIGNAL_EXIT", bar.open
            elif i == len(bars) - 1:
                reason, raw_exit = "MARK_TO_MARKET", bar.close
            if reason:
                fill = raw_exit * (1 - self.costs.slippage_bps / 10_000)
                proceeds = quantity * fill
                exit_fee = proceeds * self.costs.commission_bps / 10_000
                cash += proceeds - exit_fee
                pnl = proceeds - exit_fee - invested
                trades.append(
                    CompletedTrade(
                        len(trades) + 1,
                        symbol,
                        entry_time,
                        bar.timestamp,
                        entry_price,
                        fill,
                        invested,
                        (bar.timestamp - entry_time).total_seconds(),
                        pnl,
                        pnl / invested if invested else 0.0,
                        reason,
                    )
                )
                quantity, entry_time = 0.0, None
        wins = sum(t.pnl > 0 for t in trades)
        losses = sum(t.pnl <= 0 for t in trades)
        return AssetEvaluation(
            symbol,
            initial_capital,
            cash,
            cash / initial_capital - 1,
            cash > 0,
            wins,
            losses,
            wins / len(trades) if trades else 0.0,
            trades,
        )
