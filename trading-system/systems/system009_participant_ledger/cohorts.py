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

#: THE SHAPE OF THE CROWD, and the mistake it replaced.
#:
#: The first version gave every behavioural cohort the same number of rungs and then split the
#: private agents into whales and retail by a net-worth threshold. That produced an upside
#: down market: 148 whales, 84 institutions and 20 retail. Reality is the other way up, and the
#: operator said so - institutions are few, whales are more, and retail is thousands upon
#: thousands of people.
#:
#: The fix is to make the CLASS intrinsic and the HEADCOUNT proportional. A whale is a large
#: private holder; an institution is a funded desk buying a billion dollars of Bitcoin for an
#: ETF; a market maker is a firm quoting both sides and earning the spread. They are different
#: creatures, not different sizes of one creature, so each agent is born into its class and the
#: number of agents per class follows the real market.
#:
#: An agent remains a PROFILE GROUP rather than a person - one retail agent stands for a
#: hundred thousand people who behave the same way. That is the operator instruction in one
#: line: group them by profile, keep the proportions, do not write fifty million balance
#: sheets.
AGENT_BUDGET = 560          # agents at full growth, before the two venue operators
SCALE_MIN = 0.22            # the share of that budget the market opens with in 2017

#: Share of the agent budget by behavioural cohort. The private cohorts dominate the count
#: because the private crowd dominates the real one.
COHORT_SHARE = {
    LTH: 0.22, MOMENTUM: 0.24, DIP: 0.22, LEVERED: 0.14,     # private: 82%
    INSTITUTIONAL: 0.04, BASIS: 0.03,                        # funded desks: 7%
    MAKER: 0.03,                                             # a handful of firms
    MINER: 0.05,                                             # pools and public miners
}

#: Within a private cohort, the top slice of the Zipf ladder are the whales - few, and each
#: one large. Everything below is the crowd.
WHALE_RUNG_FRACTION = 0.12

#: How many real participants one agent stands for, per class, summed across the class. Stated
#: priors for REPORTING ONLY; they never touch the simulation. The retail figure is the order
#: of magnitude of people who actually trade rather than everyone who ever owned a coin; the
#: whale figure is the usual count of entities above a thousand bitcoin; the market-maker
#: figure is the number of firms that matter, which really is about that small.
REPRESENTS = {
    "retail": 50_000_000, "whales": 10_000, "institutional": 400,
    "market_makers": 25, "miners": 60, "venues": 210,
}

LADDER = 13                 # the minimum rungs any cohort carries

#: How the population tracks the observed world - and the weakest link in this system.
#:
#: The number of distinct economic participants in crypto is not observable. Two free series
#: BRACKET it and they disagree violently: Bitcoin active addresses peaked in 2017 and have
#: been flat since, because the activity moved onto exchanges and other chains where that
#: series cannot see it; the venue own dollar turnover grew by orders of magnitude, but
#: turnover is count TIMES size and the size per participant grew too.
#:
#: The truth is between them, so the driver is the GEOMETRIC MEAN of the two growth factors
#: raised to a sub-linear exponent. Both halves are observed; the combination and the exponent
#: are a stated prior, and the population count is the number here least entitled to belief.
#:
#: The stablecoin float was tried as the second bracket and rejected: the free series begins at
#: a hundred thousand dollars in 2017, so every later reading is a millionfold growth and the
#: ladder saturates in its first year. That measures the birth of a product, not a crowd.
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

#: What fraction of a day's vesting or emission the receiving holders are allowed to sell.
#: Slightly above one for the same reason the miner budget is: an unlock is usually met with
#: selling of a little more than the unlock itself, because it is announced in advance. It is
#: a budget, not an obligation - the tape still has to want the flow.
VESTED_SELL_BUDGET = 1.10

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
    """Zipf shares for one cohort's size ladder, largest first."""
    raw = [1.0 / (k ** alpha) for k in range(1, rungs + 1)]
    total = sum(raw)
    return [r / total for r in raw]


def rung_weight(rank: int, alpha: float = 1.0) -> float:
    """The unnormalised Zipf weight of one rung. Used when the ladder grows at the bottom."""
    return 1.0 / ((rank + 1) ** alpha)


def rungs_for(cohort: str, scale: float) -> int:
    """How many agents this cohort carries at a given growth scale."""
    if cohort not in COHORT_SHARE:
        return 0
    return max(2, int(round(AGENT_BUDGET * COHORT_SHARE[cohort] * scale)))


def class_of(cohort: str, rank: int, rungs: int) -> str:
    """Which class an agent belongs to, from WHERE IT SITS IN ITS LADDER.

    Structural, never monetary - that is the property that matters, and it is what both
    earlier attempts got wrong by testing the balance sheet. But it is relative to the
    cohort's CURRENT size rather than fixed at birth: a class assigned against the ladder as
    it stood on the day an agent appeared drifts as the ladder grows, and the market ended
    up with twelve whales against twenty-eight institutions - the pyramid upside down again,
    by a different route. `assign_classes` refreshes it whenever the population is resized.
    """
    if cohort == MAKER:
        return "market_makers"
    if cohort in (INSTITUTIONAL, BASIS):
        return "institutional"
    if cohort == MINER:
        return "miners"
    if cohort in (ISSUER, VENUE):
        return "venues"
    return "whales" if rank < max(1, int(round(rungs * WHALE_RUNG_FRACTION))) else "retail"


