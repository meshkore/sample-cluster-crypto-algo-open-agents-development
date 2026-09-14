"""L0 - the ledger core. Double-entry, stock-flow consistent, conserved, and asserted.

The one idea in this file: **a trade changes no total.** It moves coins one way and cash
the other, and when it is finished the sector holds exactly as many coins and exactly as
many dollars as it did before. The operator's original framing was that buying two coins
for $100 puts $200 into the system; it does not, it moves $200 from a buyer to a seller,
and the distribution that results is the entire state variable this project is after.

Totals move only at the BOUNDARY, and the boundary is a short list:

    issue()     coins enter, paid to miners                     (supply schedule, observed)
    mint()      dollars enter as stablecoins                    (issuer float, observed)
    burn()      dollars leave as stablecoins are redeemed       (issuer float, observed)
    inject()    dollars enter from outside crypto entirely      (ETF creations, observed)

Everything else in this system is `settle()`, and `settle()` is conservative by
construction: it is handed a vector of coin deltas that sums to zero and it derives the
cash legs itself, so no caller can invent money by writing one side of a transfer.

WHY THE ASSERTIONS ARE IN THE HOT PATH RATHER THAN IN THE TESTS
An agent-based simulation with no conservation law is a random number generator with good
manners. A test that runs the invariant once at the end tells you that something broke; an
invariant asserted every step tells you WHICH step broke it, and with tens of thousands of
buckets that difference is the difference between a bug found in a minute and a week spent
reading a trajectory. `check()` is cheap - two sums over ~100 agents - and it runs on
every settlement.

Tolerances are RELATIVE, because the coin total is ~2e7 and the cash total is ~2e11 and a
fixed epsilon that is strict for one is meaningless for the other.
"""

from __future__ import annotations

from dataclasses import dataclass

REL_TOL = 1e-9          # float64 accumulated over ~1e4 settlements has room to spare
ABS_FLOOR = 1e-6        # below this, a residual is a rounding artefact, not a leak


class ConservationError(AssertionError):
    """Raised the moment the books stop balancing. Never caught inside this package."""


@dataclass(slots=True)
class Agent:
    """One representative participant: a cohort at one size bucket, or a boundary operator.

    `basis_cost` is the dollars paid for the coins currently held, carried at average cost.
    It is not bookkeeping decoration - "who is underwater, and by how much" is one of the
    four signals the whole architecture exists to produce, and it cannot be recovered later
    from a holdings series alone.
    """
    name: str
    cohort: str
    size_rank: int = 0
    coins: float = 0.0
    cash: float = 0.0
    basis_cost: float = 0.0
    realized_pnl: float = 0.0
    perp: float = 0.0                 # signed coin-equivalent perpetual position
    bought: float = 0.0               # lifetime coins bought, for turnover diagnostics
    sold: float = 0.0

    @property
    def avg_basis(self) -> float:
        return (self.basis_cost / self.coins) if self.coins > 1e-12 else 0.0

    def unrealized(self, price: float) -> float:
        return self.coins * price - self.basis_cost

    def profit_ratio(self, price: float) -> float:
        """(price / average cost) - 1. Zero when the agent holds nothing."""
        b = self.avg_basis
        return (price / b - 1.0) if b > 1e-12 else 0.0


