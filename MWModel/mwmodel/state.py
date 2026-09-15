"""THE WORLD STATE, and the law that keeps it honest.

Everything the simulation knows at one instant: who exists, what they own, what things cost,
and what the physical network can currently carry. One object, passed to every agent, never
mutated by them - agents emit INTENTIONS and the engine applies them, because a model where
anyone can write to the world is a model where a bug is indistinguishable from a decision.

LAW 1, CONSERVATION, LIVES HERE. Money and physical units balance, and `assert_conservation`
is called in the hot path rather than in a test. System 09 proved the value of that: its
double-entry ledger asserted to 1e-14 on every step and caught more real errors than the whole
suite around it. A simulation that can quietly create a barrel or a dollar will eventually
produce a beautiful, meaningless result.

WHAT IS DELIBERATELY NOT HERE
No forecasting, no policy, no cleverness. This module is a container and an invariant. Every
opinion about how the world behaves belongs to an agent, and every opinion about how a price
is found belongs to a market.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


class ConservationError(RuntimeError):
    """Raised when units or money stop balancing. Stops the tick; never logged and continued."""


@dataclass
class Balance:
    """What one agent owns. Money in USD, everything else in its own physical unit.

    `units` is deliberately open: barrels, cubic metres, tonnes, chips, coins. The engine does
    not care what a unit is, only that the total of each kind is unchanged by a transfer.
    """

    cash: float = 0.0                                   # USD
    debt: float = 0.0                                   # USD owed
    units: dict[str, float] = field(default_factory=dict)

    def net_worth(self, prices: dict[str, float]) -> float:
        return self.cash - self.debt + sum(
            q * prices.get(k, 0.0) for k, q in self.units.items())

    def move(self, kind: str, qty: float) -> None:
        self.units[kind] = self.units.get(kind, 0.0) + qty


@dataclass
class Market:
    """One thing that has a price, and the book that found it.

    `price` is where the last clearing left it. `supply` and `demand` are the quantities
    agents actually offered and wanted on this tick, kept so that the viewer can show WHY a
    price moved rather than only that it did.
    """

    key: str
    unit: str
    price: float
    supply: float = 0.0
    demand: float = 0.0
    inventory: float = 0.0
    history: list[tuple[str, float]] = field(default_factory=list)

    @property
    def imbalance(self) -> float:
        """Positive when the world wants more than it is being offered."""
        return self.demand - self.supply


@dataclass
class Edge:
    """A physical route between two places, with a capacity that can be constrained.

    A blockade is not a special case in this design - it is a capacity that has fallen, and
    the rerouting that follows is the ordinary behaviour of a shipper choosing the cheapest
    route that still has room. That is the whole point of modelling the network rather than
    modelling "a shock".
    """

    key: str
    frm: str
    to: str
    capacity: float               # units per day at full flow
    base_capacity: float
    days: float                   # transit time
    cost: float                   # USD per unit
    flow: float = 0.0
    note: str = ""

    @property
    def open_fraction(self) -> float:
        return self.capacity / self.base_capacity if self.base_capacity else 0.0


@dataclass
class WorldState:
    """The whole world at one instant."""

    day: str
    tick: int = 0
    balances: dict[str, Balance] = field(default_factory=dict)
    markets: dict[str, Market] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)
    #: Per-agent scalar state that is not a balance: a CPI index, a GDP index, a policy rate,
    #: a utilisation, a memory of how badly the last decision went.
    vars: dict[str, dict[str, float]] = field(default_factory=dict)
    #: Everything that happened on this tick, with the reason. The viewer's "why" panel and
    #: the attribution step both read this, so it is written even when nothing is watching.
    journal: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------------ accessors
    def var(self, agent: str, name: str, default: float = 0.0) -> float:
        return self.vars.get(agent, {}).get(name, default)

    def set_var(self, agent: str, name: str, value: float) -> None:
        self.vars.setdefault(agent, {})[name] = float(value)

    def price(self, market: str) -> float:
        m = self.markets.get(market)
        return m.price if m else 0.0

    def balance(self, agent: str) -> Balance:
        return self.balances.setdefault(agent, Balance())

    def log(self, who: str, what: str, **detail) -> None:
        self.journal.append({"tick": self.tick, "day": self.day, "who": who,
                             "what": what, **detail})

    # ------------------------------------------------------------------ the law
    def totals(self) -> dict[str, float]:
        """Every unit kind summed across every balance, plus money. The conserved quantities."""
        out: dict[str, float] = {"__cash": 0.0, "__debt": 0.0}
        for b in self.balances.values():
            out["__cash"] += b.cash
            out["__debt"] += b.debt
            for k, q in b.units.items():
                out[k] = out.get(k, 0.0) + q
        # A market's inventory is NOT added here: it is held in a real balance under
        # `market.<key>`, so that a barrel sitting in storage is owned by somebody and cannot
        # be double counted. `Market.inventory` is a mirror the clearing logic reads.
        return out

    def assert_conservation(self, before: dict[str, float],
                            produced: dict[str, float] | None = None,
                            tolerance: float = 1e-6) -> None:
        """Nothing appeared and nothing vanished, except what was explicitly produced.

        `produced` is how real creation and destruction enter the model - a barrel lifted out
        of the ground, a barrel burnt, money printed by a central bank. Every one of those is
        an explicit, named, journalled act. Anything else that changes a total is a bug, and
        this raises rather than logs, because a conservation violation invalidates every
        number computed after it.
        """
        after = self.totals()
        produced = produced or {}
        for kind in set(before) | set(after):
            expected = before.get(kind, 0.0) + produced.get(kind, 0.0)
            actual = after.get(kind, 0.0)
            scale = max(1.0, abs(expected))
            if abs(actual - expected) / scale > tolerance:
                raise ConservationError(
                    f"tick {self.tick} ({self.day}): {kind} does not balance. "
                    f"expected {expected:,.6f}, found {actual:,.6f}, "
                    f"difference {actual - expected:,.6f}. "
                    "Every creation or destruction must be declared in `produced`.")

    # ------------------------------------------------------------------ transfers
    def transfer(self, frm: str, to: str, kind: str, qty: float, price: float,
                 why: str = "") -> None:
        """One trade, both sides, always. The only way units and money change hands.

        There is no single-sided version of this function and there never will be. Every
        purchase is someone's sale; that is not an accounting convention, it is what makes the
        simulation a closed system that can be checked.
        """
        if qty <= 0:
            return
        value = qty * price
        self.balance(frm).move(kind, -qty)
        self.balance(to).move(kind, qty)
        self.balance(to).cash -= value
        self.balance(frm).cash += value
        self.log(to, "buy", frm=frm, kind=kind, qty=qty, price=price, value=value, why=why)


def next_day(day: str, step_days: int = 1) -> str:
    return (date.fromisoformat(day[:10]) + timedelta(days=step_days)).isoformat()
