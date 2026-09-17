"""The live book: cash, open positions, every fill, and what the account is worth.

This is the one piece the backtester cannot lend us. Its ledger owns a *replay* - it
knows the whole timeline in advance and can be rebuilt from it at any time. A live book
is the opposite: it is the only record that the trade happened, it has to survive a
restart, a power cut and an engine upgrade, and it can never be recomputed from anything.

So the rules here are deliberately boring:

* **Every state change goes to disk before it is acknowledged.** `apply_fill` writes the
  fill to the ledger and then saves the book; a crash between the two leaves a ledger
  line whose effect is missing, which `rebuild()` detects and replays, rather than a
  position nobody can explain.
* **The account payload is byte-compatible with the backtester's.** The brain reads
  `tick["account"]` and does not know or care which side of the glass it is on. Any drift
  in this shape would be a strategy change disguised as plumbing.
* **Marks are separate from cost.** `invested` is quantity x LAST PRICE, exactly as the
  backtester defines it, so equity moves with the market between trades.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config


@dataclass
class Position:
    symbol: str
    quantity: float
    entry_time: datetime
    entry_price: float
    invested_cost: float          # what it cost to open, fees included

    def to_json(self) -> dict[str, Any]:
        row = asdict(self)
        row["entry_time"] = self.entry_time.isoformat()
        return row

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "Position":
        return cls(symbol=row["symbol"], quantity=float(row["quantity"]),
                   entry_time=datetime.fromisoformat(row["entry_time"]),
                   entry_price=float(row["entry_price"]),
                   invested_cost=float(row["invested_cost"]))


@dataclass
class Fill:
    at: datetime
    symbol: str
    side: str                     # BUY | SELL
    quantity: float
    price: float                  # the price actually paid or received, spread included
    notional: float
    fee: float
    reason: str = ""
    engine: str = ""
    realised: float | None = None  # filled in on the closing side of a round trip
    mid_at_decision: float | None = None
    slippage_bps: float | None = None

    def to_json(self) -> dict[str, Any]:
        row = asdict(self)
        row["at"] = self.at.isoformat()
        return row


@dataclass
class LiveBook:
    """One account. Long only, no leverage - the mandate the whole lab measured."""

    initial_capital: float = config.INITIAL_CAPITAL
    cash: float = config.INITIAL_CAPITAL
    positions: dict[str, Position] = field(default_factory=dict)
    realised: float = 0.0
    fees_paid: float = 0.0
    trades_closed: int = 0
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    high_water: float = 0.0
    _marks: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # The peak starts at the capital that actually opened THIS book. Defaulting it to
        # the standard $100,000 made a smaller account report a drawdown from a peak it
        # had never reached - a book opened with $10,000 would have shown -90% before its
        # first trade. Caught by the test, never by the market.
        self.high_water = max(self.high_water, self.initial_capital)

    # -- valuation -------------------------------------------------------------

    def mark(self, prices: dict[str, float]) -> None:
        for symbol, price in prices.items():
            if price and price > 0:
                self._marks[symbol] = float(price)

    def price_of(self, symbol: str) -> float:
        position = self.positions.get(symbol)
        return self._marks.get(symbol, position.entry_price if position else 0.0)

    @property
    def invested(self) -> float:
        return sum(p.quantity * self.price_of(p.symbol) for p in self.positions.values())

    @property
    def equity(self) -> float:
        return self.cash + self.invested

    @property
    def exposure(self) -> float:
        equity = self.equity
        return self.invested / equity if equity > 0 else 0.0

    @property
    def drawdown(self) -> float:
        """Peak-to-trough on equity, the number the operator's mandate is written in."""
        peak = max(self.high_water, self.equity)
        return 0.0 if peak <= 0 else max(0.0, (peak - self.equity) / peak)

    @property
    def return_pct(self) -> float:
        return (self.equity / self.initial_capital) - 1.0 if self.initial_capital else 0.0

    def unrealised_pct(self, symbol: str) -> float:
        position = self.positions.get(symbol)
        if not position or not position.entry_price:
            return 0.0
        return (self.price_of(symbol) / position.entry_price) - 1.0

    # -- the shape the brain expects ------------------------------------------

    def account_payload(self) -> dict[str, Any]:
        """Exactly `BacktestSession._account_payload`. The brain must not be able to tell."""
        return {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "equity": self.equity,
            "invested": self.invested,
            "exposure": self.exposure,
            "positions": {
                symbol: {
                    "quantity": p.quantity,
                    "entry_price": p.entry_price,
                    "entry_time": p.entry_time.isoformat(),
                    "invested": p.quantity * self.price_of(symbol),
                    "unrealised_pct": self.unrealised_pct(symbol),
                }
                for symbol, p in self.positions.items()
            },
        }

    # -- mutation --------------------------------------------------------------

    def apply_fill(self, fill: Fill) -> Fill:
        """Move cash and inventory. Returns the fill with `realised` filled in on sells."""
        if fill.side == "BUY":
            cost = fill.notional + fill.fee
            if cost > self.cash + 1e-9:
                raise ValueError(f"buy of {cost:.2f} exceeds cash {self.cash:.2f}")
            self.cash -= cost
            held = self.positions.get(fill.symbol)
            if held:
                # Averaging up is a real thing this strategy does (scale_in), so the
                # entry price has to become the weighted one or every later stop and
                # unrealised figure would be measured from the wrong level.
                total_qty = held.quantity + fill.quantity
                held.entry_price = ((held.entry_price * held.quantity
                                     + fill.price * fill.quantity) / total_qty)
                held.quantity = total_qty
                held.invested_cost += cost
            else:
                self.positions[fill.symbol] = Position(
                    symbol=fill.symbol, quantity=fill.quantity, entry_time=fill.at,
                    entry_price=fill.price, invested_cost=cost)
        elif fill.side == "SELL":
            held = self.positions.get(fill.symbol)
            if not held:
                raise ValueError(f"sell of {fill.symbol} with nothing held")
            sold = min(fill.quantity, held.quantity)
            proceeds = fill.price * sold - fill.fee
            self.cash += proceeds
            cost_share = held.invested_cost * (sold / held.quantity) if held.quantity else 0.0
            fill.realised = proceeds - cost_share
            self.realised += fill.realised
            self.trades_closed += 1
            remaining = held.quantity - sold
            if remaining <= 1e-12:
                del self.positions[fill.symbol]
            else:
                held.quantity = remaining
                held.invested_cost -= cost_share
        else:
            raise ValueError(f"unknown side {fill.side!r}")
        self.fees_paid += fill.fee
        self.high_water = max(self.high_water, self.equity)
        return fill

    # -- persistence -----------------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        return {
            "initial_capital": self.initial_capital, "cash": self.cash,
            "positions": {s: p.to_json() for s, p in self.positions.items()},
            "realised": self.realised, "fees_paid": self.fees_paid,
            "trades_closed": self.trades_closed, "opened_at": self.opened_at.isoformat(),
            "high_water": self.high_water, "marks": self._marks,
        }

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> "LiveBook":
        book = cls(initial_capital=float(row.get("initial_capital", config.INITIAL_CAPITAL)),
                   cash=float(row["cash"]))
        book.positions = {s: Position.from_json(p) for s, p in (row.get("positions") or {}).items()}
        book.realised = float(row.get("realised", 0.0))
        book.fees_paid = float(row.get("fees_paid", 0.0))
        book.trades_closed = int(row.get("trades_closed", 0))
        book.opened_at = datetime.fromisoformat(row["opened_at"]) if row.get("opened_at") \
            else datetime.now(timezone.utc)
        book.high_water = float(row.get("high_water", book.initial_capital))
        book._marks = {k: float(v) for k, v in (row.get("marks") or {}).items()}
        return book

    def save(self, path: Path | None = None) -> Path:
        """Atomic: write beside, then replace. A half-written book is an unrecoverable one."""
        path = path or config.BOOK_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_json(), indent=1, default=str), encoding="utf-8")
        tmp.replace(path)
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "LiveBook":
        path = path or config.BOOK_PATH
        if not path.is_file():
            return cls()
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))


def append_ledger(row: dict[str, Any], path: Path | None = None) -> None:
    """One line per FILL and per engine swap. Append-only, never rewritten."""
    path = path or config.LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def read_ledger(path: Path | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    path = path or config.LEDGER_PATH
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    return rows[-limit:] if limit else rows
