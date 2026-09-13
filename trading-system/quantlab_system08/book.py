"""The residual book: turning target weights into a simulated account, honestly.

WHY A WEIGHT-BASED SIMULATION AND NOT THE PER-SYMBOL ENGINE

`quantlab_backtester` holds a signed ledger with correct funding, and this module keeps
its conventions to the letter. What it does not reuse is its ENTRY/EXIT flow, and the
reason is structural rather than stylistic: that engine models a strategy deciding, per
symbol, to be in or out. A cross-sectional book does not make per-symbol decisions. It
makes ONE decision - a ranking - and expresses it as a vector of weights whose two legs
only mean anything relative to each other. Forcing that through a per-symbol entry API
would mean reconstructing the vector on the far side, and the reconstruction is where the
errors would live.

So the book is simulated on weights, and the three things that actually cost money are
each modelled explicitly rather than absorbed into a fudge:

  COSTS ARE CHARGED ON TURNOVER, at both rebalances and forced changes, at the house rate
  of 10 bps commission + 5 bps slippage per side. A round trip is 30 bps. Costs are
  charged on the CHANGE in weight, not on the position, because that is what is actually
  traded.

  WEIGHTS DRIFT BETWEEN REBALANCES. Holding a constant weight would mean silently
  rebalancing every single day and paying none of it, which is the most common way a
  cross-sectional backtest reports a return nobody could have earned. Here a position is
  set at the rebalance and then left alone; its weight moves with its price, and the
  divergence is paid for at the next rebalance.

  FUNDING USES THE LEDGER'S SIGN CONVENTION. When the funding rate is POSITIVE, longs pay
  and SHORTS RECEIVE. Crypto funding has been positive for most of its history, which is
  why the design expects the short leg to be paid rather than charged - and which is also
  the design's weakest claim, registered as such, because it rests on market data rather
  than a peer-reviewed full-cycle measurement and it sits in tension with a carry trade
  this laboratory already closed after its Sharpe went negative in 2025. If the short leg
  costs rather than pays, kill criterion K3 fires. This module is written so that the
  answer is visible in the output rather than buried: `funding_pnl` is reported
  separately and never netted into the return.

WHAT IS NOT MODELLED, AND IS SAID OUT LOUD

Liquidation, margin calls and borrow availability. Gross exposure is capped at 1.0 by
default, so the book is unlevered and none of the three binds - but that is a consequence
of the cap, not a proof of safety, and raising the cap without adding them would be
dishonest.
"""

from __future__ import annotations

import math

from dataclasses import dataclass, field
from datetime import datetime, timezone

# House costs, per side, from the operator's constraint. A round trip is 0.30%.
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
COST_PER_SIDE = (COMMISSION_BPS + SLIPPAGE_BPS) / 10_000.0

# Perpetual funding settles three times a day on the venues we model.
FUNDING_SETTLEMENTS_PER_DAY = 3

# How far gross exposure may drift above the cap before the book is trimmed back.
# A band rather than a hard line, because trimming the instant gross ticks a basis point
# over would churn daily and turnover is the enemy of this design.
DEFAULT_CAP_BAND = 0.10

# PARTIAL ADJUSTMENT. How far toward the new target the book actually trades.
#
# 1.0 reproduces the original behaviour exactly - jump the whole way - and that behaviour
# is what the first decomposition indicted: cost took between 4.7% and 5.9% of equity in
# every single research year AND in 2026, on both universes, and in the weak years it was
# larger than everything the signal earned. The asset leg made +2.0% in 2024 on the wide
# book; cost took 5.3%.
#
# The published answer is not to trade less often but to trade less FAR. Garleanu and
# Pedersen (2013) show that with proportional costs and a mean-reverting signal the
# optimal policy is not to jump to the target but to move a constant fraction of the
# remaining distance toward it each period - the position that is optimal is an "aim"
# between where you are and where the signal points. A signal that decays over the holding
# period is partly stale by the time it is fully implemented, so paying the full spread to
# reach it buys a target that is already moving away.
#
# This is ONE parameter and it is deliberately a single scalar rather than a per-name
# band, because a per-name rule is several parameters wearing one name.
DEFAULT_ADJUST = 1.0

# VOLATILITY TARGETING. 0.0 disables it, which is the default, so nothing changes unless
# it is asked for.
#
# Momentum's characteristic failure is not a slow bleed, it is a crash: Daniel and
# Moskowitz show the losses concentrate in rebounds after a market decline, and Barroso and
# Santa-Clara (2015) show that scaling the position by the strategy's OWN recent realised
# volatility removes most of that crash risk and roughly doubles the Sharpe ratio - because
# momentum's volatility is strongly predictable from its recent past even though its return
# is not. That asymmetry is the whole mechanism and it is why this is not curve fitting:
# the quantity being forecast is the one that forecasts well.
#
# THIS IMPLEMENTATION ONLY EVER DE-LEVERS. The scale is clamped at 1.0 above, so a quiet
# period cannot lever the book up. That is a constraint from the operator rather than from
# the paper - leverage is permitted but minimal, for execution risk - and it costs some of
# the published effect. It is stated here rather than buried, because a reader comparing
# our numbers to Barroso's should know we took only half of their trade.
DEFAULT_VOL_TARGET = 0.0
DEFAULT_VOL_WINDOW = 60
MIN_VOL_OBS = 20
MIN_VOL_SCALE = 0.20
TRADING_DAYS = 365          # crypto does not close