def assign_classes(agents) -> None:
    """Refresh every active agent's class against its cohort's current ladder size."""
    sizes: dict[str, int] = {}
    for a in agents:
        if a.active and a.cohort in COHORT_SHARE:
            sizes[a.cohort] = max(sizes.get(a.cohort, 0), a.size_rank + 1)
    for a in agents:
        if a.active and a.cohort in COHORT_SHARE:
            a.segment = class_of(a.cohort, a.size_rank, sizes[a.cohort])


def assign_represents(agents) -> None:
    """Distribute each class's real-world headcount across the agents that carry it.

    Normalised per CLASS over the whole population rather than per cohort, because a class
    spans several behavioural cohorts - whales appear at the top of all four private ladders -
    and normalising inside one cohort makes the totals depend on how the cohorts were split.

    Weighted by rung so the small agents stand for more people than the large ones, which is
    what a heavy-tailed wealth distribution means when read as a crowd rather than as money.
    Reporting only: nothing downstream of this touches the simulation.
    """
    groups: dict[str, list] = {}
    for a in agents:
        if a.active:
            groups.setdefault(a.segment, []).append(a)
    for klass, members in groups.items():
        total = REPRESENTS.get(klass, len(members))
        weights = [a.size_rank + 1 for a in members]
        denominator = sum(weights) or 1
        # Largest-remainder apportionment, so the class totals are EXACT. Rounding each share
        # independently left market makers at 27 against a stated 25, and a headcount that
        # does not add up to what it claims is the kind of small lie a dashboard repeats.
        shares = [total * w / denominator for w in weights]
        floors = [max(1, int(x)) for x in shares]
        gap = total - sum(floors)
        order = sorted(range(len(members)), key=lambda i: shares[i] - int(shares[i]),
                       reverse=(gap > 0))
        for i in order[:abs(gap)]:
            floors[i] += 1 if gap > 0 else (-1 if floors[i] > 1 else 0)
        for a, n in zip(members, floors):
            a.represents = n


# --------------------------------------------------------------------------- affinity

def affinity_for(name: str, symbol: str, rank: int) -> bool:
    """Does this agent trade this asset? Deterministic, stateless, reproducible.

    Bitcoin is held by everybody. Everything else is held with a probability that falls with
    the asset turnover rank, so the long tail is traded by few participants - which is both
    true and the reason a fourteen-asset ledger costs far less than fourteen one-asset ones.
    """
    if rank == 0:
        return True
    p = max(0.12, 1.0 / (1.0 + 0.65 * rank))
    h = hashlib.blake2b(f"{name}|{symbol}".encode(), digest_size=4).digest()
    return int.from_bytes(h, "big") / 0xFFFFFFFF < p


def affinity_set(name: str, ranks: dict[str, int]) -> frozenset[str]:
    return frozenset(s for s, r in ranks.items() if affinity_for(name, s, r))


# --------------------------------------------------------------------------- population

def new_agent(cohort: str, rank: int, rungs: int, day: str, ranks: dict[str, int]) -> Agent:
    """One participant, born empty and born into a class."""
    name = f"{cohort}#{rank:03d}"
    return Agent(name=name, cohort=cohort, size_rank=rank, born=day,
                 segment=class_of(cohort, rank, rungs),
                 affinity=affinity_set(name, ranks))


def opening_population(day: str, ranks: dict[str, int],
                       scale: float = SCALE_MIN) -> list[Agent]:
    """The books on the first day of the record: every cohort at its opening size, all empty.

    Nothing is handed out here. Floats arrive when an asset lists and cash arrives when it is
    minted or ramped in, so every unit and every dollar traces back to a boundary event.
    """
    agents: list[Agent] = []
    for cohort in COHORT_SHARE:
        n = rungs_for(cohort, scale)
        for rank in range(n):
            agents.append(new_agent(cohort, rank, n, day, ranks))
    for cohort in (ISSUER, VENUE):
        agents.append(Agent(name=f"{cohort}#000", cohort=cohort, born=day, segment="venues"))
    assign_classes(agents)
    assign_represents(agents)
    return agents


def target_scale(addresses_now: float, addresses_base: float,
                 turnover_now: float = 0.0, turnover_base: float = 0.0) -> float:
    """The share of the agent budget the market carries today, in (0, 1].

    See `HEADCOUNT_BETA`: two observed series bracket a number nobody publishes, so the driver
    is the geometric mean of their growth factors raised to a sub-linear exponent.
    """
    factors = []
    if addresses_base > 0 and addresses_now > 0:
        factors.append(addresses_now / addresses_base)
    if turnover_base > 0 and turnover_now > 0:
        factors.append(turnover_now / turnover_base)
    if not factors:
        return SCALE_MIN
    geo = 1.0
    for f in factors:
        geo *= f
    geo **= 1.0 / len(factors)
    return max(SCALE_MIN, min(1.0, SCALE_MIN * geo ** HEADCOUNT_BETA))


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
