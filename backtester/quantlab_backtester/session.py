"""A backtest session: the clock, the tape, and the fills. No opinions.

This is the ghost the operator asked for. It downloads nothing it is not told
to, decides nothing at all, and exists to do the boring work so the trading
system can stay small: advance time, hand over the candle with its indicators
already computed, execute whatever orders come back, and keep the book.

**The clock is pulled, not pushed.** `next_tick()` advances one bar. The trading
system asks for the next candle when it is ready for one, so a slow decision
costs only its own time and a fast one runs flat out. Nothing here has a timer.

**Orders submitted against tick N fill at the open of tick N+1.** This is the
single most important rule in the file. The trading system sees a closed candle
and reacts to it; it cannot trade inside the bar it is looking at. Every
lookahead this laboratory has caught came from blurring that line, so the
session enforces it structurally -- submitted orders sit in a queue and are
executed by the *next* call to `next_tick`, at that bar's open, never at the
close the decision was made on.

**Who owns what.** The session owns execution truth: fills, costs, cash,
holdings, the order log. The trading system owns every decision: what to buy,
how much, when to stop. It reads the account through a snapshot in each tick and
can never write it. That split is what makes two contributors' results
comparable -- same fills, same costs, same book, different brains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable
import itertools

from .backtest import CostModel
from .indicator_store import IndicatorStore
from .indicators import IndicatorSpec, panel_for
from .ledger import AccountLedger, BacktestRun
from .models import Bar, utc_now


class SessionError(RuntimeError):
    """Raised when a caller asks for something the session cannot honour."""


@dataclass
class OrderRequest:
    """What the trading system wants done. An intention, not a fill."""

    symbol: str
    side: str
    notional: float | None = None
    quantity: float | None = None
    reason: str = ""
    # Free text the visualiser can show. The session never interprets it.
    rationale: str = ""

    def __post_init__(self) -> None:
        self.side = self.side.upper()
        if self.side not in ("BUY", "SELL"):
            raise SessionError(f"side must be BUY or SELL, got {self.side!r}")
        if self.side == "BUY" and not self.notional and not self.quantity:
            raise SessionError("a BUY needs a notional or a quantity")

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> OrderRequest:
        if not isinstance(payload, dict):
            raise SessionError("each order must be an object")
        unknown = set(payload) - {
            "symbol",
            "side",
            "notional",
            "quantity",
            "reason",
            "rationale",
        }
        if unknown:
            raise SessionError(f"unknown order fields: {sorted(unknown)}")
        try:
            symbol = str(payload["symbol"])
            side = str(payload["side"])
        except KeyError as exc:
            raise SessionError(f"order is missing {exc}") from exc
        return cls(
            symbol=symbol,
            side=side,
            notional=float(payload["notional"]) if payload.get("notional") else None,
            quantity=float(payload["quantity"]) if payload.get("quantity") else None,
            reason=str(payload.get("reason", "")),
            rationale=str(payload.get("rationale", ""))[:500],
        )


@dataclass
class BacktestSession:
    """One run of the tape, pulled a bar at a time."""

    run: BacktestRun
    bars_by_symbol: dict[str, list[Bar]]
    costs: CostModel = field(default_factory=lambda: CostModel(0.0, 0.0))
    indicator_spec: IndicatorSpec = field(default_factory=IndicatorSpec)
    start: datetime | None = None
    end: datetime | None = None
    # Where backfilled panels live. With a store the arithmetic happens once,
    # ever; without one it happens per session, which is fine for a handful of
    # symbols and painful across the universe.
    indicator_store: IndicatorStore | None = None
    # Serve the first bars at all? A 200-day average is wrong for its first 200
    # bars, and a brain reading it cannot tell. Skipping is the default because
    # the alternative is trusting every contributor to check every column.
    skip_warmup: bool = True

    def __post_init__(self) -> None:
        prepared = {
            symbol: sorted(bars, key=lambda bar: bar.timestamp)
            for symbol, bars in self.bars_by_symbol.items()
            if len(bars) >= 2
        }
        if not prepared:
            raise SessionError("a session needs at least one asset with two bars")
        self.bars_by_symbol = prepared

        # Indicators are computed once, over the full series, before the clock
        # starts. Every value is a function of bars up to its own, so serving
        # them precomputed is identical to computing them live -- and it moves
        # the arithmetic off the critical path between two ticks.
        if self.indicator_store is not None:
            self._panels = {
                symbol: self.indicator_store.panel(symbol, bars, self.indicator_spec)
                for symbol, bars in prepared.items()
            }
        else:
            self._panels = {
                symbol: panel_for(bars, self.indicator_spec)
                for symbol, bars in prepared.items()
            }
        self.warmup_bars = max(
            (panel.warmup_bars for panel in self._panels.values()), default=0
        )
        self._index_of = {
            symbol: {bar.timestamp: i for i, bar in enumerate(bars)}
            for symbol, bars in prepared.items()
        }

        stamps = sorted({bar.timestamp for bars in prepared.values() for bar in bars})
        self.timeline = [
            stamp
            for stamp in stamps
            if (self.start is None or stamp >= self.start)
            and (self.end is None or stamp <= self.end)
        ]
        if self.skip_warmup and self.timeline:
            # Trim from the FRONT of the usable window rather than filtering by
            # index, so an explicit `start` still means what the caller asked and
            # the skipped bars are simply the ones no indicator can describe yet.
            earliest = {}
            for symbol, bars in prepared.items():
                panel = self._panels[symbol]
                if panel.warmup_bars < len(bars):
                    earliest[symbol] = bars[panel.warmup_bars].timestamp
            if earliest:
                ready = min(earliest.values())
                trimmed = [stamp for stamp in self.timeline if stamp >= ready]
                if len(trimmed) >= 2:
                    self.skipped_warmup_bars = len(self.timeline) - len(trimmed)
                    self.timeline = trimmed
        if len(self.timeline) < 2:
            raise SessionError("the requested window contains fewer than two bars")

        self.skipped_warmup_bars = getattr(self, "skipped_warmup_bars", 0)
        self.ledger = AccountLedger(initial_capital=self.run.initial_capital)
        self.cursor = -1
        self.status = "ready"
        self.stop_reason: str | None = None
        self.pending: list[OrderRequest] = []
        self.rejected: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.equity_curve: list[dict[str, Any]] = []
        self._sequence = itertools.count(1)
        self.started_at = utc_now()

    # -- the clock ----------------------------------------------------------- #

    @property
    def finished(self) -> bool:
        return self.status in ("complete", "stopped", "failed")

    def next_tick(self) -> dict[str, Any]:
        """Advance one bar: fill what was queued, then serve the new candle."""
        if self.finished:
            raise SessionError(f"session is {self.status}; it cannot advance")
        if self.cursor + 1 >= len(self.timeline):
            self.status = "complete"
            return self._tick_payload(done=True)

        self.cursor += 1
        stamp = self.timeline[self.cursor]
        self.status = "running"

        # Queued orders execute at THIS bar's open -- the bar after the one the
        # decision was made on. Filling before the mark means the account the
        # tick reports already reflects them.
        filled = self._execute_pending(stamp)

        for symbol, bar in self._bars_at(stamp).items():
            self.ledger.mark(symbol, bar.close)

        self.equity_curve.append(
            {
                "timestamp": stamp.isoformat(),
                "equity": self.ledger.equity,
                "cash": self.ledger.cash,
                "open_positions": len(self.ledger.holdings),
                "active": bool(self.ledger.holdings),
            }
        )
        payload = self._tick_payload(done=False)
        payload["filled"] = filled
        return payload

    def submit(self, orders: Iterable[OrderRequest], note: str = "") -> dict[str, Any]:
        """Queue orders against the tick just served.

        Accepted here, executed at the next one. Rejections are returned rather
        than raised so a single bad order does not abort a run, and every one is
        recorded -- a silently dropped order is indistinguishable from a
        strategy that chose not to trade.
        """
        if self.cursor < 0:
            raise SessionError("no tick has been served yet")
        if self.finished:
            raise SessionError(f"session is {self.status}; it cannot accept orders")

        accepted, refused = [], []
        for order in orders:
            problem = self._why_not(order)
            if problem:
                refused.append({"order": order.__dict__, "reason": problem})
            else:
                accepted.append(order)
        self.pending.extend(accepted)
        self.rejected.extend(refused)
        self.decisions.append(
            {
                "sequence": self.cursor,
                "timestamp": self.timeline[self.cursor].isoformat(),
                "note": note[:500],
                "orders": [order.__dict__ for order in accepted],
                "rejected": refused,
            }
        )
        return {"accepted": len(accepted), "rejected": refused}

    def stop(self, reason: str) -> dict[str, Any]:
        """The trading system decides to end the run. Drawdown, profit, anything.

        The session has no view on whether stopping is wise. It is not its
        decision to make, which is precisely why it is exposed as a call.
        """
        if self.finished:
            return self.summary()
        self.status = "stopped"
        self.stop_reason = reason[:500]
        return self.summary()

    # -- execution ----------------------------------------------------------- #

    def _bars_at(self, stamp: datetime) -> dict[str, Bar]:
        out = {}
        for symbol, positions in self._index_of.items():
            index = positions.get(stamp)
            if index is not None:
                out[symbol] = self.bars_by_symbol[symbol][index]
        return out

    def _why_not(self, order: OrderRequest) -> str | None:
        if order.symbol not in self.bars_by_symbol:
            return f"unknown symbol {order.symbol}"
        if order.side == "SELL" and order.symbol not in self.ledger.holdings:
            return f"no open position in {order.symbol}"
        if order.side == "BUY":
            if order.symbol in self.ledger.holdings:
                return f"already holding {order.symbol}"
            if (order.notional or 0) <= 0 and (order.quantity or 0) <= 0:
                return "buy size must be positive"
        return None

    def _execute_pending(self, stamp: datetime) -> list[dict[str, Any]]:
        if not self.pending:
            return []
        todays = self._bars_at(stamp)
        filled: list[dict[str, Any]] = []
        for order in self.pending:
            bar = todays.get(order.symbol)
            if bar is None:
                # No bar for this symbol today. The order is dropped rather than
                # carried, because carrying it would fill at an unknown later
                # price the decision never saw.
                self.rejected.append(
                    {"order": order.__dict__, "reason": "no bar at execution time"}
                )
                continue
            problem = self._why_not(order)
            if problem:
                self.rejected.append({"order": order.__dict__, "reason": problem})
                continue
            if order.side == "BUY":
                fill = bar.open * (1 + self.costs.slippage_bps / 10_000)
                notional = order.notional or (order.quantity or 0.0) * fill
                notional = min(notional, self.ledger.cash)
                if notional <= 0:
                    self.rejected.append(
                        {"order": order.__dict__, "reason": "insufficient cash"}
                    )
                    continue
                fee = notional * self.costs.commission_bps / 10_000
                quantity = (notional - fee) / fill
                record = self.ledger.record_buy(
                    stamp,
                    order.symbol,
                    quantity,
                    fill,
                    notional,
                    fee,
                    order.reason or "ENTRY",
                )
            else:
                holding = self.ledger.holdings[order.symbol]
                fill = bar.open * (1 - self.costs.slippage_bps / 10_000)
                proceeds = holding.quantity * fill
                fee = proceeds * self.costs.commission_bps / 10_000
                record = self.ledger.record_sell(
                    stamp, order.symbol, fill, proceeds, fee, order.reason or "EXIT"
                )
            filled.append(record.document())
        self.pending = []
        return filled

    # -- payloads ------------------------------------------------------------ #

    def _tick_payload(self, done: bool) -> dict[str, Any]:
        if done or self.cursor < 0:
            return {
                "backtest_id": self.run.backtest_id,
                "done": True,
                "status": self.status,
                "sequence": max(self.cursor, 0),
                "account": self._account_payload(),
                "clock": {"processed": self.cursor + 1, "total": len(self.timeline)},
            }
        stamp = self.timeline[self.cursor]
        candles, indicators = {}, {}
        for symbol, bar in self._bars_at(stamp).items():
            candles[symbol] = {
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            indicators[symbol] = self._panels[symbol].at(self._index_of[symbol][stamp])
        return {
            "backtest_id": self.run.backtest_id,
            "done": False,
            "status": self.status,
            "sequence": self.cursor,
            "timestamp": stamp.isoformat(),
            "candles": candles,
            "indicators": indicators,
            "account": self._account_payload(),
            "clock": {"processed": self.cursor + 1, "total": len(self.timeline)},
        }

    def _account_payload(self) -> dict[str, Any]:
        return {
            "initial_capital": self.ledger.initial_capital,
            "cash": self.ledger.cash,
            "equity": self.ledger.equity,
            "invested": self.ledger.invested,
            "exposure": self.ledger.exposure,
            "positions": {
                symbol: {
                    "quantity": holding.quantity,
                    "entry_price": holding.entry_price,
                    "entry_time": holding.entry_time.isoformat(),
                    "invested": holding.invested,
                    "unrealised_pct": self.ledger.view().unrealised_pct(symbol),
                }
                for symbol, holding in self.ledger.holdings.items()
            },
        }

    def summary(self) -> dict[str, Any]:
        initial = self.ledger.initial_capital
        equity = self.ledger.equity
        peak = initial
        worst = 0.0
        for point in self.equity_curve:
            peak = max(peak, point["equity"])
            worst = max(worst, 1 - point["equity"] / peak if peak else 0.0)
        return {
            "backtest_id": self.run.backtest_id,
            "label": self.run.label,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "started_at": self.started_at,
            "initial_capital": initial,
            "final_equity": equity,
            "return_pct": equity / initial - 1 if initial else 0.0,
            "max_drawdown": worst,
            "orders": len(self.ledger.orders),
            "rejected": len(self.rejected),
            "processed": self.cursor + 1,
            "total": len(self.timeline),
            "open_positions": len(self.ledger.holdings),
        }
