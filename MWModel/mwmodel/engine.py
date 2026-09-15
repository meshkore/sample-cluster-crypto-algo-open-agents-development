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


#: How fast a fear premium fades when nothing further happens. Half-life of about three weeks:
#: the 2024 Red Sea episode is the reference - freight multiplied, crude barely moved, and the
#: premium was gone within a month. A premium that did not decay would turn every scare into a
#: permanent repricing, which is the opposite of what the record shows.
RISK_HALF_LIFE = 21


def _decay_risk(w: WorldState) -> None:
    r = w.var("__world", "risk_premium", 0.0)
    if abs(r) > 1e-6:
        w.set_var("__world", "risk_premium", r * (0.5 ** (1.0 / RISK_HALF_LIFE)))


def _apply_news(w: WorldState, agents: list, news: list[dict]) -> None:
    """Deliver the day's events and apply what each one does to the world.

    Four channels, applied by name. An event that names an effect the world does not have is
    an error in the chronicle rather than something to shrug at, so it is journalled loudly.
    """
    by_id = {a.id: a for a in agents}
    for item in news or []:
        effects = item.get("effects") or {}
        w.log("__news", "event", headline=item.get("headline", ""), why=item.get("day", ""))
        for key, value in effects.items():
            kind, _, target = key.partition(".")
            if key == "risk":
                w.set_var("__world", "risk_premium",
                          w.var("__world", "risk_premium", 0.0) + float(value))
            elif kind == "valve" and target in w.edges:
                CP.constrain(w, target, float(value), why=item.get("headline", ""))
            elif kind == "capacity":
                a = by_id.get(f"country.{target}")
                if a is not None:
                    a.params["oil_capacity"] = a.params.get("oil_capacity", 0.0) * float(value)
            elif kind == "discipline":
                a = by_id.get(f"country.{target}")
                if a is not None:
                    a.params["quota_discipline"] = float(value)
            elif kind == "demand":
                targets = ([a for a in agents if a.id.startswith(("country.", "region."))]
                           if target == "world" else [by_id.get(f"country.{target}")])
                for a in targets:
                    if a is None:
                        continue
                    w.set_var(a.id, "gdp_index", w.var(a.id, "gdp_index", 1.0) * float(value))
            else:
                w.log("__news", "unknown_effect", key=key, value=value,
                      why="the chronicle names something this world does not have")


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
    _apply_news(w, agents, news)
    _decay_risk(w)

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

    # The risk premium is a cost push that corresponds to no missing barrel. Keeping it in
    # the same channel as freight is deliberate: both raise what a buyer pays without changing
    # what a producer lifted, and the viewer can then say which of the two is doing the work.
    risk = w.var("__world", "risk_premium", 0.0)
    price = commodity.clear(w, "crude", supply, demand,
                            cost_push=cost_push + risk * w.markets["crude"].price)

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
