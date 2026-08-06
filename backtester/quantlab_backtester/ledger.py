"""The account ledger: what happened, as it happens.

The backtester owns this. Every order, every fill, every mark of the account is
recorded here in real time, keyed by the run that produced it. Nothing in this
module decides anything -- it is the book of record, not a strategy.

Three things live here.

`BacktestRun` gives a run an identity. Backtests are not singletons: a
contributor may launch dozens, and every trade, equity point and statistic has
to say which one it belongs to. The id is derived from what actually determines
the result -- the strategy, its parameters, the policy, the universe and the
window -- so the same configuration run twice produces the same id and can be
recognised as a repeat rather than filed as a new discovery.

`AccountLedger` is the live book: cash, open positions, equity, and an ordered
log of every fill. Until now the engine kept these as local variables and
emitted only completed round trips, which meant a half-finished run had no
record at all and no one could ask "what did it own on this date".

`AccountView` is the read-only projection handed to the trading system. A
strategy may consult the balance, what it already holds and how exposed it is,
and may not change any of it. That asymmetry is deliberate: decisions belong to
the trading system, the book belongs to the instrument, and a strategy that
could write to the ledger could rewrite its own results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable
import hashlib
import json


@dataclass(frozen=True)
class BacktestRun:
    """Identity for one backtest, and the inputs that determine its result."""

    backtest_id: str
    label: str
    created_at: str
    initial_capital: float
    strategy_family: str
    strategy_params: dict[str, Any]
    policy: dict[str, Any]
    universe_size: int
    window_start: str | None
    window_end: str | None

    @staticmethod
    def fingerprint(
        strategy_family: str,
        strategy_params: dict[str, Any],
        policy: dict[str, Any],
        universe: Iterable[str],
        window_start: str | None,
        window_end: str | None,
        initial_capital: float,
    ) -> str:
        """A stable id for a configuration.

        Deliberately derived rather than random. Two people running the same
        thing should collide, because that is information: it says the result is
        a reproduction, not a new finding. The universe enters as a sorted list
        of symbols, not a count -- this laboratory once selected a winner at 321
        assets and deployed it at 386, and the two runs would otherwise have
        looked identical.
        """

        def normalise(value):
            if isinstance(value, float) and value.is_integer():
                return int(value)
            if isinstance(value, dict):
                return {k: normalise(v) for k, v in sorted(value.items())}
            if isinstance(value, (list, tuple)):
                return [normalise(v) for v in value]
            return value

        payload = json.dumps(
            normalise(
                {
                    "strategy_family": strategy_family,
                    "strategy_params": strategy_params,
                    "policy": policy,
                    "universe": sorted(universe),
                    "window": [window_start, window_end],
                    "initial_capital": initial_capital,
                }
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def document(self) -> dict[str, Any]:
        return {
            "backtest_id": self.backtest_id,
            "label": self.label,
            "created_at": self.created_at,
            "initial_capital": self.initial_capital,
            "strategy_family": self.strategy_family,
            "strategy_params": self.strategy_params,
            "policy": self.policy,
            "universe_size": self.universe_size,
            "window_start": self.window_start,
            "window_end": self.window_end,
        }


@dataclass(frozen=True)
class Order:
    """One fill. Not an intention -- the engine records these after execution."""

    sequence: int
    timestamp: datetime
    symbol: str
    side: str  # BUY | SELL
    quantity: float
    price: float
    notional: float
    fee: float
    reason: str
    cash_after: float

    def document(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "notional": self.notional,
            "fee": self.fee,
            "reason": self.reason,
            "cash_after": self.cash_after,
        }


@dataclass
class Holding:
    symbol: str
    quantity: float
    entry_time: datetime
    entry_price: float
    invested: float


@dataclass
class AccountLedger:
    """The live book for one run. Written by the engine, read by everyone."""

    initial_capital: float
    cash: float = 0.0
    holdings: dict[str, Holding] = field(default_factory=dict)
    orders: list[Order] = field(default_factory=list)
    _marks: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.initial_capital <= 0:
            raise ValueError("a ledger needs positive initial capital")
        if not self.cash:
            self.cash = self.initial_capital

    # -- writes, engine only ------------------------------------------------ #

    def record_buy(
        self,
        stamp: datetime,
        symbol: str,
        quantity: float,
        price: float,
        notional: float,
        fee: float,
        reason: str = "ENTRY",
    ) -> Order:
        self.cash -= notional
        self.holdings[symbol] = Holding(symbol, quantity, stamp, price, notional)
        self._marks[symbol] = price
        return self._append(
            stamp, symbol, "BUY", quantity, price, notional, fee, reason
        )

    def record_sell(
        self,
        stamp: datetime,
        symbol: str,
        price: float,
        proceeds: float,
        fee: float,
        reason: str,
    ) -> Order:
        holding = self.holdings.pop(symbol)
        self.cash += proceeds - fee
        self._marks.pop(symbol, None)
        return self._append(
            stamp, symbol, "SELL", holding.quantity, price, proceeds, fee, reason
        )

    def _append(
        self,
        stamp: datetime,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        notional: float,
        fee: float,
        reason: str,
    ) -> Order:
        order = Order(
            sequence=len(self.orders) + 1,
            timestamp=stamp,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            notional=notional,
            fee=fee,
            reason=reason,
            cash_after=self.cash,
        )
        self.orders.append(order)
        return order

    def mark(self, symbol: str, price: float) -> None:
        """Latest observed price for an open holding, for marking to market."""
        if symbol in self.holdings:
            self._marks[symbol] = price

    # -- reads --------------------------------------------------------------- #

    @property
    def invested(self) -> float:
        return sum(
            holding.quantity * self._marks.get(holding.symbol, holding.entry_price)
            for holding in self.holdings.values()
        )

    @property
    def equity(self) -> float:
        return self.cash + self.invested

    @property
    def exposure(self) -> float:
        equity = self.equity
        return self.invested / equity if equity > 0 else 0.0

    def view(self) -> AccountView:
        return AccountView(self)


class AccountView:
    """Read-only window onto the ledger, handed to the trading system.

    Everything is a snapshot read from the live book, so a strategy asking for
    its balance mid-run gets the truth rather than a copy made at open. There is
    deliberately no setter of any kind: the trading system decides, the
    instrument records, and the two must not be the same object.
    """

    __slots__ = ("_ledger",)

    def __init__(self, ledger: AccountLedger) -> None:
        object.__setattr__(self, "_ledger", ledger)

    @property
    def cash(self) -> float:
        return self._ledger.cash

    @property
    def equity(self) -> float:
        return self._ledger.equity

    @property
    def invested(self) -> float:
        return self._ledger.invested

    @property
    def exposure(self) -> float:
        return self._ledger.exposure

    @property
    def initial_capital(self) -> float:
        return self._ledger.initial_capital

    @property
    def open_symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._ledger.holdings))

    def holds(self, symbol: str) -> bool:
        return symbol in self._ledger.holdings

    def position(self, symbol: str) -> Holding | None:
        holding = self._ledger.holdings.get(symbol)
        if holding is None:
            return None
        # A copy, so a strategy cannot mutate the live book through the handle
        # it was given to read it.
        return Holding(
            holding.symbol,
            holding.quantity,
            holding.entry_time,
            holding.entry_price,
            holding.invested,
        )

    def unrealised_pct(self, symbol: str) -> float:
        holding = self._ledger.holdings.get(symbol)
        if holding is None or not holding.entry_price:
            return 0.0
        mark = self._ledger._marks.get(symbol, holding.entry_price)
        return mark / holding.entry_price - 1

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(
            "AccountView is read-only: the trading system decides, the "
            "backtester records. Return a decision instead of writing the book."
        )