class Ledger:
    """The books. Holds every agent, the two totals, and the invariants that bind them."""

    def __init__(self, agents: list[Agent], *, check_every: bool = True) -> None:
        self.agents = agents
        self.index = {a.name: i for i, a in enumerate(agents)}
        self.total_coins = sum(a.coins for a in agents)
        self.total_cash = sum(a.cash for a in agents)
        self.check_every = check_every
        self.fees_paid = 0.0
        self.steps = 0
        # Diagnostics a reconstruction must report rather than hide.
        self.shortfall_coins = 0.0    # sell flow the state could not supply
        self.shortfall_events = 0
        self.funding_unpaid = 0.0     # margin calls the levered cohort could not meet

    # ---------------------------------------------------------------- invariants
    def check(self, where: str = "") -> None:
        coins = sum(a.coins for a in self.agents)
        cash = sum(a.cash for a in self.agents)
        self._assert_close(coins, self.total_coins, "coins", where)
        self._assert_close(cash, self.total_cash, "cash", where)
        perp = sum(a.perp for a in self.agents)
        gross = sum(abs(a.perp) for a in self.agents)
        if abs(perp) > max(ABS_FLOOR, REL_TOL * gross):
            raise ConservationError(f"{where}: perpetual positions sum to {perp}, not zero")
        for a in self.agents:
            if a.coins < -ABS_FLOOR or a.cash < -ABS_FLOOR:
                raise ConservationError(
                    f"{where}: {a.name} holds coins={a.coins:.6f} cash={a.cash:.2f}; "
                    f"a negative stock is a short position the ledger never authorised")

    @staticmethod
    def _assert_close(got: float, want: float, what: str, where: str) -> None:
        tol = max(ABS_FLOOR, REL_TOL * max(abs(want), 1.0))
        if abs(got - want) > tol:
            raise ConservationError(
                f"{where}: total {what} is {got!r} but the boundary says {want!r} "
                f"(drift {got - want:+.6g}, tolerance {tol:.3g})")

    # ---------------------------------------------------------------- the boundary
    def issue(self, coins: float, to: str) -> None:
        """New coins enter the sector. The only event that raises the coin total.

        Issued coins arrive with a zero cash cost to the miner. Their true basis is the
        cost of production, which this MVP does not model and does not pretend to.
        """
        if coins < 0:
            raise ValueError("issuance is not negative")
        self.agents[self.index[to]].coins += coins
        self.total_coins += coins

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
    def settle(self, deltas: dict[str, float], price: float,
               fees: dict[str, float] | None = None, fee_to: str | None = None) -> None:
        """Apply one bucket's coin deltas and derive every cash leg from them.

        `deltas` must sum to zero - that is the accounting identity of a trade, stated as
        a precondition rather than hoped for. Cash moves at `price` against the coin leg,
        so cash is conserved automatically and cannot be conserved "approximately".

        Fees are a transfer to the venue, not a disappearance: the exchange cohort is
        inside the ledger precisely so that the dollars it takes stay inside the totals.
        """
        gross = sum(abs(v) for v in deltas.values())
        net = sum(deltas.values())
        if abs(net) > max(ABS_FLOOR, REL_TOL * gross):
            raise ConservationError(
                f"coin deltas sum to {net:+.6g}; a trade has two sides and they are equal")

        for name, dq in deltas.items():
            a = self.agents[self.index[name]]
            if dq >= 0:
                a.coins += dq
                a.basis_cost += dq * price
                a.cash -= dq * price
                a.bought += dq
            else:
                want = -dq
                q = min(want, a.coins)     # never sell coins that are not held
                basis = a.avg_basis
                a.coins -= q
                a.basis_cost -= q * basis
                a.realized_pnl += q * (price - basis)
                a.cash += q * price
                a.sold += q
                if q < want - ABS_FLOOR:
                    # The allocator asked for more than the state could supply. Record it
                    # loudly: it is the signal that the reconstruction is mis-specified,
                    # and a model that swallows it is telling a story. The coin total is
                    # adjusted so the books still balance and the damage stays visible.
                    self.shortfall_coins += want - q
                    self.shortfall_events += 1
                    self.total_coins -= (want - q)

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
            self.check(f"settle#{self.steps}")

    # ---------------------------------------------------------------- perpetuals
    def perp_settle(self, deltas: dict[str, float]) -> None:
        """Open interest changes hands. No coins move and no cash moves: perps are a bet."""
        gross = sum(abs(v) for v in deltas.values())
        net = sum(deltas.values())
        if abs(net) > max(ABS_FLOOR, REL_TOL * gross):
            raise ConservationError(f"perp deltas sum to {net:+.6g}; every long has a short")
        for name, dq in deltas.items():
            self.agents[self.index[name]].perp += dq

    def perp_funding(self, rate: float, price: float) -> None:
        """Longs pay shorts when the rate is positive. A pure cash transfer, sum zero.

        A payer with insufficient margin pays what it has. That is not a rounding
        convenience - it is the model's crudest stand-in for a liquidation, and the
        receipts are scaled to whatever was actually collected so the transfer still nets
        to zero. `funding_unpaid` counts the dollars leverage could not cover, which is the
        quantity a later phase turns into forced flow.
        """
        owed = {a.name: a.perp * price * rate for a in self.agents if a.perp != 0.0}
        payers = {k: v for k, v in owed.items() if v > 0}
        receivers = {k: -v for k, v in owed.items() if v < 0}
        collected = 0.0
        for name, amount in payers.items():
            a = self.agents[self.index[name]]
            pay = min(amount, max(0.0, a.cash))
            a.cash -= pay
            collected += pay
            self.funding_unpaid += amount - pay
        due = sum(receivers.values())
        if due > 0:
            for name, amount in receivers.items():
                self.agents[self.index[name]].cash += collected * amount / due

    # ---------------------------------------------------------------- reporting
    def by_cohort(self, price: float) -> dict[str, dict]:
        """The state the rest of the system consumes: stocks aggregated per cohort."""
        out: dict[str, dict] = {}
        for a in self.agents:
            d = out.setdefault(a.cohort, {
                "coins": 0.0, "cash": 0.0, "basis_cost": 0.0, "perp": 0.0,
                "realized_pnl": 0.0, "bought": 0.0, "sold": 0.0})
            d["coins"] += a.coins
            d["cash"] += a.cash
            d["basis_cost"] += a.basis_cost
            d["perp"] += a.perp
            d["realized_pnl"] += a.realized_pnl
            d["bought"] += a.bought
            d["sold"] += a.sold
        for d in out.values():
            d["avg_basis"] = (d["basis_cost"] / d["coins"]) if d["coins"] > 1e-12 else 0.0
            d["unrealized"] = d["coins"] * price - d["basis_cost"]
        return out
