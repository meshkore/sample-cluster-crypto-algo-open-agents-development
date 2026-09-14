"""The population: who the participants are, how big they are, and what makes them act.

Section 4 of the design document argued that headcount is not the design parameter - the
number of distinct BEHAVIOURAL TYPES is, and so is the size distribution within each type.
This module is that argument in code.

TEN TYPES, each distinct for a mechanical reason rather than a psychological one. Seven of
them trade; three of them are boundary operators and exist so that money can enter and
leave the sector at all.

THE SIZE LADDER. Within a type, wealth follows a heavy tail - one of the most robust facts
in crypto and in every other market anyone has looked at. Each trading type is therefore a
Zipf ladder of `LADDER` buckets rather than one average agent, and the reason is not
decoration: the tail agents are the ones that hit their cash floor last and their coin
floor never, so averaging them away destroys exactly the constraint dynamics the project
exists to capture. Seven types x thirteen rungs plus three boundary operators is 94 agents,
which is the O(100) the design specified for this phase.

THE PROPENSITY RULES are deliberately simple and deliberately NOT FITTED. They are the
Brock-Hommes family the design named as the published baseline: a small number of
interpretable rules whose failure is diagnosable. Every constant below is a prior taken
from the shape of the cohort, not a number calibrated against this laboratory's data, and
that matters for how the MVP's result must be read - a reconstruction that recovers a
held-out anchor with UNFITTED priors is evidence about the structure; one that recovers it
after fitting is evidence about the fitting.

What a rule returns is a DESIRE, not a trade. Desire is multiplied by the agent's capacity
(cash to buy with, coins to sell) and then normalised against the tape's actual volume in
`reconstruct.py`, because the tape - not the rule - decides how much changed hands.
"""

from __future__ import annotations

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
#: The levered cohort trades perpetuals only; it never touches the spot ledger, which is
#: why it is absent from TRADING and present in the perp book instead.
PERP_ONLY = (LEVERED,)

LADDER = 13          # rungs per trading type; see `size_weights`

#: How aggressively each type demands immediacy: the share of its flow that crosses the
#: spread. This is the parameter that decides whether a cohort shows up on the taker side
#: of the tape or the maker side, and it is the only place the taxonomy touches market
#: microstructure in this MVP.
TAKER_SHARE = {
    LTH: 0.15,             # patient; accumulates and distributes on limits
    MOMENTUM: 0.80,        # chases; pays the spread by definition
    DIP: 0.45,             # works orders into weakness but will reach when it is scared
    MAKER: 0.05,           # passive by definition; crosses only to manage inventory
    BASIS: 0.30,           # cares about carry, not about the next tick
    INSTITUTIONAL: 0.50,   # scheduled execution, half of it aggressive
    MINER: 0.20,           # sells into bids, rarely in a hurry
}

#: The fraction of its own book a cohort can turn over in ONE DAY, buying or selling.
#: This is the constraint that makes a holder a holder. Without it the allocator hands
#: flow to whoever has the most capacity, a long-term holder with sixty per cent of the
#: float becomes the market's largest day trader, and the taxonomy means nothing: the
#: cohorts would differ in what they want and not at all in how they behave. Market makers
#: sit above 1.0 because turning inventory over several times a day is their business.
TURNOVER_CAP = {
    LTH: 0.002,            # ~0.2% a day; a holder that sells 50% in a year is not one
    MOMENTUM: 0.15,
    DIP: 0.10,
    MAKER: 2.00,
    BASIS: 0.08,
    INSTITUTIONAL: 0.03,   # slow, calendar-driven, size-constrained
    MINER: 1.00,           # unused: miners are budgeted by issuance, not by stack
}

#: Miners sell what they mine. Net miner outflows track issuance closely over any window
#: longer than a few weeks, so the daily sell budget is a multiple of the coins issued
#: that day rather than a fraction of the stack they are sitting on.
MINER_SELL_BUDGET = 1.20

#: Opening distribution of the coin float. Priors, stated rather than fitted, and the
#: single largest source of level error in the MVP. Long-term holders absorb the dormant
#: and lost supply, which is why their share is so large; the venue holds its customers'
#: coins custodially rather than on its own book, so it opens with none.
COIN_PRIOR = {
    LTH: 0.60, MOMENTUM: 0.10, DIP: 0.08, MAKER: 0.05,
    BASIS: 0.05, INSTITUTIONAL: 0.06, MINER: 0.06,
}

#: Opening distribution of the cash float. Market makers and arbitrageurs carry dry powder
#: out of proportion to their coin holdings; holders carry almost none, which is what makes
#: them holders.
CASH_PRIOR = {
    LTH: 0.05, MOMENTUM: 0.18, DIP: 0.22, MAKER: 0.18,
    BASIS: 0.17, INSTITUTIONAL: 0.10, MINER: 0.00, LEVERED: 0.10,
}


# --------------------------------------------------------------------------- population

def size_weights(rungs: int = LADDER, alpha: float = 1.0) -> list[float]:
    """Zipf shares for one type's size ladder, largest first.

    `alpha = 1.0` is the plain Zipf law; it puts about a third of a cohort's wealth in its
    single largest agent and a long thin tail below, which is the shape both traditional
    and crypto wealth data keep producing.
    """
    raw = [1.0 / (k ** alpha) for k in range(1, rungs + 1)]
    total = sum(raw)
    return [r / total for r in raw]


