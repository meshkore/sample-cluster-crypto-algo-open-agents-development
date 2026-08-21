"""The module contract: what every decision module sees, and what it returns.

A module is a small, independent judge. It never touches the account, never
computes a fill, never decides to stop the run — those belong to the
orchestrator and the mandate. It looks at the bar the orchestrator assembled and
returns opinions: for each symbol it cares about, how much it wants to be long it
(`conviction`), whether it forbids being long it (`veto`), and how it would scale
the size (`size_mult`); and optionally a book-wide deployment suggestion.

Keeping the surface this small is what lets the modules run independently, be
unit-tested one at a time, be turned off (abstain → the orchestrator behaves as
if the module were never there), and — later — be gathered concurrently when one
of them needs a live network call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from ..channels import Channels


@dataclass
class MarketView:
    """Everything a module needs to judge one bar, assembled once by the orchestrator.

    Assembling it once and sharing it is the point: no module re-derives the
    timestamp, the held set, or reopens the channel table.
    """

    timestamp: datetime
    ns: int  # epoch-ns key into the precomputed channels, matching infer._epoch_ns
    candles: dict[str, dict[str, Any]]  # symbol -> latest closed bar
    account: dict[str, Any]  # cash, equity, initial_capital, positions
    channels: Channels  # precomputed causal lookups (prob/trend/vol/mom/…)
    held: set[str]  # symbols currently held, for convenience
    peaks: dict[str, float]  # per-holding high-water price, kept by the orchestrator
    #                          (bookkeeping, not a decision) so a trailing-stop module
    #                          reads the same peak the book seeded at entry.

    @property
    def equity(self) -> float:
        return float(self.account.get("equity", 0.0))

    def price(self, symbol: str) -> float:
        bar = self.candles.get(symbol) or {}
        return float(bar.get("close") or 0.0)


@dataclass
class SymbolVote:
    """One module's opinion on one symbol.

    conviction: 0..1 desire to be long (0 = no opinion / abstain on direction).
    veto:       hard block on ENTERING this symbol this bar (risk-off, meta refusal,
                trend down). A veto never force-exits a held name — that is an exit
                rule the orchestrator owns — it only keeps the name out of the book.
    size_mult:  multiplicative scale on this symbol's notional (vol-target,
                microstructure). 1.0 = neutral. Multipliers from different modules
                compose by product.
    """

    conviction: float = 0.0
    veto: bool = False
    size_mult: float = 1.0
    # An exit demand on a HELD name (stop, trailing stop, regime risk-off). Unlike a
    # veto (which only keeps a name out of the book), an exit closes a position and
    # fires immediately, ignoring `min_hold` — capital preservation outranks patience.
    # `exit_reason` orders competing demands: the orchestrator keeps EXIT_PRIORITY.
    exit_now: bool = False
    exit_reason: str = ""
    exit_rationale: str = ""


@dataclass
class ModuleOutput:
    """What a module returns for one bar.

    votes:  sparse map symbol -> SymbolVote. A symbol absent from the map means
            the module abstains on it (no conviction, no veto, no scaling).
    deploy: optional book-wide fraction of equity this module thinks should be at
            work (regime / money management). None = no opinion. The orchestrator
            reconciles the deploy suggestions into one fraction.
    note:   short human-readable trace, surfaced on the Decision.
    """

    votes: dict[str, SymbolVote] = field(default_factory=dict)
    deploy: float | None = None
    note: str = ""

    def vote(self, symbol: str, conviction: float = 0.0, veto: bool = False,
             size_mult: float = 1.0) -> "ModuleOutput":
        self.votes[symbol] = SymbolVote(conviction, veto, size_mult)
        return self

    def demand_exit(self, symbol: str, reason: str, rationale: str = "") -> "ModuleOutput":
        """Close a held position (stop / risk-off). Merges with any existing vote."""
        vote = self.votes.setdefault(symbol, SymbolVote())
        vote.exit_now = True
        vote.exit_reason = reason
        vote.exit_rationale = rationale
        return self


@runtime_checkable
class Module(Protocol):
    """The entire contribution surface of a decision module.

    `name` identifies it (in cards, dashboards, logs). `weight` scales its
    conviction in the orchestrator's weighted vote (0 = off but still able to
    veto; set the module out of the list entirely to silence it completely).
    `reset()` clears per-run state so each independent calendar-year account
    starts clean, exactly like the brain's own reset.
    """

    name: str
    weight: float

    def evaluate(self, view: MarketView) -> ModuleOutput: ...

    def reset(self) -> None: ...
