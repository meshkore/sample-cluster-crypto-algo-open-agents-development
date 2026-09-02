from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any

from .models import BacktestResult, Bar, Trade


@dataclass(frozen=True)
class CostModel:
    """What trading costs, per fill.

    `slippage_bps` is the FIXED half-spread every order pays regardless of size.
    `impact_bps` is the size-dependent part: our own order pushes the price, and a
    flat slippage silently claims it does not. The extra cost charged on a fill is

        impact_bps * sqrt(participation),   participation = notional / bar traded value

    - the square-root law, which is what the empirical market-microstructure
    literature keeps finding and what every execution desk sizes against. So
    `impact_bps` reads as "the bps we would pay if a single order were the whole
    bar's volume"; at 1% of the bar it charges a tenth of that, at 0.01% a hundredth.

    Concretely, why this exists (system 06 audit, 2026-09-02): a compounded account
    was buying $45M of NEARUSDT inside one 15-minute candle and paying the same 5 bps
    a $100 order pays. That is not a rounding error, it is a different market. Default
    0.0 keeps every historical result reproducible; each system turns it on
    deliberately.
    """

    commission_bps: float
    slippage_bps: float
    funding_bps_per_bar: float = 0.0
    impact_bps: float = 0.0

    def slippage_for(self, notional: float, traded_value: float) -> float:
        """Total slippage in bps for an order of `notional` into a bar that traded
        `traded_value`. Falls back to the fixed part when volume is unknown - a feed
        without volume must not silently price impact as zero OR as infinite."""
        if self.impact_bps <= 0 or traded_value <= 0 or notional <= 0:
            return self.slippage_bps
        participation = min(1.0, notional / traded_value)
        return self.slippage_bps + self.impact_bps * math.sqrt(participation)


class Backtester:
    def __init__(
        self, initial_equity: float, costs: CostModel, max_position: float = 1.0
    ):
        if initial_equity <= 0 or not 0 < max_position <= 1:
            raise ValueError("invalid capital or position limit")
        self.initial_equity, self.costs, self.max_position = (
            initial_equity,
            costs,
            max_position,
        )

    def run(self, bars: list[Bar], strategy: Any) -> BacktestResult:
        if len(bars) < 3:
            raise ValueError("at least three bars required")
        # Enforce causality at the engine boundary. Strategy code never receives
        # bars later than the decision it is currently producing.
        if hasattr(strategy, "reset"):
            strategy.reset()
        targets: list[float] = []
        for end in range(1, len(bars) + 1):
            observed = bars[:end]
            target = (
                strategy.on_bar(observed)
                if hasattr(strategy, "on_bar")
                else strategy(observed)
            )
            targets.append(float(target))
        equity = gross_equity = self.initial_equity
        position = 0.0
        trades: list[Trade] = []
        equity_curve = [(bars[0].timestamp, equity)]
        bar_returns: list[float] = []
        total_commission = total_slippage = total_funding = turnover = exposure = 0.0
        gross_gains = gross_losses = 0.0
        for i in range(1, len(bars)):
            desired = max(
                -self.max_position, min(self.max_position, float(targets[i - 1]))
            )
            change = desired - position
            pre_cost_equity = equity
            if abs(change) > 1e-12:
                traded_notional = abs(change) * equity
                commission = traded_notional * self.costs.commission_bps / 10_000
                slippage = traded_notional * self.costs.slippage_bps / 10_000
                equity -= commission + slippage
                total_commission += commission
                total_slippage += slippage
                turnover += abs(change)
                trades.append(
                    Trade(
                        bars[i].timestamp,
                        position,
                        desired,
                        bars[i].open,
                        abs(change),
                        commission,
                        slippage,
                    )
                )
                position = desired
            move = bars[i].close / bars[i].open - 1.0
            pnl = equity * position * move
            gross_pnl = gross_equity * position * move
            funding_rate = (
                bars[i].funding_rate
                if bars[i].funding_rate is not None
                else self.costs.funding_bps_per_bar / 10_000
            )
            funding = equity * abs(position) * funding_rate
            equity += pnl - funding
            gross_equity += gross_pnl
            total_funding += funding
            period_return = equity / pre_cost_equity - 1 if pre_cost_equity else 0.0
            bar_returns.append(period_return)
            if pnl >= 0:
                gross_gains += pnl
            else:
                gross_losses -= pnl
            exposure += abs(position)
            equity_curve.append((bars[i].timestamp, equity))
        peak, max_drawdown = equity_curve[0][1], 0.0
        for _, value in equity_curve:
            peak = max(peak, value)
            max_drawdown = max(max_drawdown, 1 - value / peak)
        avg = mean(bar_returns) if bar_returns else 0.0
        volatility = pstdev(bar_returns) if len(bar_returns) > 1 else 0.0
        downside = [r for r in bar_returns if r < 0]
        downside_dev = math.sqrt(mean([r * r for r in downside])) if downside else 0.0
        annualizer = math.sqrt(365)
        return BacktestResult(
            self.initial_equity,
            equity,
            gross_equity / self.initial_equity - 1,
            equity / self.initial_equity - 1,
            max_drawdown,
            avg / volatility * annualizer if volatility else 0.0,
            avg / downside_dev * annualizer if downside_dev else 0.0,
            gross_gains / gross_losses
            if gross_losses
            else (None if gross_gains else 0.0),
            turnover,
            exposure / max(1, len(bars) - 1),
            trades,
            equity_curve,
            bar_returns,
            total_commission,
            total_slippage,
            total_funding,
        )