def build_population(total_coins: float, total_cash: float, opening_price: float,
                     rungs: int = LADDER) -> list[Agent]:
    """The opening books: every agent, its rung, its coins and its cash.

    The two totals are handed in rather than assumed, because they are OBSERVED - the coin
    float from the chain, the cash float from the stablecoin supply - and an agent
    population that invented its own totals would break the ledger's only invariant before
    the first bucket.

    EVERY AGENT OPENS AT THE OPENING PRICE. Cost basis drives half the behavioural rules -
    who is in profit, who is underwater - and an opening basis of zero would make every
    cohort infinitely profitable on day one and silence those rules entirely. Opening at
    the current price is the one choice that asserts nothing: nobody starts in profit,
    nobody starts underwater, and the tape earns the distribution from there. It is also
    why the window opens years before the period being judged - the first years are
    burn-in, not result.
    """
    weights = size_weights(rungs)
    agents: list[Agent] = []
    for cohort in TRADING:
        for rank, w in enumerate(weights):
            agents.append(Agent(
                name=f"{cohort}#{rank:02d}", cohort=cohort, size_rank=rank,
                coins=total_coins * COIN_PRIOR[cohort] * w,
                basis_cost=total_coins * COIN_PRIOR[cohort] * w * opening_price,
                cash=total_cash * CASH_PRIOR[cohort] * w))
    for rank, w in enumerate(weights):
        agents.append(Agent(
            name=f"{MINER}#{rank:02d}", cohort=MINER, size_rank=rank,
            coins=total_coins * COIN_PRIOR[MINER] * w,
            basis_cost=total_coins * COIN_PRIOR[MINER] * w * opening_price, cash=0.0))
    for cohort in (ISSUER, VENUE):
        agents.append(Agent(name=f"{cohort}#00", cohort=cohort, size_rank=0))
    for rank, w in enumerate(weights):
        # The levered cohort holds no coins and trades no spot, but it must hold MARGIN:
        # a perpetual position that cannot pay its funding is not a model of leverage, it
        # is a hole in the ledger.
        agents.append(Agent(name=f"{LEVERED}#{rank:02d}", cohort=LEVERED, size_rank=rank,
                            cash=total_cash * CASH_PRIOR[LEVERED] * w))
    return agents


# --------------------------------------------------------------------------- market state

@dataclass(slots=True)
class MarketState:
    """Everything a propensity rule is allowed to see about the market.

    Deliberately short. A rule that needs more than this is a rule that is being fitted.
    """
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
    """(buy desire, sell desire) for one agent, both non-negative and unitless.

    `anchor_inventory` is the only piece of history a rule is given: the inventory a
    market maker is trying to revert to. It is held by the caller rather than on the agent
    because an agent is a balance sheet and a target is a belief.

    Each rule reads the market AND the agent's own book. Conditioning on own state is the
    detail that makes the population self-limiting: a cohort deep in profit distributes,
    a cohort out of cash cannot buy however much it wants to, and without that the agents
    buy forever and the model explodes. It is also why every rule below takes `agent`.
    """
    profit = agent.profit_ratio(m.price)

    if cohort == LTH:
        # Almost never sells; sells only on extreme unrealised profit. The buy side is a
        # small constant: holders accumulate regardless of the tape, which is the whole
        # content of the HODL-wave literature.
        return 0.15, _softplus(profit - 1.00, 0.35)

    if cohort == MOMENTUM:
        # Buys strength on two horizons, sells weakness on the fast one. No cash
        # discipline: the rule does not look at how much dry powder is left, which is
        # exactly why this cohort is the first to hit its capacity floor in a rally.
        return (max(0.0, m.r_slow) * 4.0 + max(0.0, m.r_fast) * 6.0,
                max(0.0, -m.r_fast) * 8.0 + max(0.0, -m.r_slow) * 2.0)

    if cohort == DIP:
        # Buys drawdown, with finite dry powder; takes profit early. The asymmetry
        # between the two thresholds is what makes this cohort a net supplier of
        # liquidity in panics and a net taker of it in rallies.
        return max(0.0, -m.drawdown) * 5.0, _softplus(profit - 0.25, 0.20)

    if cohort == MAKER:
        # Inventory-averse: wants to end the day flat against a target that is simply the
        # inventory it started the window with. Quotes both sides, so both desires are
        # live at once and the larger one wins.
        if anchor_inventory <= 0.0:
            return 0.5, 0.5
        gap = (anchor_inventory - agent.coins) / anchor_inventory
        return max(0.0, gap) * 3.0 + 0.3, max(0.0, -gap) * 3.0 + 0.3

    if cohort == BASIS:
        # Cares only about carry. Positive funding pays it to be long spot and short perp,
        # so the spot leg follows the sign of funding and nothing else.
        f = m.funding * 1000.0
        return max(0.0, f), max(0.0, -f)

    if cohort == INSTITUTIONAL:
        # Slow, calendar-driven, asymmetric: allocators are much quicker to add than to
        # cut. It reads only the glacial trend, which is what makes this cohort's inferred
        # flow a genuine prediction of the ETF series rather than a copy of it.
        return max(0.0, m.r_glacial) * 3.0 + 0.10, max(0.0, -m.r_glacial) * 1.5

    if cohort == MINER:
        # Structural seller: converts issuance to cash to pay for power and hardware.
        # Never a buyer. The one cohort whose flow is a cost of production rather than
        # an opinion about price.
        return 0.0, 1.0

    return 0.0, 0.0
