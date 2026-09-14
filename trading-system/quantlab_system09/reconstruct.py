"""L1 - the inverse problem: observables in, a cohort state trajectory out.

WHAT IS EXACT AND WHAT IS MODELLED, because the difference is the whole credibility of the
output and it is easy to blur.

  EXACT, straight from the tape, no model at all:
    - `volume` units changed hands, so somebody bought exactly that many and somebody sold
      exactly that many;
    - `taker_buy` of them were bought by the AGGRESSOR, which means the same quantity was
      sold passively, and `taker_sell` were sold aggressively and bought passively.
    Four pool sizes per bucket, observations rather than assumptions.

  MODELLED, and this is the only place the model lives:
    - WHICH participants filled each of those four pools.

So the reconstruction never invents volume and never invents a direction. It answers one
question per bucket - who did it - under constraints that make most of the wrong answers
impossible: nobody buys with cash they do not have, nobody sells units they do not hold,
nobody exceeds their kind's daily turnover, and the four pools must be filled exactly.

WHAT THIS VERSION ADDED, and why each one is about veracity rather than features:

  ONE SHARED WALLET ACROSS FOURTEEN ASSETS. Dry powder spent on Solana is not available for
  Bitcoin. The single-asset version gave BTC its own private share of the sector's cash,
  which invented liquidity; competition for one pool is most of what "managing the liquidity
  of the ecosystem" actually means.

  A POPULATION THAT CHANGES. Agents are born and retired against observed activity, and new
  ones arrive small, late and expensive - which is the only way a model can contain the
  people who bought the top, because the incumbents did not.

  ASSETS THAT ARRIVE. Each asset joins on the day it first appears in the record, bringing
  its float with it. Nothing trades before it exists.

  OBSERVED LEVERAGE. The perpetual book is pinned to Binance's published open interest
  instead of a constant times a trend.

  AN INFERRED FIAT CHANNEL. When the observed cash cannot fund the observed tape, the gap is
  ramped in as fiat and RECORDED. See `boundary.py`: the resulting series is a measurement of
  what the stablecoin float fails to explain, not a plug.

THE DIAGNOSTIC THAT MATTERS MORE THAN THE OUTPUT. `fill_ratio` is the fraction of observed
volume the reconstructed population was able to trade. A population whose stocks are
distributed roughly right fills essentially all of it; a collapse means the state is wrong in
a way no extra layer fixes, and it is reported on every run rather than discovered later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import cohorts as C
from . import segments as SEG
from .boundary import MINTED, Boundary
from .buckets import Bucket
from .ledger import Agent, Ledger

#: Binance's published spot schedule, rounded to the tier most volume actually pays. Fees
#: are a transfer to the venue rather than a leak: the exchange is inside the ledger.
TAKER_FEE = 0.0004
MAKER_FEE = 0.0001

#: Shrinking the population costs an amalgamation, so it only happens when the observed
#: activity level has fallen well through the last rung rather than wobbled past it.
SHRINK_HYSTERESIS = 3


@dataclass
class Trajectory:
    """What a run produces: daily cohort state, plus the diagnostics that judge it."""
    days: list[str] = field(default_factory=list)
    prices: list[dict] = field(default_factory=list)
    state: list[dict] = field(default_factory=list)
    fill_ratio: list[float] = field(default_factory=list)
    headcount: list[int] = field(default_factory=list)
    #: The reporting view, recomputed daily: six segments, and the sector's capitalisation.
    #: Stored per day rather than derived later because it needs per-AGENT net worth, which
    #: the cohort aggregate has already thrown away.
    segments: list[dict] = field(default_factory=list)
    market_cap: list[float] = field(default_factory=list)
    listed: list[int] = field(default_factory=list)
    buckets: int = 0
    shortfall_events: int = 0
    volume_observed: float = 0.0        # in dollars, so assets are commensurable
    volume_realised: float = 0.0

    @property
    def overall_fill(self) -> float:
        return self.volume_realised / self.volume_observed if self.volume_observed else 0.0


def _waterfill(weights: dict[str, float], caps: dict[str, float], pool: float,
               rounds: int = 10) -> tuple[dict[str, float], float]:
    """Share `pool` out in proportion to `weights`, never exceeding `caps`.

    Returns what was allocated and what could not be placed. The unplaced remainder is the
    honest output here: it is how the caller learns that the population could not fund or
    supply the tape, and it is what the fiat channel and the fill ratio are built from.
    """
    out = {k: 0.0 for k in weights}
    live = [k for k, w in weights.items() if w > 0.0 and caps.get(k, 0.0) > 0.0]
    if not live or pool <= 0.0:
        return out, max(0.0, pool)
    remaining = pool
    for _ in range(rounds):
        if remaining <= 1e-12 or not live:
            break
        total_w = sum(weights[k] for k in live)
        if total_w <= 0.0:
            break
        clamped = []
        placed = 0.0
        for k in live:
            want = remaining * weights[k] / total_w
            room = caps[k] - out[k]
            if want >= room:
                out[k] += room
                placed += room
                clamped.append(k)
            else:
                out[k] += want
                placed += want
        remaining -= placed
        if not clamped:
            break
        live = [k for k in live if k not in clamped]
    return out, max(0.0, remaining)


class Reconstruction:
    """One pass over the whole record, producing one cohort-state trajectory."""

    def __init__(self, tapes: dict[str, list[Bucket]], *, boundary: Boundary,
                 funding: dict[str, list[dict]] | None = None,
                 check_daily: bool = True, rank_cutoff: str = "2026-01-01") -> None:
        self.tapes = tapes
        self.boundary = boundary
        self.check_daily = check_daily

        # Assets ranked by the dollars that actually crossed in them. Rank 0 is held by
        # everybody; the tail is held by few. The ranking is over the WHOLE record, which is
        # a mild look-ahead in the affinity structure only - it decides who trades what, not
        # when or how much, and the alternative (re-ranking daily) would make an agent's
        # identity depend on the date it is asked about.
        # Ranked on the RESEARCH era only. The ranking decides who trades what, and letting
        # it see the sealed window would put 2026 inside the population's identity - a small
        # leak, but the kind this laboratory has been caught by before.
        turnover = {s: sum(b.dollars for b in bk if b.day < rank_cutoff)
                    for s, bk in tapes.items()}
        self.ranks = {s: i for i, s in enumerate(
            sorted(turnover, key=lambda k: -turnover[k]))}
        self.listings = {s: bk[0].day for s, bk in tapes.items()}

        # A bucket carries its own symbol. The first version kept a dict keyed by id(), which
        # is correct exactly until the object is pickled and then silently wrong - the ids are
        # different on the way back in and every bucket would be attributed to nothing.
        self.timeline = sorted((b for bk in tapes.values() for b in bk),
                               key=lambda b: (b.t_start, b.symbol))

        self.first_day = self.timeline[0].day
        self.agents = C.opening_population(self.first_day, self.ranks)
        self.ledger = Ledger(self.agents, check_every=False)
        self.cohort_of: dict[str, list[Agent]] = {}
        for a in self.agents:
            self.cohort_of.setdefault(a.cohort, []).append(a)

        # Dollars that crossed on the venue each day, and their trailing thirty-day sum.
        # One half of the population driver; see `cohorts.HEADCOUNT_BETA`.
        day_dollars: dict[str, float] = {}
        for b in self.timeline:
            day_dollars[b.day] = day_dollars.get(b.day, 0.0) + b.dollars
        self.turnover30 = _rolling_sum(day_dollars, 30)
        ordered = sorted(self.turnover30)
        self.turnover_base = (self.turnover30[ordered[min(29, len(ordered) - 1)]]
                              if ordered else 0.0)

        self.closes = {s: {b.day: b.close for b in bk} for s, bk in tapes.items()}
        self.peaks = {s: _rolling_peak(self.closes[s]) for s in tapes}
        self.funding = {s: _funding_by_day(rows) for s, rows in (funding or {}).items()}

        self.live: set[str] = set()               # assets that have listed
        self.mm_anchor: dict[tuple[str, str], float] = {}
        self.buy_budget: dict[str, float] = {}
        self.sell_budget: dict[str, float] = {}
        self.unfunded_today = 0.0                 # dollars of buying the sector could not do
        self.spent_today = 0.0                    # dollars of buying it DID do
        self.cash_at_open = 0.0
        self.day_state: dict[str, dict[str, C.MarketState]] = {}
        self.scale = C.SCALE_MIN

    # ------------------------------------------------------------------ market state
    def _state(self, sym: str, b: Bucket) -> C.MarketState:
        """Causal by construction: every return is computed from days STRICTLY earlier.

        A rule that saw the close of the day it is trading inside would reproduce the tape
        beautifully and mean nothing.
        """
        d = b.day
        cl = self.closes[sym]
        base = cl.get(_shift(d, -1))
        def r(k: int) -> float:
            old = cl.get(_shift(d, -k))
            return (base / old - 1.0) if (base and old) else 0.0
        peak = self.peaks[sym].get(d) or b.vwap
        fund = self.funding.get(sym, {}).get(_shift(d, -1), 0.0)
        return C.MarketState(symbol=sym, price=b.vwap, r_fast=r(2), r_slow=r(31),
                             r_glacial=r(91),
                             drawdown=(base / peak - 1.0) if (base and peak) else 0.0,
                             funding=fund, day=d)

    # ------------------------------------------------------------------ the daily books
    def _list_asset(self, sym: str, day: str, px: float) -> None:
        """One asset joins the ledger, bringing its float and its holders with it.

        The modelled sector is "participants reachable by this venue", so a listing is a
        boundary event: the float does not spring into existence, it becomes visible.
        """
        if sym in self.live:
            return
        self.live.add(sym)
        total = self.boundary.listing_float(sym)
        # Only Bitcoin has miners here; for every other asset their share goes to holders.
        prior = C.COIN_PRIOR if sym == MINTED else C.COIN_PRIOR_NO_MINER
        # Renormalise over the cohorts that actually hold this asset. A thinly-held token has
        # cohorts with no interested agent at all, and skipping their share silently floated
        # less than the asset's real supply - Worldcoin arrived two thirds short before this
        # line existed, which is a quiet lie about how many units exist rather than a rounding
        # error.
        holders_of = {co: [a for a in self.cohort_of[co] if a.active and sym in a.affinity]
                      for co in prior}
        live_share = sum(w for co, w in prior.items() if holders_of[co])
        if live_share <= 0:
            return
        for cohort, share in prior.items():
            holders = holders_of[cohort]
            if not holders:
                continue
            share /= live_share
            w = [C.rung_weight(a.size_rank) for a in holders]
            tot = sum(w)
            for a, wi in zip(holders, w):
                q = total * share * wi / tot
                self.ledger.issue(sym, q, a.name)
                # Everyone opens at the listing price, which asserts nothing: nobody starts
                # in profit and nobody starts underwater. The tape earns the rest.
                a.basis_cost[sym] = a.basis_cost.get(sym, 0.0) + q * px

    def _cash_boundary(self, day: str, prev_day: str) -> None:
        d_cash = self.boundary.cash_delta(day, prev_day)
        if d_cash > 0:
            self._spread_cash(d_cash, self.ledger.mint)
        elif d_cash < 0:
            self._drain_cash(-d_cash)

        # The fifth channel. Yesterday's unfunded buying is ramped in as fiat today, and
        # recorded. Causal: today's tape has not been seen yet.
        #
        # The amount is the shortfall divided by the sector's MEASURED cash velocity - the
        # dollars it actually spent yesterday per dollar it held. Ramping the bare shortfall
        # was the first attempt and it converges far too slowly, because a dollar handed to a
        # cohort that turns over three per cent of its cash a day buys three cents of the
        # gap. Dividing by the velocity the population just demonstrated is the smallest
        # correction that is not a guess: it is the cash that WOULD have been needed, at the
        # rate this market recycles cash.
        if self.unfunded_today > 0:
            velocity = (self.spent_today / self.cash_at_open) if self.cash_at_open > 0 else 0.0
            usd = self.unfunded_today / max(velocity, 0.05)
            self._spread_cash(usd, self.ledger.mint)
            self.boundary.record_ramp(day, usd)
        self.unfunded_today = 0.0
        self.spent_today = 0.0
        self.cash_at_open = self.ledger.total_cash

        flow = self.boundary.etf_flow(day)
        inst = [a for a in self.cohort_of[C.INSTITUTIONAL] if a.active]
        if flow and inst:
            w = [C.rung_weight(a.size_rank) for a in inst]
            tot = sum(w)
            for a, wi in zip(inst, w):
                if flow > 0:
                    self.ledger.inject(flow * wi / tot, a.name)
                else:
                    self.ledger.withdraw(-flow * wi / tot, a.name)

    def _spread_cash(self, usd: float, put) -> None:
        """New dollars arrive where dry powder is held, in the population's own proportions.

        Which participant receives a mint is not observable; that it arrived is. Spreading it
        by cohort prior and rung weight means new agents get a small share automatically,
        which is how new money and new participants arrive together.
        """
        targets = []
        for cohort, share in C.CASH_PRIOR.items():
            if share <= 0:
                continue
            for a in self.cohort_of.get(cohort, ()):
                if a.active:
                    targets.append((a, share * C.rung_weight(a.size_rank)))
        tot = sum(w for _, w in targets)
        if tot <= 0:
            return
        for a, w in targets:
            put(usd * w / tot, a.name)

    def _drain_cash(self, usd: float) -> None:
        holders = [a for a in self.agents if a.active and a.cash > 0]
        tot = sum(a.cash for a in holders)
        if tot <= 0:
            return
        for a in holders:
            self.ledger.burn(usd * a.cash / tot, a.name)

    def _population(self, day: str) -> None:
        """Agents arrive and leave with the observed activity level.

        Every cohort is resized by ONE shared scale, so the proportions between classes -
        many retail, fewer whales, fewer institutions still, a handful of market makers -
        hold at every point in the cycle instead of only at the start.
        """
        scale = C.target_scale(self.boundary.active_addresses(day),
                               self.boundary.active_addresses(self.first_day),
                               self.turnover30.get(day, 0.0), self.turnover_base)
        if scale <= self.scale * (1.0 + 1e-9) and scale >= self.scale * 0.90:
            return                              # hysteresis: resizing costs amalgamations
        for cohort in C.COHORT_SHARE:
            have = sum(1 for a in self.cohort_of.get(cohort, ()) if a.active)
            want = C.rungs_for(cohort, scale)
            if want > have:
                for rank in range(have, want):
                    fresh = C.new_agent(cohort, rank, want, day, self.ranks)
                    seat = self.ledger.index.get(fresh.name)
                    if seat is None:
                        self.ledger.add(fresh)
                        self.cohort_of.setdefault(cohort, []).append(self.ledger.agents[-1])
                    else:
                        # This rung existed before and was amalgamated away in a downturn.
                        # Reviving the seat rather than adding a second agent with the same
                        # name is the difference between a population that breathes and a
                        # crash the first time the market recovers.
                        back = self.ledger.agents[seat]
                        back.retired = ""
                        back.born = day
            elif want < have:
                keep = self.cohort_of[cohort][0]
                for a in self.cohort_of[cohort]:
                    if a.active and a.size_rank >= want and a is not keep:
                        self.ledger.amalgamate(a.name, keep.name, day)
        C.assign_classes(self.agents)
        C.assign_represents(self.agents)
        self.scale = scale

    def _perps(self, day: str, price_of: dict[str, float]) -> None:
        """Pin the perpetual book to Binance's published open interest.

        The levered cohort is the long side and the carry cohort is the short side - which is
        the cash-and-carry structure itself, not a convenience - so open interest nets to
        zero and funding has somebody real to flow between.
        """
        oi = self.boundary.open_interest(day)
        if oi is None or MINTED not in self.live:
            return
        longs = [a for a in self.cohort_of[C.LEVERED] if a.active]
        shorts = [a for a in self.cohort_of[C.BASIS] if a.active and MINTED in a.affinity]
        if not longs or not shorts:
            return
        deltas: dict[str, float] = {}
        wl = [C.rung_weight(a.size_rank) for a in longs]
        tl = sum(wl)
        for a, w in zip(longs, wl):
            deltas[a.name] = oi * w / tl - a.perp.get(MINTED, 0.0)
        ws = [C.rung_weight(a.size_rank) for a in shorts]
        ts = sum(ws)
        for a, w in zip(shorts, ws):
            deltas[a.name] = -oi * w / ts - a.perp.get(MINTED, 0.0)
        net = sum(deltas.values())
        deltas[shorts[0].name] -= net
        self.ledger.perp_settle(MINTED, deltas)
        rate = self.funding.get(MINTED, {}).get(day)
        px = price_of.get(MINTED)
        if rate and px:
            self.ledger.perp_funding(MINTED, rate, px)

    def _open_budgets(self, day: str, price_of: dict[str, float]) -> None:
        """Each agent's trading allowance for the day ahead, in dollars and in units.

        A budget is not a capacity. Capacity says what an agent COULD do if it liquidated
        itself; the budget says what this kind of participant actually does in a day. Both
        bind, and the smaller wins.
        """
        issuance = self._issuance_today
        vested = self._vested_today
        miners = [a for a in self.cohort_of[C.MINER] if a.active]
        wm = sum(C.rung_weight(a.size_rank) for a in miners) or 1.0
        for a in self.agents:
            if not a.active or a.cohort in (C.ISSUER, C.VENUE, C.LEVERED):
                continue
            if a.cohort == C.MINER:
                self.buy_budget[a.name] = 0.0
                self.sell_budget[a.name] = (issuance * C.rung_weight(a.size_rank) / wm
                                            * C.MINER_SELL_BUDGET)
                continue
            cap = C.TURNOVER_CAP[a.cohort]
            self.buy_budget[a.name] = max(0.0, a.cash) * cap
            for sym in a.affinity:
                q = a.coins.get(sym, 0.0)
                if q > 0:
                    budget = q * cap
                    if a.cohort == C.LTH and vested.get(sym):
                        # Vested supply is not a holding this agent chose, so the holder's
                        # turnover cap has no claim on it. Without this line the cap - which
                        # is what makes a long-term holder long-term - silently swallows the
                        # unlock and the tokens never reach the market at all.
                        budget += (vested[sym] * C.rung_weight(a.size_rank)
                                   / self._lth_weight(sym) * C.VESTED_SELL_BUDGET)
                    self.sell_budget[f"{a.name}|{sym}"] = budget
        for a in self.cohort_of[C.MAKER]:
            for sym in a.affinity:
                self.mm_anchor[(a.name, sym)] = a.coins.get(sym, 0.0)

    def _lth_weight(self, sym: str) -> float:
        w = sum(C.rung_weight(a.size_rank) for a in self.cohort_of[C.LTH]
                if a.active and sym in a.affinity)
        return w or 1.0

    def _close_the_day(self, day: str, prev_day: str, price_of: dict[str, float]) -> None:
        self._vested_today = {}
        self._issuance_today = self.boundary.issuance(day, prev_day)
        if self._issuance_today > 0 and MINTED in self.live:
            miners = [a for a in self.cohort_of[C.MINER] if a.active]
            w = [C.rung_weight(a.size_rank) for a in miners]
            tot = sum(w) or 1.0
            for a, wi in zip(miners, w):
                self.ledger.issue(MINTED, self._issuance_today * wi / tot, a.name)
        self._supply_boundary(day, prev_day)
        self._cash_boundary(day, prev_day)
        self._population(day)
        self._perps(day, price_of)
        self._open_budgets(day, price_of)

    def _supply_boundary(self, day: str, prev_day: str) -> None:
        """Every other asset emits and burns too, and the ledger has to carry it.

        v1 floated an asset once, at listing, and never changed its supply again - so a token
        that tripled its float over two years of unlocks stayed at its listing size, and one
        that burned a fifth of itself kept every burned unit. Both are level errors the V5
        calibration can see.

        Where the new units go matters as much as how many there are. Emission and vesting do
        not arrive in the hands of the crowd: they arrive with foundations, validators and
        early backers, who are structural sellers of them. So the long-term-holder cohort
        receives them by size, and the sell budget that follows treats them exactly as miner
        issuance is treated - forced flow, allocated before anyone's opinion. Burns are taken
        back from holders in proportion to what they hold, which is what a burn is.
        """
        for sym in sorted(self.live):
            delta = self.boundary.supply_delta(sym, day, prev_day)
            if abs(delta) < 1e-9:
                continue
            if delta > 0:
                holders = [a for a in self.cohort_of[C.LTH]
                           if a.active and sym in a.affinity]
                w = [C.rung_weight(a.size_rank) for a in holders]
                tot = sum(w)
                if not tot:
                    continue
                for a, wi in zip(holders, w):
                    self.ledger.issue(sym, delta * wi / tot, a.name)
                self._vested_today[sym] = delta
            else:
                held = {a.name: a.coins.get(sym, 0.0) for a in self.agents
                        if a.active and a.coins.get(sym, 0.0) > 0.0}
                total = sum(held.values())
                if total <= 0:
                    continue
                burn = min(-delta, total)
                for name, q in held.items():
                    self.ledger.burn_units(sym, burn * q / total, name)

    # ------------------------------------------------------------------ one bucket
    def _step(self, sym: str, b: Bucket) -> float:
        if sym not in self.live:
            # An asset joins the ledger on its first bucket rather than at the day's open,
            # because its float has to arrive carrying a PRICE and the open does not have
            # one yet. Opening every holder at the listing price asserts nothing: nobody
            # starts in profit, nobody starts underwater, and the tape earns the rest.
            self._list_asset(sym, b.day, b.vwap)
        if b.volume <= 0:
            return 1.0
        m = self._state(sym, b)
        self.day_state.setdefault(b.day, {}).setdefault(sym, m)
        price = b.vwap

        buy_agg: dict[str, float] = {}
        buy_pass: dict[str, float] = {}
        sell_agg: dict[str, float] = {}
        sell_pass: dict[str, float] = {}
        cash_cap: dict[str, float] = {}
        coin_cap: dict[str, float] = {}
        miners: dict[str, float] = {}

        for a in self.agents:
            if not a.active or a.cohort in (C.ISSUER, C.VENUE, C.LEVERED):
                continue
            if sym not in a.affinity:
                continue
            share = C.TAKER_SHARE[a.cohort]
            bd, sd = C.desires(a.cohort, a, m, self.mm_anchor.get((a.name, sym), 0.0))
            # Capacity in UNITS: cash buys at the bucket's price, and both the wallet and
            # the day's budget bind.
            cash_cap[a.name] = min(max(0.0, a.cash),
                                   self.buy_budget.get(a.name, 0.0)) / price
            coin_cap[a.name] = min(a.coins.get(sym, 0.0),
                                   self.sell_budget.get(f"{a.name}|{sym}", 0.0))
            if a.cohort == C.MINER:
                miners[a.name] = min(a.coins.get(sym, 0.0),
                                     self.sell_budget.get(a.name, 0.0)) if sym == MINTED else 0.0
                continue
            # Weight is DESIRE TIMES CAPACITY. Capacity already caps the allocation, but
            # using it only as a cap makes a rung-40 agent with a rounding error of cash as
            # influential as the rung-0 agent beside it, and the size ladder buys nothing.
            buy_agg[a.name] = bd * share * cash_cap[a.name]
            buy_pass[a.name] = bd * (1.0 - share) * cash_cap[a.name]
            sell_agg[a.name] = sd * share * coin_cap[a.name]
            sell_pass[a.name] = sd * (1.0 - share) * coin_cap[a.name]

        # Miners sell FIRST and out of the pool rather than in competition for it. Their flow
        # is a cost of production, not an opinion: a miner with power bills sells what it
        # mined whatever the tape is doing.
        forced_a, forced_p = {}, {}
        want = sum(miners.values())
        if want > 0:
            ms = C.TAKER_SHARE[C.MINER]
            a_cap = min(b.taker_sell, want * ms)
            p_cap = min(b.taker_buy, want * (1.0 - ms))
            for k, v in miners.items():
                forced_a[k] = a_cap * v / want
                forced_p[k] = p_cap * v / want
        fa, fp = sum(forced_a.values()), sum(forced_p.values())

        agg_buy, short_ab = _waterfill(buy_agg, cash_cap, b.taker_buy)
        left_cash = {k: cash_cap[k] - agg_buy.get(k, 0.0) for k in cash_cap}
        pass_buy, short_pb = _waterfill(buy_pass, left_cash, b.taker_sell)

        agg_sell, _ = _waterfill(sell_agg, coin_cap, max(0.0, b.taker_sell - fa))
        left_coin = {k: coin_cap[k] - agg_sell.get(k, 0.0) for k in coin_cap}
        pass_sell, _ = _waterfill(sell_pass, left_coin, max(0.0, b.taker_buy - fp))
        for k in forced_a:
            agg_sell[k] = forced_a[k]
            pass_sell[k] = forced_p[k]

        # Buying the population could not fund becomes tomorrow's fiat ramp, in dollars.
        self.unfunded_today += (short_ab + short_pb) * price

        bought = {k: agg_buy.get(k, 0.0) + pass_buy.get(k, 0.0) for k in cash_cap}
        sold = {k: agg_sell.get(k, 0.0) + pass_sell.get(k, 0.0)
                for k in set(coin_cap) | set(forced_a)}
        tb, ts = sum(bought.values()), sum(sold.values())
        traded = min(tb, ts)
        if traded <= 1e-12:
            return 0.0
        deltas: dict[str, float] = {}
        for k, v in bought.items():
            deltas[k] = deltas.get(k, 0.0) + v * traded / tb
        for k, v in sold.items():
            deltas[k] = deltas.get(k, 0.0) - v * traded / ts
        scale_b, scale_s = traded / tb, traded / ts

        fees = {}
        for k in set(agg_buy) | set(agg_sell) | set(pass_buy) | set(pass_sell):
            f = ((agg_buy.get(k, 0.0) * scale_b + agg_sell.get(k, 0.0) * scale_s) * TAKER_FEE
                 + (pass_buy.get(k, 0.0) * scale_b
                    + pass_sell.get(k, 0.0) * scale_s) * MAKER_FEE) * price
            if f > 0:
                fees[k] = f
        self.ledger.settle(sym, deltas, price, fees=fees,
                           fee_to=self.cohort_of[C.VENUE][0].name)
        self.spent_today += traded * price

        for k, v in bought.items():
            self.buy_budget[k] = max(0.0, self.buy_budget.get(k, 0.0) - v * scale_b * price)
        for k, v in sold.items():
            key = f"{k}|{sym}"
            self.sell_budget[key] = max(0.0, self.sell_budget.get(key, 0.0) - v * scale_s)
            if k in forced_a:
                self.sell_budget[k] = max(0.0, self.sell_budget.get(k, 0.0) - v * scale_s)
        return traded / b.volume

    # ------------------------------------------------------------------ the run
    def run(self, until: str | None = None) -> Trajectory:
        traj = Trajectory()
        prev_day = self.first_day
        price_of: dict[str, float] = {}
        fills: list[tuple[float, float]] = []

        self._issuance_today = 0.0
        self._vested_today: dict[str, float] = {}
        self.cash_at_open = self.ledger.total_cash
        self._open_budgets(self.first_day, price_of)

        for b in self.timeline:
            sym = b.symbol
            if until and b.day > until:
                break
            if b.day != prev_day:
                self._snapshot(traj, prev_day, price_of, fills)
                fills = []
                self._close_the_day(b.day, prev_day, price_of)
                if self.check_daily:
                    self.ledger.check(f"open of {b.day}")
                prev_day = b.day
            price_of[sym] = b.vwap
            fill = self._step(sym, b)
            fills.append((fill, b.dollars))
            traj.buckets += 1
            traj.volume_observed += b.dollars
            traj.volume_realised += b.dollars * fill
        self._snapshot(traj, prev_day, price_of, fills)
        traj.shortfall_events = self.ledger.shortfall_events
        self.ledger.check("end of run")
        return traj

    def _snapshot(self, traj: Trajectory, day: str, price_of: dict[str, float],
                  fills: list[tuple[float, float]]) -> None:
        if not fills:
            return
        w = sum(d for _, d in fills) or 1.0
        traj.days.append(day)
        traj.prices.append(dict(price_of))
        traj.state.append(self.ledger.by_cohort(price_of))
        traj.fill_ratio.append(sum(f * d for f, d in fills) / w)
        traj.headcount.append(sum(1 for a in self.agents if a.active))
        traj.listed.append(len(self.live))
        seg = SEG.snapshot(self.agents, price_of)
        traj.segments.append({k: {"players": v["players"], "represents": v["represents"],
                                  "cash": v["cash"], "assets": v["assets"],
                                  "coins": v["coins"], "basis": v["basis"]}
                              for k, v in seg.items()})
        traj.market_cap.append(SEG.market_cap(self.agents, price_of))


# --------------------------------------------------------------------------- helpers

def baseline_desire(rec: Reconstruction, cohort: str, symbol: str) -> dict[str, float]:
    """What a cohort WANTED each day, before the ledger told it what it could have.

    The control V2 scores against. It calls the same rule the reconstruction calls, on a
    balance sheet deliberately left empty, so the only thing it can respond to is the market
    - which is exactly the naive predictor the full machinery has to beat.
    """
    blank = Agent(name="baseline", cohort=cohort)
    out: dict[str, float] = {}
    for day, per_sym in rec.day_state.items():
        m = per_sym.get(symbol)
        if m is None:
            continue
        bd, sd = C.desires(cohort, blank, m)
        out[day] = bd - sd
    return out


def _rolling_sum(per_day: dict[str, float], span: int) -> dict[str, float]:
    """Trailing `span`-day sum on the days that exist, ending at each day inclusive."""
    days = sorted(per_day)
    out: dict[str, float] = {}
    run = 0.0
    for i, d in enumerate(days):
        run += per_day[d]
        if i >= span:
            run -= per_day[days[i - span]]
        out[d] = run
    return out


def _rolling_peak(close: dict[str, float], span: int = 365) -> dict[str, float]:
    """The highest close in the `span` days STRICTLY before each day.

    Precomputed because rescanning history inside every bucket is the difference between a
    run that takes minutes and one that takes hours, and the answer is identical.
    """
    days = sorted(close)
    out: dict[str, float] = {}
    for i, d in enumerate(days):
        lo = _shift(d, -span)
        window = [close[x] for x in days[max(0, i - span - 5):i] if x >= lo]
        out[d] = max(window) if window else 0.0
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
