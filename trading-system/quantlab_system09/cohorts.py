"""The population: who the participants are, how big they are, what they trade, and when
they arrive.

Section 4 of the design document argued that headcount is not the design parameter - the
number of distinct BEHAVIOURAL TYPES is, and so is the size distribution within each type.
Two things have been added since the first MVP, both because the operator asked for the
ecosystem to be managed with the maximum veracity available:

  PLAYERS ARRIVE AND LEAVE. The first version created 106 agents on day one and never made
  another. That is wrong for crypto in a way that matters: a bull market does not just give
  the incumbents more money, it brings in people who were not there, and those people buy at
  the top and carry a cost basis nobody else has. Headcount is now driven by two OBSERVED
  series that bracket the truth - Bitcoin active addresses and the stablecoin float, see
  `HEADCOUNT_BETA` - and new agents enter at the small end of the size ladder carrying the
  new money that arrived with them.

  AGENTS TRADE A FEW ASSETS, NOT ALL OF THEM. The operator's own observation: nobody trades
  fifty coins at once. Each agent carries an affinity set, deterministic from its name, with
  Bitcoin held by everybody and the long tail held by few.

THE PROPENSITY RULES are deliberately simple and deliberately NOT FITTED. They are the
Brock-Hommes family the design named as the published baseline: a small number of
interpretable rules whose failure is diagnosable. Every constant below is a prior taken from
the shape of the cohort, not a number calibrated against this laboratory's data.

What a rule returns is a DESIRE, not a trade. Desire is multiplied by capacity and then
normalised against the tape's actual volume in `reconstruct.py`, because the tape - not the
rule - decides how much changed hands.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from .ledger import Agent

# --------------------------------------------------------------------------- types

LTH = "long_term_holders"
MOMENTUM = "momentum_retail"
DIP = "dip_buyers"
MAKER = "market_makers"
BASIS = "basis_arb"
LEVERED = "levered_directional"
INSTITUTIONAL = "institutional"
MINER = "miners"
ISSUER = "stablecoin_issuers"
VENUE = "exchanges"

TRADING = (LTH, MOMENTUM, DIP, MAKER, BASIS, INSTITUTIONAL)
BOUNDARY = (MINER, ISSUER, VENUE)
PERP_ONLY = (LEVERED,)

#: Size rungs each trading cohort opens with, and the ceiling growth may reach. The ladder
#: is Zipf, so rung k holds a share proportional to 1/(k+1); new entrants are appended at
#: the bottom, which is where new participants actually appear.
LADDER = 13
MAX_RUNGS = 60

#: How the population tracks the observed world - and the weakest link in this system, so it
#: is spelled out.
#:
#: The number of distinct economic participants in crypto is not observable. Two free series
#: BRACKET it and they disagree violently:
#:   * Bitcoin active addresses peaked in 2017 and have been flat ever since - by that
#:     measure the crowd never grew, which is false, because the activity moved onto
#:     exchanges and other chains where this series cannot see it;
#:   * the venue's own dollar turnover grew by orders of magnitude over the same period - by
#:     that measure the crowd exploded, which is also false, because turnover is count TIMES
#:     size and the size per participant grew too.
#:
#: The truth is between them, so the driver is the GEOMETRIC MEAN of the two growth factors,
#: raised to a sub-linear exponent. Both halves are observed; the combination and the exponent
#: are a stated prior, not a fitted one, and the population count is the number in this system
#: least entitled to be believed.
#:
#: The stablecoin float was tried as the second bracket first and rejected: the free series
#: begins at a hundred thousand dollars in 2017, so every later reading is a millionfold
#: growth and the ladder saturates in the first year. That number measures the birth of a
#: product, not the arrival of a crowd. Turnover is measured on the same venue this system
#: reconstructs, which is the one place its base is trustworthy.
HEADCOUNT_BETA = 0.40

#: How aggressively each type demands immediacy: the share of its flow that crosses the
#: spread. This decides whether a cohort shows up on the taker side of the tape or the maker
#: side, and it is the only place the taxonomy touches microstructure.
TAKER_SHARE = {
    LTH: 0.15,             # patient; accumulates and distributes on limits
    MOMENTUM: 0.80,        # chases; pays the spread by definition
    DIP: 0.45,             # works orders into weakness but will reach when it is scared
    MAKER: 0.05,           # passive by definition; crosses only to manage inventory
    BASIS: 0.30,           # cares about carry, not about the next tick
    INSTITUTIONAL: 0.50,   # scheduled execution, half of it aggressive
    MINER: 0.20,           # sells into bids, rarely in a hurry
}

#: The fraction of its own book a cohort turns over in ONE DAY. This is the constraint that
#: makes a holder a holder; without it the allocator hands flow to whoever holds the most and
#: the taxonomy is decoration.
#:
#: The long-term-holder figure was 0.002 in the first MVP and that was far too loose - the
#: cohort shed two million coins in 2021 alone. Published long-term-holder supply swings by
#: roughly a tenth of its base over a full cycle, which is nearer three hundredths of a per
#: cent a day, and that is what it is set to now.
TURNOVER_CAP = {
    LTH: 0.0003,
    MOMENTUM: 0.15,
    DIP: 0.10,
    MAKER: 2.00,           # turning inventory over several times a day is the business
    BASIS: 0.08,
    INSTITUTIONAL: 0.03,   # slow, calendar-driven, size-constrained
    MINER: 1.00,           # unused: miners are budgeted by issuance, not by stack
}

#: Miners sell what they mine. Net miner outflows track issuance closely over any window
#: longer than a few weeks, so the daily sell budget is a multiple of the units issued that
#: day rather than a fraction of the stack they are sitting on.
MINER_SELL_BUDGET = 1.20

#: Opening distribution of an asset's float when it joins the venue. Priors, stated rather
#: than fitted, and the single largest source of LEVEL error in the system. Long-term holders
#: absorb the dormant and lost supply, which is why their share is so large; the venue holds
#: its customers' coins custodially rather than on its own book.
COIN_PRIOR = {
    LTH: 0.60, MOMENTUM: 0.10, DIP: 0.08, MAKER: 0.05,
    BASIS: 0.05, INSTITUTIONAL: 0.06, MINER: 0.06,
}
#: Only Bitcoin has miners in this model; for every other asset their share goes to holders.
COIN_PRIOR_NO_MINER = {**{k: v for k, v in COIN_PRIOR.items() if k != MINER},
                       LTH: COIN_PRIOR[LTH] + COIN_PRIOR[MINER]}

#: Where dry powder sits. Market makers and arbitrageurs carry cash out of proportion to
#: their holdings; holders carry almost none, which is what makes them holders.
CASH_PRIOR = {
    LTH: 0.05, MOMENTUM: 0.18, DIP: 0.22, MAKER: 0.18,
    BASIS: 0.17, INSTITUTIONAL: 0.10, MINER: 0.00, LEVERED: 0.10,
}


# --------------------------------------------------------------------------- the ladder

def size_weights(rungs: int, alpha: float = 1.0) -> list[float]:
    """Zipf shares for one cohort's size ladder, largest first.

    `alpha = 1.0` is the plain Zipf law; it puts about a third of a cohort's wealth in its
    single largest agent and a long thin tail below, which is the shape both traditional and
    crypto wealth data keep producing.
    """
    raw = [1.0 / (k ** alpha) for k in range(1, rungs + 1)]
    total = sum(raw)
    return [r / total for r in raw]


def rung_weight(rank: int, alpha: float = 1.0) -> float:
    """The unnormalised Zipf weight of one rung. Used when the ladder grows at the bottom."""
    return 1.0 / ((rank + 1) ** alpha)


# --------------------------------------------------------------------------- affinity

def affinity_for(name: str, symbol: str, rank: int) -> bool:
    """Does this agent trade this asset? Deterministic, stateless, reproducible.

    Bitcoin is held by everybody. Everything else is held with a probability that falls with
    the asset's turnover rank, so the long tail is traded by few participants - which is both
    true and the reason a fourteen-asset ledger costs far less than fourteen times a
    one-asset one.
    """
    if rank == 0:
        return True
    p = max(0.12, 1.0 / (1.0 + 0.65 * rank))
    h = hashlib.blake2b(f"{name}|{symbol}".encode(), digest_size=4).digest()
    return int.from_bytes(h, "big") / 0xFFFFFFFF < p


def affinity_set(name: str, ranks: dict[str, int]) -> frozenset[str]:
    return frozenset(s for s, r in ranks.items() if affinity_for(name, s, r))


# --------------------------------------------------------------------------- population

def new_agent(cohort: str, rank: int, day: str, ranks: dict[str, int]) -> Agent:
    """One participant, born empty. Whatever it is given afterwards is a boundary event."""
    name = f"{cohort}#{rank:03d}"
    return Agent(name=name, cohort=cohort, size_rank=rank, born=day,
                 affinity=affinity_set(name, ranks))


def opening_population(day: str, ranks: dict[str, int]) -> list[Agent]:
    """The books on the first day of the record: every cohort at `LADDER` rungs, all empty.

    Nothing is handed out here. Floats arrive when an asset lists and cash arrives when it is
    minted or ramped in, so that every unit and every dollar in this system can be traced to
    a boundary event rather than to a constructor.
    """
    agents: list[Agent] = []
    for cohort in (*TRADING, MINER, LEVERED):
        for rank in range(LADDER):
            agents.append(new_agent(cohort, rank, day, ranks))
    for cohort in (ISSUER, VENUE):
        agents.append(Agent(name=f"{cohort}#000", cohort=cohort, born=day))
    return agents


def target_rungs(addresses_now: float, addresses_base: float,
                 cash_now: float = 0.0, cash_base: float = 0.0) -> int:
    """How many rungs each trading cohort should have, given the observed world.

    See `HEADCOUNT_BETA`: the two proxies bracket the truth and neither is usable alone, so
    this takes the geometric mean of their growth factors. With only one of them available
    it falls back to that one, which is the honest degradation rather than a guess.
    """
    factors = []
    if addresses_base > 0 and addresses_now > 0:
        factors.append(addresses_now / addresses_base)
    if cash_base > 0 and cash_now > 0:
        factors.append(cash_now / cash_base)
    if not factors:
        return LADDER
    geo = 1.0
    for f in factors:
        geo *= f
    geo **= 1.0 / len(factors)
    return max(LADDER, min(MAX_RUNGS, int(round(LADDER * geo ** HEADCOUNT_BETA))))


# --------------------------------------------------------------------------- market state

@dataclass(slots=True)
class MarketState:
    """Everything a propensity rule is allowed to see about one asset on one day.

    Deliberately short. A rule that needs more than this is a rule that is being fitted.
    """
    symbol: str
    price: float
    r_fast: float        # return over roughly one day
    r_slow: float        # return over roughly one month
    r_glacial: float     # return over roughly one quarter
    drawdown: float      # <= 0, from the trailing one-year high
    funding: float       # last perpetual settlement rate, signed
    day: str


def _softplus(x: float, scale: float = 1.0) -> float:
    """A hinge with a soft corner. Keeps desires positive and gradients finite."""
    z = x / scale
    if z > 30:
        return x
    return scale * math.log1p(math.exp(z))


# --------------------------------------------------------------------------- the rules

def desires(cohort: str, agent: Agent, m: MarketState,
            anchor_inventory: float = 0.0) -> tuple[float, float]:
    """(buy desire, sell desire) for one agent in one asset, both non-negative.

    Each rule reads the market AND the agent's own book. Conditioning on own state is the
    detail that makes the population self-limiting: a cohort deep in profit distributes, a
    cohort out of cash cannot buy however much it wants to, and without that the agents buy
    forever and the model explodes.

    `anchor_inventory` is the only piece of history a rule is given: the inventory a market
    maker is trying to revert to. It is held by the caller because an agent is a balance
    sheet and a target is a belief.
    """
    profit = agent.profit_ratio(m.symbol, m.price)

    if cohort == LTH:
        # Almost never sells; sells only on extreme unrealised profit. The buy side is a
        # small constant: holders accumulate regardless of the tape, which is the whole
        # content of the HODL-wave literature.
        return 0.15, _softplus(profit - 1.00, 0.35)

    if cohort == MOMENTUM:
        # Buys strength on two horizons, sells weakness on the fast one. No cash discipline:
        # the rule never looks at how much dry powder is left, which is exactly why this
        # cohort is the first to hit its capacity floor in a rally.
        return (max(0.0, m.r_slow) * 4.0 + max(0.0, m.r_fast) * 6.0,
                max(0.0, -m.r_fast) * 8.0 + max(0.0, -m.r_slow) * 2.0)

    if cohort == DIP:
        # Buys drawdown, with finite dry powder; takes profit early. The asymmetry between
        # the two thresholds is what makes this cohort a net supplier of liquidity in panics
        # and a net taker of it in rallies.
        return max(0.0, -m.drawdown) * 5.0, _softplus(profit - 0.25, 0.20)

    if cohort == MAKER:
        # Inventory-averse: reverts to the inventory it opened the day with. Quotes both
        # sides, so both desires are live at once and the larger one wins.
        if anchor_inventory <= 0.0:
            return 0.5, 0.5
        gap = (anchor_inventory - agent.held(m.symbol)) / anchor_inventory
        return max(0.0, gap) * 3.0 + 0.3, max(0.0, -gap) * 3.0 + 0.3

    if cohort == BASIS:
        # Cares only about carry. Positive funding pays it to be long spot and short perp, so
        # the spot leg follows the sign of funding and nothing else.
        f = m.funding * 1000.0
        return max(0.0, f), max(0.0, -f)

    if cohort == INSTITUTIONAL:
        # Slow, calendar-driven, asymmetric: allocators are much quicker to add than to cut.
        # It reads only the glacial trend, which is what makes this cohort's inferred flow a
        # genuine prediction of the ETF series rather than a copy of it.
        return max(0.0, m.r_glacial) * 3.0 + 0.10, max(0.0, -m.r_glacial) * 1.5

    if cohort == MINER:
        # Structural seller: converts issuance to cash to pay for power and hardware. Never a
        # buyer. The one cohort whose flow is a cost of production rather than an opinion.
        return 0.0, 1.0

    return 0.0, 0.0
