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
    # A position must be worth taking. Once the drawdown de-leverage throttles
    # the risk budget, notional collapses toward the exchange floor and the run
    # grinds out thousands of ten-dollar trades that are pure noise: a quarter
    # of one strategy's ledger closed for less than fifty cents. Below this
    # fraction of equity the laboratory simply does not open. It only ever
    # reduces risk-taking, never increases it.
    minimum_position_fraction: float = 0.0025
    maximum_drawdown: float = 0.25
    # Retained for backwards-compatible stored policies. The binding abort is
    # always maximum_drawdown itself; a hidden lower threshold is misleading.
    drawdown_safety_buffer: float = 0.0
    volatility_target: float = 0.025
    volatility_lookback: int = 20
    # Capacity and drawdown controls. The zero/one defaults preserve existing
    # library callers; production thresholds are supplied by configuration.
    minimum_daily_quote_volume: float = 0.0
    volume_lookback: int = 20
    maximum_volume_participation: float = 1.0
    drawdown_deleverage_start: float = 0.10
    # How far price is assumed to move against a position when sizing it --
    # the denominator of `risk_budget / distance`. This used to BE
    # `stop_loss_pct`, which made the exit distance and the position size one
    # inseparable decision: widening the stop from 5% to 20% moved the exit
    # AND cut notional to a quarter, so neither effect could be attributed and
    # "wide stop, full size" could not be expressed at all. QUANT13 measured
    # the two separately at matched exposure and found the exit distance worth
    # +26.7 points on its own, which is the reason they are now separate.
    #
    # `None` means "use stop_loss_pct", so every policy already stored in the
    # database keeps its exact previous behaviour.
    risk_distance_pct: float | None = None

    @property
    def sizing_distance(self) -> float:
        """The distance used to size a position, independent of the exit."""
        distance = (
            self.stop_loss_pct
            if self.risk_distance_pct is None
            else self.risk_distance_pct
        )
        if not 0 < distance < 1:
            raise ValueError("risk_distance_pct must be in (0, 1)")
        return distance

    @property
    def exposure_calibration(self) -> dict[str, Any]:
        """What this policy assumes about the scope it is applied to.

        A policy is only meaningful relative to a bar interval and an asset
        count. `maximum_position_fraction` of 0.2 across 386 daily assets is a
        fully-invested portfolio; the same number on one hourly asset caps the
        run at 20% of capital and silently divides every published return by
        five. Recording the assumption lets a run flag the mismatch instead of
        producing an uninterpretable number.
        """
        return {
            "assets_for_full_investment": (
                math.ceil(1.0 / self.maximum_position_fraction)
                if self.maximum_position_fraction > 0
                else None
            ),
            "maximum_concurrent_assets": self.maximum_concurrent_assets,
            "sizing_distance": self.sizing_distance,
        }


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
    # A return number cannot be read without these. This laboratory published
    # eight months of results that turned out to have been generated at 5-9%
    # average exposure, which divides every return by roughly ten against a
    # fully-invested comparison and made "+3.46%" and "+350%" equally
    # uninterpretable. Nobody could see it because it was never recorded --
    # it took a bespoke diagnostic to discover. These are therefore first-class
    # outputs of every run, not analysis performed afterwards on some of them.
    average_exposure: float = 0.0
    peak_exposure: float = 0.0
    time_in_market: float = 0.0


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
        if (
            not 0 < policy.risk_per_trade <= 1
            or not 0 < policy.stop_loss_pct < 1
            or not 0 < policy.sizing_distance < 1
        ):
            raise ValueError("invalid risk policy")
        if not 0 < policy.maximum_volume_participation <= 1:
            raise ValueError("maximum_volume_participation must be in (0, 1]")
        self.costs, self.policy = costs, policy

    def run(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        strategy_factory: Callable[[], Any],
        initial_capital: float,
        progress: Callable[[dict[str, Any]], None] | None = None,
        trading_start: datetime | None = None,
        preparation_progress: Callable[[dict[str, Any]], None] | None = None,
        pace_seconds: float = 0.0,
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
        dollar_liquidity: dict[str, dict[datetime, float]] = {}
        for symbol_index, (symbol, bars) in enumerate(prepared.items(), 1):
            strategy = strategy_factory()
            if hasattr(strategy, "reset"):
                strategy.reset()
            series: dict[datetime, float] = {}
            vol_series: dict[datetime, float] = {}
            liquidity_series: dict[datetime, float] = {}
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
                # Sizing at this bar happens at its OPEN, so the volatility that
                # scales it may only use bars that closed before it. Including
                # this bar's own close let the engine shrink exposure on days it
                # had not lived through yet — a systematic flattery, since the
                # days it de-risked were exactly the ones that turned out badly.
                # The signal is lagged where it is consumed and the liquidity
                # window below already stops at end-1; this now matches both.
                start = max(1, end - 1 - self.policy.volatility_lookback)
                returns = [
                    math.log(bars[i].close / bars[i - 1].close)
                    for i in range(start, end - 1)
                ]
                if len(returns) >= 2:
                    mean = sum(returns) / len(returns)
                    vol_series[bar.timestamp] = math.sqrt(
                        sum((value - mean) ** 2 for value in returns)
                        / (len(returns) - 1)
                    )
                else:
                    vol_series[bar.timestamp] = self.policy.volatility_target
                volume_start = max(0, end - 1 - self.policy.volume_lookback)
                prior_volumes = [
                    item.close * item.volume for item in bars[volume_start : end - 1]
                ]
                liquidity_series[bar.timestamp] = (
                    sum(prior_volumes) / len(prior_volumes) if prior_volumes else 0.0
                )
            signals[symbol] = series
            volatilities[symbol] = vol_series
            dollar_liquidity[symbol] = liquidity_series
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
        last_liquidity = {}
        first_trade_stamp = timeline[0]
        for symbol in prepared:
            warmup = [stamp for stamp in signals[symbol] if stamp < first_trade_stamp]
            last_signal[symbol] = signals[symbol][max(warmup)] if warmup else 0.0
            last_liquidity[symbol] = (
                dollar_liquidity[symbol][max(warmup)] if warmup else 0.0
            )
        deployed = {symbol: 0.0 for symbol in prepared}
        peak_risk = {symbol: 0.0 for symbol in prepared}
        equity_curve: list[dict[str, Any]] = []
        progress_trade_cursor = 0
        started_at = time.monotonic()

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
                    close(symbol, bar, min(stop, bar.open), "STOP_LOSS")
                elif bar.high >= take:
                    close(symbol, bar, max(take, bar.open), "TAKE_PROFIT")
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
                available_liquidity = last_liquidity[symbol]
                if available_liquidity < self.policy.minimum_daily_quote_volume:
                    continue
                capacity_limit = (
                    available_liquidity * self.policy.maximum_volume_participation
                    if self.policy.minimum_daily_quote_volume > 0
                    else float("inf")
                )
                current_drawdown = 1 - equity / peak_equity if peak_equity else 0.0
                trigger = self.policy.maximum_drawdown
                if current_drawdown <= self.policy.drawdown_deleverage_start:
                    deleverage_scale = 1.0
                else:
                    remaining = max(0.0, trigger - current_drawdown)
                    span = max(1e-9, trigger - self.policy.drawdown_deleverage_start)
                    deleverage_scale = remaining / span
                risk_budget = (
                    equity
                    * self.policy.risk_per_trade
                    * confidence
                    * volatility_scale
                    * deleverage_scale
                )
                notional = min(
                    cash,
                    equity * self.policy.maximum_position_fraction,
                    risk_budget / self.policy.sizing_distance,
                    capacity_limit,
                )
                floor = max(
                    self.policy.minimum_order_notional,
                    equity * self.policy.minimum_position_fraction,
                )
                if notional < floor:
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
                last_liquidity[symbol] = dollar_liquidity[symbol][stamp]
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
            drawdown_trigger = self.policy.maximum_drawdown
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
                aborted, abort_reason = True, "MAX_DRAWDOWN_ABORT"
            point = {
                "timestamp": stamp.isoformat(),
                "equity": marked,
                "cash": cash,
                "open_positions": len(positions),
                "processed_days": day_index + 1,
                "total_days": len(timeline),
                "trades": len(trades),
                # Distinct assets touched so far, counting positions still open.
                # Closed trades alone read as zero for the early part of every
                # run — which is why the monitor showed "0 traded" against an
                # equity curve that was visibly trading.
                "assets_traded": len(
                    {trade.symbol for trade in trades} | set(positions)
                ),
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
                # Stretch the run to `pace_seconds` so the public monitor can show
                # the simulation advancing instead of a result that appears fully
                # formed. Sleeping between emissions cannot change any number the
                # engine produces, only when it is observed.
                if pace_seconds > 0 and day_index < len(timeline) - 1:
                    target = pace_seconds * (day_index + 1) / len(timeline)
                    behind = target - (time.monotonic() - started_at)
                    if behind > 0:
                        time.sleep(min(behind, 2.0))
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
        # Exposure is measured from the equity curve the run already emits, so
        # it costs one pass and cannot drift from the equity it describes.
        exposures = [
            1 - float(point["cash"]) / float(point["equity"])
            for point in equity_curve
            if float(point.get("equity") or 0) > 0
        ]
        invested_bars = [value for value in exposures if value > 1e-6]
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
            sum(exposures) / len(exposures) if exposures else 0.0,
            max(exposures) if exposures else 0.0,
            len(invested_bars) / len(exposures) if exposures else 0.0,
        )


class LongOnlyExecutionBacktester:
    """Signal-independent execution, risk sizing and protective-exit simulator."""

    def __init__(self, costs: CostModel, policy: MoneyManagement):
        if not policy.long_only:
            raise ValueError("this laboratory only permits long-only policies")
        if (
            not 0 < policy.risk_per_trade <= 1
            or not 0 < policy.stop_loss_pct < 1
            or not 0 < policy.sizing_distance < 1
        ):
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
                    risk_budget / self.policy.sizing_distance,
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
                reason, raw_exit = "STOP_LOSS", min(stop, bar.open)
            elif bar.high >= take:
                reason, raw_exit = "TAKE_PROFIT", max(take, bar.open)
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
