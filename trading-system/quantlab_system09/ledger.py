"""L0 - the ledger core. Double-entry, stock-flow consistent, conserved, and asserted.

The one idea in this file: **a trade changes no total.** It moves units one way and cash
the other, and when it is finished the sector holds exactly as many units and exactly as
many dollars as it did before. The operator's original framing was that buying two coins
for $100 puts $200 into the system; it does not, it moves $200 from a buyer to a seller,
and the distribution that results is the entire state variable this project is after.

Totals move only at the BOUNDARY, and the boundary is a short list:

    issue()     units enter, paid to miners                     (supply schedule, observed)
    mint()      dollars enter as stablecoins                    (issuer float, observed)
    burn()      dollars leave as stablecoins are redeemed       (issuer float, observed)
    inject()    dollars enter from outside crypto entirely      (ETF creations, observed)

Everything else is `settle()`, and `settle()` is conservative by construction: it is handed
a vector of unit deltas that sums to zero and it derives the cash legs itself, so no caller
can invent money by writing one side of a transfer.

MANY ASSETS, ONE WALLET. An agent holds a book of coins per symbol and a SINGLE cash
balance shared across all of them. That is not a convenience, it is the point: dry powder
spent on one asset is not available for another, and modelling each pair with its own
private pile of dollars - which is what the first version of this system did for BTC alone -
invents liquidity that the sector does not have. Competition for one shared cash pool is
most of what "managing the liquidity of the crypto ecosystem" means.

WHY THE ASSERTIONS ARE IN THE HOT PATH RATHER THAN IN THE TESTS
An agent-based simulation with no conservation law is a random number generator with good
manners. A test that runs the invariant once at the end tells you that something broke; an
invariant asserted every step tells you WHICH step broke it. `check()` is cheap and it runs
on every settlement while `check_every` is on.

Tolerances are RELATIVE, because a coin total is ~2e7 and the cash total is ~2e11 and a
fixed epsilon that is strict for one is meaningless for the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field

REL_TOL = 1e-9          # float64 accumulated over ~1e5 settlements has room to spare
ABS_FLOOR = 1e-6        # below this, a residual is a rounding artefact, not a leak


class ConservationError(AssertionError):
    """Raised the moment the books stop balancing. Never caught inside this package."""


@dataclass(slots=True)
class Agent:
    """One representative participant: a cohort at one size rung, or a boundary operator.

    `basis_cost` is the dollars paid for the units currently held, per symbol, at average
    cost. It is not bookkeeping decoration - "who is underwater, and by how much" is one of
    the four signals the whole architecture exists to produce, and it cannot be recovered
    later from a holdings series alone.

    `affinity` is the set of symbols this agent trades. The operator's own observation:
    nobody trades fifty coins at once. It is both realistic and an enormous saving.

    `born` and `retired` carry the population dynamics. An agent that does not exist yet
    holds nothing and is skipped; one that has retired has already had its book handed to
    its cohort, so it holds nothing either. Neither can break conservation by construction.
    """
    name: str
    cohort: str
    size_rank: int = 0
    coins: dict[str, float] = field(default_factory=dict)
    basis_cost: dict[str, float] = field(default_factory=dict)
    cash: float = 0.0
    realized_pnl: float = 0.0
    perp: dict[str, float] = field(default_factory=dict)
    affinity: frozenset[str] = frozenset()
    born: str = ""                    # UTC date this agent entered the market
    retired: str = ""                 # UTC date it left, empty while active
    bought: float = 0.0               # lifetime dollars bought, for turnover diagnostics
    sold: float = 0.0

    @property
    def active(self) -> bool:
        return not self.retired

    def held(self, symbol: str) -> float:
        return self.coins.get(symbol, 0.0)

    def avg_basis(self, symbol: str) -> float:
        q = self.coins.get(symbol, 0.0)
        return (self.basis_cost.get(symbol, 0.0) / q) if q > 1e-12 else 0.0

    def profit_ratio(self, symbol: str, price: float) -> float:
        """(price / average cost) - 1 for one symbol. Zero when nothing is held."""
        b = self.avg_basis(symbol)
        return (price / b - 1.0) if b > 1e-12 else 0.0

    def unrealized(self, prices: dict[str, float]) -> float:
        return sum(q * prices.get(s, 0.0) - self.basis_cost.get(s, 0.0)
                   for s, q in self.coins.items())


class Ledger:
    """The books. Holds every agent, the totals, and the invariants that bind them."""

    def __init__(self, agents: list[Agent], *, check_every: bool = True) -> None:
        self.agents = agents
        self.index = {a.name: i for i, a in enumerate(agents)}
        self.total_coins: dict[str, float] = {}
        for a in agents:
            for s, q in a.coins.items():
                self.total_coins[s] = self.total_coins.get(s, 0.0) + q
        self.total_cash = sum(a.cash for a in agents)
        self.check_every = check_every
        self.fees_paid = 0.0
        self.steps = 0
        # Diagnostics a reconstruction must report rather than hide.
        self.shortfall_coins = 0.0    # sell flow the state could not supply
        self.shortfall_events = 0
        self.funding_unpaid = 0.0     # margin calls leverage could not meet

    # ---------------------------------------------------------------- population
    def add(self, agent: Agent) -> None:
        """Admit a new participant. Its opening stocks join the totals, so a caller that
        hands it coins or cash out of nowhere is making a boundary claim and must say so."""
        if agent.name in self.index:
            raise ValueError(f"{agent.name} is already on the books")
        self.index[agent.name] = len(self.agents)
        self.agents.append(agent)
        for s, q in agent.coins.items():
            self.total_coins[s] = self.total_coins.get(s, 0.0) + q
        self.total_cash += agent.cash

    def amalgamate(self, leaving: str, into: str, day: str) -> None:
        """Retire one agent into another. Conserves everything: this is a merger, not an
        exit from the market.

        A participant that stops trading has not destroyed its coins - somebody holds them.
        Modelling departure as deletion would leak the sector's float a little at a time,
        and the invariant would catch it, which is the whole reason this is written as a
        transfer instead.
        """
        a, b = self.agents[self.index[leaving]], self.agents[self.index[into]]
        for s, q in a.coins.items():
            b.coins[s] = b.coins.get(s, 0.0) + q
            b.basis_cost[s] = b.basis_cost.get(s, 0.0) + a.basis_cost.get(s, 0.0)
        for s, q in a.perp.items():
            b.perp[s] = b.perp.get(s, 0.0) + q
        b.cash += a.cash
        b.realized_pnl += a.realized_pnl
        a.coins, a.basis_cost, a.perp = {}, {}, {}
        a.cash = 0.0
        a.retired = day

    # ---------------------------------------------------------------- invariants
    def check(self, where: str = "") -> None:
        for sym, want in self.total_coins.items():
            got = sum(a.coins.get(sym, 0.0) for a in self.agents)
            self._assert_close(got, want, f"{sym} units", where)
        cash = sum(a.cash for a in self.agents)
        self._assert_close(cash, self.total_cash, "cash", where)
        syms = {s for a in self.agents for s in a.perp}
        for sym in syms:
            net = sum(a.perp.get(sym, 0.0) for a in self.agents)
            gross = sum(abs(a.perp.get(sym, 0.0)) for a in self.agents)
            if abs(net) > max(ABS_FLOOR, REL_TOL * gross):
                raise ConservationError(
                    f"{where}: {sym} perpetual positions sum to {net}, not zero")
        for a in self.agents:
            if a.cash < -ABS_FLOOR or any(q < -ABS_FLOOR for q in a.coins.values()):
                raise ConservationError(
                    f"{where}: {a.name} holds cash={a.cash:.2f} coins={a.coins}; "
                    f"a negative stock is a short position the ledger never authorised")

    @staticmethod
    def _assert_close(got: float, want: float, what: str, where: str) -> None:
        tol = max(ABS_FLOOR, REL_TOL * max(abs(want), 1.0))
        if abs(got - want) > tol:
            raise ConservationError(
                f"{where}: total {what} is {got!r} but the boundary says {want!r} "
                f"(drift {got - want:+.6g}, tolerance {tol:.3g})")

    # ---------------------------------------------------------------- the boundary
    def issue(self, symbol: str, coins: float, to: str) -> None:
        """New units enter the sector. The only event that raises a unit total.

        Issued units arrive with a zero cash cost to the miner. Their true basis is the
        cost of production, which this system does not model and does not pretend to.
        """
        if coins < 0:
            raise ValueError("issuance is not negative")
        a = self.agents[self.index[to]]
        a.coins[symbol] = a.coins.get(symbol, 0.0) + coins
        self.total_coins[symbol] = self.total_coins.get(symbol, 0.0) + coins

    def mint(self, usd: float, to: str) -> None:
        """Dollars enter the sector as newly issued stablecoins."""
        self.agents[self.index[to]].cash += usd
        self.total_cash += usd

    def burn(self, usd: float, frm: str) -> float:
        """Dollars leave as stablecoins are redeemed. Returns what was actually burned.

        Capped by the holder's balance: a redemption cannot take dollars that are not
        there, and silently allowing a negative balance would destroy the one invariant
        that makes this model checkable.
        """
        a = self.agents[self.index[frm]]
        usd = min(usd, max(0.0, a.cash))
        a.cash -= usd
        self.total_cash -= usd
        return usd

    def inject(self, usd: float, to: str) -> None:
        """Dollars enter from outside crypto altogether - an ETF creation, a fiat deposit."""
        self.agents[self.index[to]].cash += usd
        self.total_cash += usd

    def withdraw(self, usd: float, frm: str) -> float:
        """Dollars leave crypto altogether - an ETF redemption, a fiat withdrawal."""
        return self.burn(usd, frm)

    # ---------------------------------------------------------------- the inside
    def settle(self, symbol: str, deltas: dict[str, float], price: float,
               fees: dict[str, float] | None = None, fee_to: str | None = None) -> None:
        """Apply one bucket's unit deltas for one symbol and derive every cash leg.

        `deltas` must sum to zero - the accounting identity of a trade, stated as a
        precondition rather than hoped for. Cash moves at `price` against the unit leg, so
        cash is conserved automatically and cannot be conserved "approximately".

        Fees are a transfer to the venue, not a disappearance: the exchange cohort is
        inside the ledger precisely so that the dollars it takes stay inside the totals.
        """
        gross = sum(abs(v) for v in deltas.values())
        net = sum(deltas.values())
        if abs(net) > max(ABS_FLOOR, REL_TOL * gross):
            raise ConservationError(
                f"{symbol}: unit deltas sum to {net:+.6g}; a trade has two sides")

        for name, dq in deltas.items():
            a = self.agents[self.index[name]]
            if dq >= 0:
                a.coins[symbol] = a.coins.get(symbol, 0.0) + dq
                a.basis_cost[symbol] = a.basis_cost.get(symbol, 0.0) + dq * price
                a.cash -= dq * price
                a.bought += dq * price
            else:
                want = -dq
                have = a.coins.get(symbol, 0.0)
                q = min(want, have)
                basis = a.avg_basis(symbol)
                a.coins[symbol] = have - q
                a.basis_cost[symbol] = a.basis_cost.get(symbol, 0.0) - q * basis
                a.realized_pnl += q * (price - basis)
                a.cash += q * price
                a.sold += q * price
                if q < want - ABS_FLOOR:
                    # The allocator asked for more than the state could supply. Record it
                    # loudly: it is the signal that the reconstruction is mis-specified,
                    # and a model that swallows it is telling a story.
                    self.shortfall_coins += want - q
                    self.shortfall_events += 1
                    self.total_coins[symbol] -= (want - q)

        if fees:
            if fee_to is None:
                raise ValueError("fees must be paid to somebody; the venue is an agent")
            venue = self.agents[self.index[fee_to]]
            for name, usd in fees.items():
                a = self.agents[self.index[name]]
                usd = min(usd, max(0.0, a.cash))
                a.cash -= usd
                venue.cash += usd
                self.fees_paid += usd

        self.steps += 1
        if self.check_every:
            self.check(f"settle#{self.steps} {symbol}")

    # ---------------------------------------------------------------- perpetuals
    def perp_settle(self, symbol: str, deltas: dict[str, float]) -> None:
        """Open interest changes hands. No units move and no cash moves: perps are a bet."""
        gross = sum(abs(v) for v in deltas.values())
        net = sum(deltas.values())
        if abs(net) > max(ABS_FLOOR, REL_TOL * gross):
            raise ConservationError(f"{symbol}: perp deltas sum to {net:+.6g}")
        for name, dq in deltas.items():
            a = self.agents[self.index[name]]
            a.perp[symbol] = a.perp.get(symbol, 0.0) + dq

    def perp_funding(self, symbol: str, rate: float, price: float) -> None:
        """Longs pay shorts when the rate is positive. A pure cash transfer, sum zero.

        A payer with insufficient margin pays what it has. That is not a rounding
        convenience - it is the model's crudest stand-in for a liquidation, and the
        receipts are scaled to whatever was actually collected so the transfer still nets
        to zero. `funding_unpaid` counts the dollars leverage could not cover.
        """
        owed = {a.name: a.perp.get(symbol, 0.0) * price * rate
                for a in self.agents if a.perp.get(symbol, 0.0) != 0.0}
        collected = 0.0
        for name, amount in owed.items():
            if amount <= 0:
                continue
            a = self.agents[self.index[name]]
            pay = min(amount, max(0.0, a.cash))
            a.cash -= pay
            collected += pay
            self.funding_unpaid += amount - pay
        due = -sum(v for v in owed.values() if v < 0)
        if due > 0:
            for name, amount in owed.items():
                if amount < 0:
                    self.agents[self.index[name]].cash += collected * (-amount) / due

    # ---------------------------------------------------------------- reporting
    def by_cohort(self, prices: dict[str, float]) -> dict[str, dict]:
        """The state the rest of the system consumes: stocks aggregated per cohort."""
        out: dict[str, dict] = {}
        for a in self.agents:
            d = out.setdefault(a.cohort, {
                "value": 0.0, "cash": 0.0, "basis_cost": 0.0, "perp": 0.0,
                "realized_pnl": 0.0, "headcount": 0, "coins": {}})
            for s, q in a.coins.items():
                d["coins"][s] = d["coins"].get(s, 0.0) + q
                d["value"] += q * prices.get(s, 0.0)
                d["basis_cost"] += a.basis_cost.get(s, 0.0)
            d["cash"] += a.cash
            d["perp"] += sum(a.perp.values())
            d["realized_pnl"] += a.realized_pnl
            d["headcount"] += 1 if a.active else 0
        for d in out.values():
            d["unrealized"] = d["value"] - d["basis_cost"]
        return out
