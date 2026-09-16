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

from . import execution as X

from dataclasses import dataclass, field
from datetime import datetime, timezone

# House costs, per side, from the operator's constraint. A round trip is 0.30%.
#
# THIS FLAT RATE IS THE FALLBACK, NOT THE MODEL. It applies only when the caller supplies no
# liquidity data, and it is deliberately PESSIMISTIC relative to the realistic model - a
# published Binance taker fee is 5 bps, not 10. Keeping it means a run without turnover data
# still cannot pretend trading is cheap; see `execution.py` for what is charged when the
# book knows how big the order is and how deep the name is.
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



def _trade_cost(traded: dict[str, float], equity: float, day: str,
                returns: dict[str, dict[str, float]],
                turnover: dict[str, dict[str, float]] | None,
                factor_symbol: str, realistic: bool) -> float:
    """What a set of weight changes costs in dollars, by whichever model is in force.

    `traded` is per-symbol change in ABSOLUTE weight, so multiplying by equity gives the
    notional actually sent to the market in each name - which is the quantity the realistic
    model needs and the flat rate never asked for.

    The stress factor is taken from the FACTOR's move on the day. It is a market-wide
    condition rather than a per-name one: on a liquidation cascade every book widens
    together, and using each name's own move would let a coin that happened to be flat
    pretend the day was calm.
    """
    gross = sum(abs(v) for v in traded.values())
    if not realistic or not turnover:
        return gross * COST_PER_SIDE * equity

    # EVERYTHING PRICED HERE IS KNOWN BEFORE THE TRADE, and the first version of this
    # function was not. It read the CURRENT day's return, the current day's factor move and
    # the current day's volume to price a trade placed at the start of that day - three
    # separate look-aheads, found while writing the audit brief that described them.
    #
    # The direction of the error was not even favourable in the obvious way: same-day
    # volatility RAISES the charge on violent days, so it flattered nothing about cost. It
    # was worse than that - it let the book price its trades with knowledge of how the day
    # turned out, which is the same class of error as sizing them that way. A cost model
    # that peeks is a cost model whose number cannot be defended, whichever way it leans.
    market_move = _prev(returns.get(factor_symbol, {}), day)
    total = 0.0
    for sym, dw in traded.items():
        notional = abs(dw) * equity
        if notional <= 0:
            continue
        # Liquidity as it was last seen, not as it turns out to be. A name that is about to
        # print a huge volume day is not liquid at the moment the order is placed.
        dv = _prev(turnover.get(sym) or {}, day)
        own = abs(_prev(returns.get(sym, {}), day))
        fill = X.cost_bps(notional, dv, own, market_move=market_move)
        total += notional * fill.bps / 10_000.0
    return total


def _prev(series: dict[str, float], day: str) -> float:
    """The most recent value STRICTLY BEFORE `day`, or 0.0 if there is none.

    Kept as its own named function because every use of it is a causality boundary, and a
    boundary that is inlined three times is a boundary that gets edited back out twice.
    """
    best_day, best = None, 0.0
    for d, v in series.items():
        if d < day and (best_day is None or d > best_day):
            best_day, best = d, v
    return float(best or 0.0)


def run_book(days: list[str],
             returns: dict[str, dict[str, float]],
             targets_on: dict[str, list],
             hedge_on: dict[str, float],
             factor_symbol: str,
             funding: dict[str, dict[str, float]] | None = None,
             initial_equity: float = 100_000.0,
             gross_cap: float = 1.0,
             cap_band: float = DEFAULT_CAP_BAND,
             turnover: dict[str, dict[str, float]] | None = None,
             realistic_costs: bool = False) -> BookResult:
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

    for day in days:
        rebalanced = False
        cost = 0.0

        # ---- rebalance happens at the START of the day, on yesterday's information,
        # and is paid for before the day's returns are earned.
        if day in targets_on:
            target = {t.symbol: t.weight for t in targets_on[day]}
            target_hedge = hedge_on.get(day, 0.0)

            # Straight to the target. Partial adjustment was implemented and measured
            # (Garleanu-Pedersen): cost fell almost exactly proportionally and return fell
            # FASTER, so the cost is the price of the signal rather than waste. Removed
            # rather than left switched off, because a knob nobody should turn is still a
            # knob every future result has to be corrected for.
            new = {s: w for s, w in target.items() if abs(w) > 1e-9}
            new_hedge = target_hedge


            traded = {s: abs(new.get(s, 0.0) - weights.get(s, 0.0))
                      for s in set(new) | set(weights)}
            traded[factor_symbol] = traded.get(factor_symbol, 0.0) + abs(new_hedge - hedge)
            cost = _trade_cost(traded, equity, day, returns, turnover,
                               factor_symbol, realistic_costs)
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
                trimmed = {s: abs(w) * (1.0 - scale) for s, w in weights.items()}
                trimmed[factor_symbol] = (trimmed.get(factor_symbol, 0.0)
                                          + abs(hedge) * (1.0 - scale))
                cost += _trade_cost(trimmed, equity, day, returns, turnover,
                                    factor_symbol, realistic_costs)
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

        gross = sum(abs(w) for w in weights.values()) + abs(hedge)
        net = sum(weights.values()) + hedge
        res.days.append(DayRecord(
            day, equity, gross, net,
            asset_pnl * equity, hedge_pnl * equity, funding_pnl * equity, cost,
            sum(1 for w in weights.values() if w > 0),
            sum(1 for w in weights.values() if w < 0),
            rebalanced))
    return res
