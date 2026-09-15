"""THE TICK - the loop the whole system is made of.

Seven steps, always in this order, and the order is the design:

    1 ADVANCE   the clock moves
    2 DELIVER   every event whose known_at has arrived reaches the agents who can see it
    3 PERCEIVE  each agent forms its own view - late, partial, its own
    4 DECIDE    policies emit intentions; nothing is applied yet
    5 CLEAR     markets find prices; the network decides what physically moves
    6 SETTLE    balances change, both sides at once, and CONSERVATION IS ASSERTED
    7 RECORD    the state and the reason for every decision are written down

Steps 3 and 4 are separate from 5 and 6 on purpose. Agents propose and the world disposes: an
agent that could write to the world directly would make a bug indistinguishable from a
decision, and the entire value of the agent architecture is that when reality diverges we can
ask WHICH PLAYER was wrong. That question dies the moment anyone is allowed to cheat.

WHY BARRELS THAT CANNOT SAIL ARE NOT DESTROYED
When a strait narrows, the crude that cannot pass and cannot be rerouted stays in the
producer's own tanks. It is stranded, not burnt. That is both physically true and the reason
the model can express the difference between a chokepoint closing and a field failing: in the
first case the barrels come back when the valve reopens, and the market knows it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .agents.base import Agent
from .agents.country import CentralBank, Country
from .markets import commodity
from .network import chokepoints as CP
from .state import WorldState, next_day


@dataclass
class TickReport:
    day: str
    tick: int
    prices: dict[str, float]
    supply: float = 0.0
    demand: float = 0.0
    stranded: float = 0.0
    cost_push: float = 0.0
    cover_days: float = 0.0
    notes: list[str] = field(default_factory=list)


def step(w: WorldState, agents: list[Agent], news: list[dict] | None = None,
         step_days: int = 1) -> TickReport:
    """One tick. Raises rather than returns if the world stops balancing."""
    before = w.totals()
    produced: dict[str, float] = {}
    news = news or []

    w.tick += 1
    w.day = next_day(w.day, step_days)
    w.journal.clear()
    CP.reset_bypass(w)

    # ---------------------------------------------------------------- 3 & 4: decide
    intents = []
    for a in agents:
        intents.extend(a.decide(a.observe(w, news), w))

    # ---------------------------------------------------------------- 5: supply side
    # Production first: barrels come out of the ground into the producer's own balance, and
    # the creation is DECLARED so the conservation check knows to expect it.
    for i in intents:
        if i.kind == "produce" and i.what == "crude":
            qty = i.qty * step_days
            w.balance(i.who).move("bbl", qty)
            produced["bbl"] = produced.get("bbl", 0.0) + qty

    # Then routing: how much of what each producer wants to sell can physically reach the
    # market, and what the detour costs for the part that had to go the long way.
    offers: list[tuple[str, float, float]] = []
    supply = stranded = weighted_cost = 0.0
    for i in intents:
        if i.kind != "sell" or i.what != "crude":
            continue
        want = min(i.qty * step_days, w.balance(i.who).units.get("bbl", 0.0))
        got, extra = CP.delivered(w, i.who, want)
        offers.append((i.who, got, extra))
        supply += got
        stranded += want - got
        weighted_cost += got * extra
    cost_push = (weighted_cost / supply) if supply > 0 else 0.0

    demand = sum(i.qty * step_days for i in intents
                 if i.kind == "buy" and i.what == "crude")

    price = commodity.clear(w, "crude", supply, demand, cost_push=cost_push)

    # ---------------------------------------------------------------- 6: settle
    mkt = "market.crude"
    for who, qty, _ in offers:
        w.transfer(who, mkt, "bbl", qty, price, why="lifting sold to market")

    # Buyers are served pro rata from what the market actually holds. Rationing is the
    # physical truth of a shortage and it is what makes the next tick's price move again.
    available = w.balance(mkt).units.get("bbl", 0.0)
    fill = min(1.0, available / demand) if demand > 0 else 0.0
    burnt = 0.0
    for i in intents:
        if i.kind != "buy" or i.what != "crude":
            continue
        qty = i.qty * step_days * fill
        w.transfer(mkt, i.who, "bbl", qty, price, why=i.why)
        # Consumption destroys the barrel, and the destruction is declared.
        w.balance(i.who).move("bbl", -qty)
        burnt += qty
        w.set_var(i.who, "oil_filled", qty)
    produced["bbl"] = produced.get("bbl", 0.0) - burnt

    w.markets["crude"].inventory = w.balance(mkt).units.get("bbl", 0.0)

    # ---------------------------------------------------------------- the chains
    for a in agents:
        if isinstance(a, Country):
            a.update_prices(w)
    for i in intents:
        if i.kind == "set":
            agent, _, name = i.what.rpartition(".")
            w.set_var(agent, name, i.qty)
            w.log(i.who, "set", name=name, value=i.qty, why=i.why)

    # ---------------------------------------------------------------- the law
    w.assert_conservation(before, produced)

    cover = (w.markets["crude"].inventory / demand) if demand > 0 else 0.0
    report = TickReport(day=w.day, tick=w.tick,
                        prices={k: m.price for k, m in w.markets.items()},
                        supply=supply, demand=demand, stranded=stranded,
                        cost_push=cost_push, cover_days=cover)
    if stranded > 0:
        report.notes.append(
            f"{stranded:,.2f} mb/d could not reach the market: a strait is narrowed and the "
            f"bypass is full. Those barrels are stranded in producers' tanks, not lost.")
    if fill < 1.0:
        report.notes.append(f"buyers rationed to {fill:.1%} of what they asked for")
    return report


def run(w: WorldState, agents: list[Agent], days: int,
        news_for=None, on_tick=None) -> list[TickReport]:
    out = []
    for _ in range(days):
        news = news_for(w.day) if news_for else []
        r = step(w, agents, news)
        out.append(r)
        if on_tick:
            on_tick(w, r)
    return out
