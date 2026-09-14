"""Who is who, in the words the operator actually uses.

The ledger's ten cohorts are BEHAVIOURAL - they answer "what makes this participant act". That
is the right axis for a model and the wrong axis for a person looking at a screen, who wants to
know how much the whales hold and how much the crowd has left to spend.

This module is the second axis, and it is a VIEW: it aggregates, it never decides. The class
itself is decided once, at birth, in `cohorts.class_of`.

SIX CLASSES, and they are different creatures rather than different sizes of one

  retail          private participants. The most numerous by a wide margin, exactly as in the
                  real market: one agent stands for about a hundred thousand people.
  whales          large private holders - the top slice of the private wealth ladder. Still
                  individuals, not firms.
  institutional   funded desks: the ETF allocator buying a billion dollars of Bitcoin, and the
                  basis-arbitrage fund. Few, and each one large.
  market_makers   the firms quoting both sides behind the venue. Fewer still - in reality a
                  handful of names, and that is what is modelled.
  miners          the only participants whose supply is a cost of production.
  venues          exchanges and stablecoin issuers: they hold the float and the faucet.

WHY THE CLASS IS INTRINSIC, AND THE TWO ATTEMPTS THAT FAILED

First attempt: an absolute net-worth line, a hundred million dollars. It produced a degenerate
report - 148 whales against 20 retail agents holding a tenth of one billion between them -
because an agent in this ledger is a representative bucket, not a household, so essentially
every bucket clears any line a person would not.

Second attempt: the richest tenth of private agents by net worth, re-ranked daily. Better, but
still wrong in kind: it says a whale is whoever happens to be rich today, when what the
operator described is a different sort of participant altogether.

What is modelled now: an agent is BORN a whale, a retail participant, a desk or a firm, and
the number of agents in each class follows the real market. The counts come out as retail >
whales > institutions > miners > market makers, which is the pyramid the way up it actually
stands.

HEADCOUNT IS REPORTED TWICE, and the difference matters. `players` counts AGENTS - the profile
groups the simulation actually carries. `represents` counts the real participants those groups
stand for. One is what was computed; the other is what it is a model of.
"""

from __future__ import annotations

from . import cohorts as C

#: Which definition produced an artefact. Stamped into the reconstruction cache, the trained
#: model and the phase 3 report, so a mismatch is visible rather than silent: the whale and
#: retail features change meaning when this changes, and a model trained under one definition
#: must not be scored under another.
SEGMENTATION = "born-class-v3"

MARKET_MAKERS = "market_makers"
INSTITUTIONAL = "institutional"
WHALES = "whales"
RETAIL = "retail"
MINERS = "miners"
VENUES = "venues"

ORDER = (WHALES, INSTITUTIONAL, RETAIL, MARKET_MAKERS, MINERS, VENUES)

LABELS = {
    WHALES: "Whales",
    INSTITUTIONAL: "Institutional",
    RETAIL: "Retail",
    MARKET_MAKERS: "Market makers",
    MINERS: "Miners",
    VENUES: "Exchanges & issuers",
}

DESCRIPTIONS = {
    WHALES: "Large private holders - the top of the private wealth ladder, still individuals",
    INSTITUTIONAL: "Funded desks - the ETF allocator and the basis-arbitrage fund",
    RETAIL: "The private crowd; one agent stands for about a hundred thousand people",
    MARKET_MAKERS: "The firms quoting both sides behind the venue; a handful of names",
    MINERS: "Structural sellers; supply is a cost of production",
    VENUES: "Exchanges and stablecoin issuers",
}

def classify(agent) -> str:
    """Which class this agent belongs to. Read off the agent; never re-derived from money."""
    return agent.segment or RETAIL


def snapshot(agents, prices: dict[str, float]) -> dict[str, dict]:
    """The six segments as of now: headcount, cash, asset value, and the sum of the two.

    `assets` is what they hold valued at today's price; `cash` is what they can still spend.
    `total` is the two together, which is the only number that compares a whale to a desk.
    """
    out = {k: {"players": 0, "represents": 0, "cash": 0.0, "assets": 0.0, "total": 0.0,
               "basis_cost": 0.0, "realized_pnl": 0.0, "coins": {}, "basis": {}}
           for k in ORDER}
    for a in agents:
        if not a.active:
            continue
        value = sum(q * prices.get(s, 0.0) for s, q in a.coins.items())
        seg = out[classify(a)]
        seg["players"] += 1
        seg["represents"] += a.represents
        seg["cash"] += a.cash
        seg["assets"] += value
        seg["basis_cost"] += sum(a.basis_cost.values())
        seg["realized_pnl"] += a.realized_pnl
        for s, q in a.coins.items():
            if q:
                seg["coins"][s] = seg["coins"].get(s, 0.0) + q
                # Basis kept PER SYMBOL as well as in total: "this segment is underwater in
                # Solana and in profit in Bitcoin" is a different fact from its net, and the
                # net is the one that hides a forced seller.
                seg["basis"][s] = seg["basis"].get(s, 0.0) + a.basis_cost.get(s, 0.0)
    for seg in out.values():
        seg["total"] = seg["cash"] + seg["assets"]
        seg["unrealized"] = seg["assets"] - seg["basis_cost"]
    return out


def market_cap(agents, prices: dict[str, float]) -> float:
    """Every unit the ledger carries, valued at the day's price.

    This is the capitalisation of the MODELLED sector - the fourteen assets of the
    laboratory's universe, each at its full circulating supply - and not of all of crypto.
    The distinction matters and the frontend says so on the chart.
    """
    held: dict[str, float] = {}
    for a in agents:
        for s, q in a.coins.items():
            held[s] = held.get(s, 0.0) + q
    return sum(q * prices.get(s, 0.0) for s, q in held.items())