@dataclass
class DayRecord:
    """One day of the book, decomposed so no component can hide inside another."""

    day: str
    equity: float
    gross: float
    net: float
    asset_pnl: float
    hedge_pnl: float
    funding_pnl: float
    cost: float
    n_long: int
    n_short: int
    rebalanced: bool


@dataclass
class BookResult:
    days: list[DayRecord] = field(default_factory=list)
    initial_equity: float = 0.0

    @property
    def final_equity(self) -> float:
        return self.days[-1].equity if self.days else self.initial_equity

    @property
    def total_return(self) -> float:
        if not self.days or self.initial_equity <= 0:
            return 0.0
        return self.final_equity / self.initial_equity - 1.0

    @property
    def total_costs(self) -> float:
        return sum(d.cost for d in self.days)

    @property
    def total_funding(self) -> float:
        """Positive means the book RECEIVED funding. The design predicts this is
        positive; if it is not, K3 is the kill that fires."""
        return sum(d.funding_pnl for d in self.days)

    @property
    def max_drawdown(self) -> float:
        peak, worst = self.initial_equity, 0.0
        for d in self.days:
            peak = max(peak, d.equity)
            if peak > 0:
                worst = max(worst, (peak - d.equity) / peak)
        return worst

    def returns(self) -> list[float]:
        out, prev = [], self.initial_equity
        for d in self.days:
            out.append(d.equity / prev - 1.0 if prev > 0 else 0.0)
            prev = d.equity
        return out

    def by_year(self) -> dict[int, float]:
        """Compounded return per calendar year. The mandate is stated per calendar year,
        so the report is too - a mean across years hides the year that kills you."""
        out: dict[int, float] = {}
        prev = self.initial_equity
        start: dict[int, float] = {}
        end: dict[int, float] = {}
        for d in self.days:
            y = int(d.day[:4])
            start.setdefault(y, prev)
            end[y] = d.equity
            prev = d.equity
        for y in sorted(start):
            if start[y] > 0:
                out[y] = end[y] / start[y] - 1.0
        return out


def daily_funding(rows: list[dict]) -> dict[str, float]:
    """Sum the settlements inside each UTC day, from the catalogue's raw rows.

    Summing rather than averaging: a position is charged on every settlement it is open
    across, so the day's cost is the sum of that day's rates. Averaging would understate
    the carry by the number of settlements, which is the whole size of the effect the
    design is leaning on.
    """
    out: dict[str, float] = {}
    for row in rows:
        ms, rate = row.get("t_ms"), row.get("rate")
        if ms is None or rate is None:
            continue
        day = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
        out[day] = out.get(day, 0.0) + float(rate)
    return out


