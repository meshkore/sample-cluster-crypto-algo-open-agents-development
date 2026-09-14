"""L1 - the inverse problem: observables in, a cohort state trajectory out.

WHAT IS EXACT AND WHAT IS MODELLED, because the difference is the whole credibility of the
output and it is easy to blur.

  EXACT, straight from the tape, no model at all:
    - `volume` coins changed hands, so somebody bought exactly that many and somebody sold
      exactly that many;
    - `taker_buy` of them were bought by the AGGRESSOR, which means the same quantity was
      sold passively, and `taker_sell` were sold aggressively and bought passively.
    That is four pool sizes per bucket, and they are observations rather than assumptions.

  MODELLED, and this is the only place the model lives:
    - WHICH cohorts filled each of those four pools.

So the reconstruction never invents volume and never invents a direction. It answers one
question per bucket - who did it - and it answers it under constraints that make most of
the wrong answers impossible: an agent cannot buy with cash it does not have, cannot sell
coins it does not hold, and the four pools must be filled exactly.

THE ALLOCATION, in one paragraph. Each agent gets a weight per pool equal to its
behavioural desire (`cohorts.desires`) times its aggressiveness for that side times its
remaining capacity. Flow is shared out in proportion to weight, any agent that hits its
capacity is clamped, and the residual is re-shared among the rest until the pool is filled
or everybody is clamped. This is water-filling; it is the cheap, well-behaved first cut the
design named, and it has the property that matters most here - it degrades into a REPORTED
failure rather than a silent one.

WHY AGGRESSIVE FLOW GETS FIRST CLAIM ON CAPACITY. An agent's cash limits its buying across
both the aggressive and the passive pool, so the two compete. Aggressive flow is allocated
first because that is the flow the tape identifies as having demanded immediacy: an agent
that crossed the spread had already decided, while a resting bid is a preference. Passive
flow then fills from what capacity is left.

THE DIAGNOSTIC THAT MATTERS MORE THAN THE OUTPUT. `fill_ratio` is the fraction of observed
volume the reconstructed population was actually able to trade. A population whose cash and
coins are distributed roughly right fills essentially all of it. A fill ratio that collapses
means the state is wrong in a way no amount of extra layers will fix, and it is reported on
every run rather than discovered later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import cohorts as C
from .boundary import Boundary
from .buckets import Bucket
from .ledger import Agent, Ledger

#: Binance's published spot schedule, rounded to the tier most volume actually pays.
#: Fees are a transfer to the venue rather than a leak: the exchange is inside the ledger.
TAKER_FEE = 0.0004
MAKER_FEE = 0.0001

#: How much of the levered cohort's notional responds to the fast trend, as a fraction of
#: the coin float. A placeholder for the open-interest series this MVP does not download,
#: and the reason the perpetual book is reported as a mechanism rather than as a result.
PERP_SCALE = 0.02


@dataclass
class Trajectory:
    """What a run produces: daily cohort state, plus the diagnostics that judge it."""
    days: list[str] = field(default_factory=list)
    price: list[float] = field(default_factory=list)
    state: list[dict] = field(default_factory=list)      # day -> cohort -> stocks
    fill_ratio: list[float] = field(default_factory=list)
    buckets: int = 0
    shortfall_events: int = 0
    volume_observed: float = 0.0
    volume_realised: float = 0.0

    @property
    def overall_fill(self) -> float:
        return self.volume_realised / self.volume_observed if self.volume_observed else 0.0


def _waterfill(weights: dict[str, float], caps: dict[str, float], pool: float,
               rounds: int = 12) -> dict[str, float]:
    """Share `pool` out in proportion to `weights`, never exceeding `caps`.

    Returns what was actually allocated, which is less than `pool` only when every
    participant is at its cap. The caller is expected to notice that and say so.
    """
    out = {k: 0.0 for k in weights}
    remaining = pool
    live = {k for k, w in weights.items() if w > 0 and caps.get(k, 0.0) > 0}
    for _ in range(rounds):
        if remaining <= 1e-12 or not live:
            break
        total_w = sum(weights[k] for k in live)
        if total_w <= 0:
            break
        clamped = False
        for k in list(live):
            want = remaining * weights[k] / total_w
            room = caps[k] - out[k]
            if want >= room:
                out[k] += room
                live.discard(k)
                clamped = True
            else:
                out[k] += want
        if not clamped:
            break
        remaining = pool - sum(out.values())
    # One last proportional pass over whoever still has room, so an exactly-fillable pool
    # is exactly filled rather than left a rounding crumb short.
    remaining = pool - sum(out.values())
    if remaining > 1e-12:
        room = {k: caps[k] - out[k] for k in weights if caps.get(k, 0.0) - out[k] > 0}
        total_room = sum(room.values())
        if total_room > 0:
            take = min(remaining, total_room)
            for k, r in room.items():
                out[k] += take * r / total_room
    return out


class Reconstruction:
    """One pass over the tape, producing one cohort-state trajectory."""

    def __init__(self, bkts: list[Bucket], *, boundary: Boundary,
                 funding: list[dict] | None = None, check_every: bool = False) -> None:
        self.bkts = bkts
        self.boundary = boundary
        self.funding = funding or []
        first_day = bkts[0].day
        coins, cash = boundary.opening_totals(first_day)
        self.agents = C.build_population(coins, cash, bkts[0].vwap)
        self.ledger = Ledger(self.agents, check_every=check_every)
        self.by_cohort: dict[str, list[Agent]] = {}
        for a in self.agents:
            self.by_cohort.setdefault(a.cohort, []).append(a)
        self.mm_anchor = {a.name: a.coins for a in self.by_cohort[C.MAKER]}
        self.buy_budget: dict[str, float] = {}
        self.sell_budget: dict[str, float] = {}
        self._daily_close = _daily_closes(bkts)
        self._days = sorted(self._daily_close)
        self._peak = _rolling_peak(self._daily_close, self._days, 365)
        #: The market state as each day first saw it. Kept so that V2 can rebuild the
        #: UNCONSTRAINED desire a rule started from, using the rule itself rather than a
        #: copy of its formula living in the test.
        self.day_state: dict[str, C.MarketState] = {}
        self._fund_by_day = _funding_by_day(self.funding)

    # ------------------------------------------------------------------ market state
    def _state(self, b: Bucket) -> C.MarketState:
        """Causal by construction: every return is computed from days STRICTLY earlier.

        A rule that saw the close of the day it is trading inside would reproduce the tape
        beautifully and mean nothing.
        """
        d = b.day
        prev = _shift(d, -1)
        px = lambda k: self._daily_close.get(_shift(d, -k))          # noqa: E731
        base = px(1)
        r = lambda k: (base / px(k) - 1.0) if (base and px(k)) else 0.0   # noqa: E731
        peak = self._peak.get(d) or b.vwap
        return C.MarketState(
            price=b.vwap,
            r_fast=r(2), r_slow=r(31), r_glacial=r(91),
            drawdown=(base / peak - 1.0) if (base and peak) else 0.0,
            funding=self._fund_by_day.get(prev, 0.0),
            day=d)

    # ------------------------------------------------------------------ the daily books
    def _close_the_day(self, day: str, prev_day: str, price: float) -> None:
        d = self.boundary.deltas(day, prev_day)
        if d["issuance"] > 0:
            for a, w in zip(self.by_cohort[C.MINER], C.size_weights()):
                self.ledger.issue(d["issuance"] * w, a.name)
        if d["mint"] > 0:
            # New dollars arrive where dry powder is held, in the same proportions the
            # population opened with. Which cohort receives a mint is not observable; that
            # it arrives is.
            for cohort, share in C.CASH_PRIOR.items():
                if share <= 0:
                    continue
                for a, w in zip(self.by_cohort[cohort], C.size_weights()):
                    self.ledger.mint(d["mint"] * share * w, a.name)
        if d["burn"] > 0:
            holders = [a for a in self.agents if a.cash > 0]
            total = sum(a.cash for a in holders)
            if total > 0:
                for a in holders:
                    self.ledger.burn(d["burn"] * a.cash / total, a.name)
        if d["etf_in"] > 0:
            for a, w in zip(self.by_cohort[C.INSTITUTIONAL], C.size_weights()):
                self.ledger.inject(d["etf_in"] * w, a.name)
        if d["etf_out"] > 0:
            for a, w in zip(self.by_cohort[C.INSTITUTIONAL], C.size_weights()):
                self.ledger.withdraw(d["etf_out"] * w, a.name)

        self._open_budgets(d["issuance"], price)
        rate = self._fund_by_day.get(day)
        if rate:
            self.ledger.perp_funding(rate, price)
        self._reprice_perps(price, day)
        self.mm_anchor = {a.name: a.coins for a in self.by_cohort[C.MAKER]}

    def _open_budgets(self, issuance: float, price: float) -> None:
        """Each agent's trading allowance for the day ahead, in coins.

        A budget is not the same thing as a capacity. Capacity says what an agent COULD do
        if it liquidated itself; the budget says what this kind of participant actually
        does in a day. Both bind, and the smaller one wins.
        """
        for a in self.agents:
            if a.cohort in (C.ISSUER, C.VENUE, C.LEVERED):
                continue
            if a.cohort == C.MINER:
                w = C.size_weights()[a.size_rank]
                self.buy_budget[a.name] = 0.0
                self.sell_budget[a.name] = issuance * w * C.MINER_SELL_BUDGET
                continue
            cap = C.TURNOVER_CAP[a.cohort]
            self.buy_budget[a.name] = max(0.0, a.cash) / price * cap
            self.sell_budget[a.name] = max(0.0, a.coins) * cap

    def _reprice_perps(self, price: float, day: str) -> None:
        """A minimal perpetual book: the levered cohort is long the trend, the carry cohort
        is short against it, and open interest nets to zero by construction.

        This is the smallest thing that can be called a perp book and still be true. It
        exists so that funding has somebody to transfer cash between and so that "the
        levered cohort is underwater" is a quantity rather than a phrase. It is not
        anchored to observed open interest, which is the series the next phase downloads.
        """
        prev = _shift(day, -1)
        base, older = self._daily_close.get(prev), self._daily_close.get(_shift(day, -8))
        trend = (base / older - 1.0) if (base and older) else 0.0
        target = self.ledger.total_coins * PERP_SCALE * max(-1.0, min(1.0, trend * 5.0))
        longs, shorts = self.by_cohort[C.LEVERED], self.by_cohort[C.BASIS]
        deltas: dict[str, float] = {}
        for a, w in zip(longs, C.size_weights()):
            deltas[a.name] = target * w - a.perp
        held = sum(a.perp for a in shorts)
        for a, w in zip(shorts, C.size_weights()):
            deltas[a.name] = -target * w - a.perp
        net = sum(deltas.values())
        if abs(net) > 0:                      # absorb rounding on the largest short
            deltas[shorts[0].name] -= net
        self.ledger.perp_settle(deltas)

    # ------------------------------------------------------------------ one bucket
    def _step(self, b: Bucket) -> float:
        m = self._state(b)
        self.day_state.setdefault(b.day, m)
        price = b.vwap
        if b.volume <= 0:
            return 1.0

        buy_w_agg: dict[str, float] = {}
        buy_w_pass: dict[str, float] = {}
        sell_w_agg: dict[str, float] = {}
        sell_w_pass: dict[str, float] = {}
        cash_cap: dict[str, float] = {}
        coin_cap: dict[str, float] = {}

        for a in self.agents:
            if a.cohort in (C.ISSUER, C.VENUE, C.LEVERED):
                continue
            share = C.TAKER_SHARE[a.cohort]
            bd, sd = C.desires(a.cohort, a, m, self.mm_anchor.get(a.name, 0.0))
            cash_cap[a.name] = min(max(0.0, a.cash) / price,
                                   self.buy_budget.get(a.name, 0.0))
            coin_cap[a.name] = min(max(0.0, a.coins),
                                   self.sell_budget.get(a.name, 0.0))
            # Weight is DESIRE TIMES CAPACITY, not desire alone. Capacity already caps
            # the allocation, but using it only as a cap makes a rung-12 agent with a
            # rounding error of cash as influential as the rung-0 agent beside it, and the
            # size ladder then buys nothing. Wanting and being able to are both required.
            buy_w_agg[a.name] = bd * share * cash_cap[a.name]
            buy_w_pass[a.name] = bd * (1.0 - share) * cash_cap[a.name]
            sell_w_agg[a.name] = sd * share * coin_cap[a.name]
            sell_w_pass[a.name] = sd * (1.0 - share) * coin_cap[a.name]

        # Miners sell FIRST, and out of the pool rather than in competition for it. Their
        # flow is a cost of production, not an opinion: a miner with power bills sells the
        # coins it mined whatever the tape is doing. Leaving them to compete for a
        # weighted share meant they out-earned everybody by accident, which is the
        # opposite of what a structural seller is.
        forced = _forced_miner_sells(self.by_cohort[C.MINER], self.sell_budget,
                                     b.taker_sell, b.taker_buy)
        for k, (fa, fp) in forced.items():
            sell_w_agg[k] = sell_w_pass[k] = 0.0
            coin_cap[k] = 0.0
        fa_total = sum(v[0] for v in forced.values())
        fp_total = sum(v[1] for v in forced.values())

        # The four observed pools. Aggressive buying is met by passive selling of exactly
        # the same size, and vice versa - that is what the tape says, not what we assume.
        agg_buy = _waterfill(buy_w_agg, cash_cap, b.taker_buy)
        left_cash = {k: cash_cap[k] - agg_buy.get(k, 0.0) for k in cash_cap}
        pass_buy = _waterfill(buy_w_pass, left_cash, b.taker_sell)

        agg_sell = _waterfill(sell_w_agg, coin_cap, max(0.0, b.taker_sell - fa_total))
        left_coin = {k: coin_cap[k] - agg_sell.get(k, 0.0) for k in coin_cap}
        pass_sell = _waterfill(sell_w_pass, left_coin, max(0.0, b.taker_buy - fp_total))
        for k, (fa, fp) in forced.items():
            agg_sell[k] = fa
            pass_sell[k] = fp

        bought = {k: agg_buy.get(k, 0.0) + pass_buy.get(k, 0.0) for k in cash_cap}
        sold = {k: agg_sell.get(k, 0.0) + pass_sell.get(k, 0.0) for k in coin_cap}
        tb, ts = sum(bought.values()), sum(sold.values())

        # Buys and sells must be equal - every coin bought was sold. Where the population
        # could not fill one side, BOTH sides are scaled to the smaller, which keeps the
        # identity exact and turns the failure into a reported number instead of a leak.
        traded = min(tb, ts)
        if traded <= 1e-12:
            return 0.0
        bought = {k: v * traded / tb for k, v in bought.items()}
        sold = {k: v * traded / ts for k, v in sold.items()}

        deltas = {k: bought.get(k, 0.0) - sold.get(k, 0.0) for k in cash_cap}
        taker_dollars = (sum(agg_buy.values()) + sum(agg_sell.values())) * price
        fees = {}
        for k in cash_cap:
            f = (agg_buy.get(k, 0.0) + agg_sell.get(k, 0.0)) * price * TAKER_FEE + \
                (pass_buy.get(k, 0.0) + pass_sell.get(k, 0.0)) * price * MAKER_FEE
            if f > 0:
                fees[k] = f * (traded / max(tb, ts))
        for k in cash_cap:
            self.buy_budget[k] = max(0.0, self.buy_budget.get(k, 0.0) - bought.get(k, 0.0))
            self.sell_budget[k] = max(0.0, self.sell_budget.get(k, 0.0) - sold.get(k, 0.0))
        venue = self.by_cohort[C.VENUE][0].name
        self.ledger.settle(deltas, price, fees=fees, fee_to=venue)
        _ = taker_dollars
        return traded / b.volume

    # ------------------------------------------------------------------ the run
    def run(self, snapshot_daily: bool = True) -> Trajectory:
        traj = Trajectory()
        prev_day = self.bkts[0].day
        self._open_budgets(0.0, self.bkts[0].vwap)
        day_fills: list[float] = []
        for b in self.bkts:
            if b.day != prev_day:
                self._close_the_day(b.day, prev_day, b.vwap)
                if snapshot_daily and day_fills:
                    traj.days.append(prev_day)
                    traj.price.append(self._daily_close.get(prev_day, b.vwap))
                    traj.state.append(self.ledger.by_cohort(
                        self._daily_close.get(prev_day, b.vwap)))
                    traj.fill_ratio.append(sum(day_fills) / len(day_fills))
                day_fills = []
                prev_day = b.day
            fill = self._step(b)
            day_fills.append(fill)
            traj.buckets += 1
            traj.volume_observed += b.volume
            traj.volume_realised += b.volume * fill
        if snapshot_daily and day_fills:
            px = self._daily_close.get(prev_day, self.bkts[-1].vwap)
            traj.days.append(prev_day)
            traj.price.append(px)
            traj.state.append(self.ledger.by_cohort(px))
            traj.fill_ratio.append(sum(day_fills) / len(day_fills))
        traj.shortfall_events = self.ledger.shortfall_events
        self.ledger.check("end of run")
        return traj


# --------------------------------------------------------------------------- helpers

def baseline_desire(rec: "Reconstruction", cohort: str) -> dict[str, float]:
    """What a cohort WANTED each day, before the ledger told it what it could have.

    This is the control V2 scores against. It calls the same rule the reconstruction calls,
    on a balance sheet deliberately left empty, so the only thing it can respond to is the
    market - which is exactly the naive predictor the full machinery has to beat.
    """
    blank = Agent(name="baseline", cohort=cohort)
    out: dict[str, float] = {}
    for day, m in rec.day_state.items():
        bd, sd = C.desires(cohort, blank, m)
        out[day] = bd - sd
    return out


def _rolling_peak(close: dict[str, float], days: list[str], span: int) -> dict[str, float]:
    """The highest close in the `span` days STRICTLY before each day.

    Precomputed because the alternative - rescanning the history inside every bucket - is
    the difference between a run that takes seconds and one that takes an hour, and the
    answer is identical.
    """
    out: dict[str, float] = {}
    window: list[float] = []
    for i, d in enumerate(days):
        lo = _shift(d, -span)
        window = [close[x] for x in days[max(0, i - span - 5):i] if x >= lo]
        out[d] = max(window) if window else 0.0
    return out


def _forced_miner_sells(miners: list[Agent], budget: dict[str, float],
                        agg_pool: float, pass_pool: float) -> dict[str, tuple[float, float]]:
    """How much each miner sells this bucket, before anybody else gets a look in.

    Split across the aggressive and passive pools by the cohort's taker share, and clipped
    so a miner can never take more of either pool than the tape says was there.
    """
    share = C.TAKER_SHARE[C.MINER]
    want = {a.name: min(budget.get(a.name, 0.0), max(0.0, a.coins)) for a in miners}
    total = sum(want.values())
    if total <= 0:
        return {}
    a_cap = min(agg_pool, total * share)
    p_cap = min(pass_pool, total * (1.0 - share))
    return {k: (a_cap * v / total, p_cap * v / total) for k, v in want.items() if v > 0}


def _daily_closes(bkts: list[Bucket]) -> dict[str, float]:
    out: dict[str, float] = {}
    for b in bkts:
        out[b.day] = b.close
    return out


def _shift(day: str, days: int) -> str:
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (d + timedelta(days=days)).strftime("%Y-%m-%d")


def _funding_by_day(rows: list[dict]) -> dict[str, float]:
    """Mean settlement rate per UTC day. Three settlements a day; the ledger closes once."""
    acc: dict[str, list[float]] = {}
    for r in rows:
        day = datetime.fromtimestamp(int(r["t_ms"]) / 1000, timezone.utc).strftime("%Y-%m-%d")
        acc.setdefault(day, []).append(float(r["rate"]))
    return {d: sum(v) / len(v) for d, v in acc.items()}