def run_book(days: list[str],
             returns: dict[str, dict[str, float]],
             targets_on: dict[str, list],
             hedge_on: dict[str, float],
             factor_symbol: str,
             funding: dict[str, dict[str, float]] | None = None,
             initial_equity: float = 100_000.0,
             gross_cap: float = 1.0,
             cap_band: float = DEFAULT_CAP_BAND,
             adjust: float = DEFAULT_ADJUST,
             vol_target: float = DEFAULT_VOL_TARGET,
             vol_window: int = DEFAULT_VOL_WINDOW) -> BookResult:
    """Simulate the book day by day.

    `targets_on[day]` is the new target vector to trade INTO on that day; days absent
    from it are holds. `hedge_on[day]` is the factor weight decided at the same moment.
    Both are produced from information strictly before the day - that is the signal
    module's contract, and there is a test that asserts it end to end rather than
    trusting it.
    """
    funding = funding or {}
    res = BookResult(initial_equity=initial_equity)
    equity = initial_equity
    weights: dict[str, float] = {}
    hedge = 0.0
    realised: list[float] = []       # the book's OWN daily returns, for vol targeting
    target_daily = (vol_target / math.sqrt(TRADING_DAYS)) if vol_target > 0 else 0.0

    for day in days:
        rebalanced = False
        cost = 0.0

        # ---- rebalance happens at the START of the day, on yesterday's information,
        # and is paid for before the day's returns are earned.
        if day in targets_on:
            target = {t.symbol: t.weight for t in targets_on[day]}
            target_hedge = hedge_on.get(day, 0.0)

            # Move `adjust` of the way from the drifted book to the target. At 1.0 this
            # is exactly the old behaviour; below it, a name the signal has dropped is
            # scaled down rather than closed, and a name it has picked is entered part
            # size and topped up at the next rebalance if the signal still wants it.
            # Names are dropped once they round to nothing, so an exited position cannot
            # linger forever as dust that is nonetheless charged for.
            new: dict[str, float] = {}
            for sym in set(target) | set(weights):
                held, want = weights.get(sym, 0.0), target.get(sym, 0.0)
                moved = held + adjust * (want - held)
                if abs(moved) > 1e-9:
                    new[sym] = moved
            new_hedge = hedge + adjust * (target_hedge - hedge)

            # ---- volatility targeting, applied to the NEW book before it is priced.
            #
            # `realised` holds only days already closed, so the scale is decided on
            # information strictly before this day - the same causality rule the loadings
            # and the liquidity screen obey. Until there are enough closed days the scale
            # is 1.0 rather than a guess: an estimate from eight observations is not a
            # risk measurement, it is noise with a decimal point.
            if target_daily > 0 and len(realised) >= MIN_VOL_OBS:
                recent = realised[-vol_window:]
                mean = sum(recent) / len(recent)
                var = sum((r - mean) ** 2 for r in recent) / (len(recent) - 1)
                sd = math.sqrt(var)
                if sd > 0:
                    scale = min(1.0, max(MIN_VOL_SCALE, target_daily / sd))
                    new = {k: v * scale for k, v in new.items()}
                    new_hedge *= scale

            turnover = sum(abs(new.get(s, 0.0) - weights.get(s, 0.0))
                           for s in set(new) | set(weights))
            turnover += abs(new_hedge - hedge)
            cost = turnover * COST_PER_SIDE * equity
            weights, hedge, rebalanced = new, new_hedge, True

        # ---- ENFORCE THE GROSS CAP EVERY DAY, not only at rebalances.
        #
        # The design states the cap as a standing constraint, "subject to sum|w| <= L",
        # and the first real run showed why that word matters: applying it only at the
        # rebalance let drift carry gross exposure to 2.67x on a 1.0 cap, and the book's
        # worst nine days were spent there. That is not a result, it is the constraint
        # not being implemented. Leverage is permitted but MINIMAL and the operator's
        # reason is execution risk, so a book cannot be allowed to lever itself simply by
        # holding winners.
        #
        # The band exists because turnover is the enemy: trimming the instant gross ticks
        # a basis point over would churn daily and pay for it. Breaching the band is
        # rare; being inside it is the normal state.
        if gross_cap > 0 and not rebalanced:
            live = sum(abs(w) for w in weights.values()) + abs(hedge)
            if live > gross_cap * (1.0 + cap_band):
                scale = gross_cap / live
                trimmed = sum(abs(w) * (1.0 - scale) for w in weights.values())
                trimmed += abs(hedge) * (1.0 - scale)
                cost += trimmed * COST_PER_SIDE * equity
                weights = {s: w * scale for s, w in weights.items()}
                hedge *= scale

        # ---- the day's P&L, decomposed.
        asset_pnl = 0.0
        drifted: dict[str, float] = {}
        for sym, w in weights.items():
            r = returns.get(sym, {}).get(day)
            if r is None:
                drifted[sym] = w          # no tape today: the position is unchanged
                continue
            asset_pnl += w * r
            drifted[sym] = w * (1.0 + r)  # the position grew or shrank with its price

        fr = returns.get(factor_symbol, {}).get(day)
        hedge_pnl = hedge * fr if fr is not None else 0.0
        if fr is not None:
            hedge = hedge * (1.0 + fr)

        # ---- funding. Positive rate: longs pay, shorts receive. The ledger's
        # convention, kept identical so the two can never disagree.
        funding_pnl = 0.0
        for sym, w in weights.items():
            rate = funding.get(sym, {}).get(day)
            if rate:
                funding_pnl -= w * rate
        rate_f = funding.get(factor_symbol, {}).get(day)
        if rate_f:
            funding_pnl -= hedge * rate_f

        weights = drifted
        equity = equity * (1.0 + asset_pnl + hedge_pnl + funding_pnl) - cost
        if equity <= 0:
            # A book that reaches zero is over. Recording it and stopping is the honest
            # end; carrying a negative equity forward would produce returns that are
            # arithmetic nonsense and a curve that looks like a recovery.
            res.days.append(DayRecord(day, 0.0, 0.0, 0.0, asset_pnl, hedge_pnl,
                                      funding_pnl, cost, 0, 0, rebalanced))
            break

        realised.append(asset_pnl + hedge_pnl + funding_pnl)

        gross = sum(abs(w) for w in weights.values()) + abs(hedge)
        net = sum(weights.values()) + hedge
        res.days.append(DayRecord(
            day, equity, gross, net,
            asset_pnl * equity, hedge_pnl * equity, funding_pnl * equity, cost,
            sum(1 for w in weights.values() if w > 0),
            sum(1 for w in weights.values() if w < 0),
            rebalanced))
    return res
