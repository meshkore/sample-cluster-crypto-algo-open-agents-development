"""The trading system's side of the wire: pull a candle, decide, send orders.

This is the small piece. Everything generic -- downloading, indicator
arithmetic, the clock, fills, costs, the order book -- lives in the backtester.
What is left here is the part that has to be argued about: what to buy, how
much, and when to stop.

The loop is deliberately three lines of logic:

    while not done:
        tick = backtester.next()          # a closed candle, indicators done
        decision = brain.decide(tick)     # the only interesting call
        backtester.submit(decision)

The clock is pulled, so a brain that needs a second to think costs itself a
second and nothing else. Nothing here runs on a timer.

**What this owns.** The mandate: capital at risk, the drawdown ceiling, the
decision to stop. `Brain.decide` sees the account as the backtester reports it
-- cash, equity, positions, unrealised PnL -- and returns intentions. It never
computes a fill and never touches the book, because a strategy that graded
itself would be marking its own homework.

A contributor writes a `Brain`. Nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json


@dataclass
class Decision:
    """What the brain wants done with the candle it just saw."""

    orders: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""
    stop: str | None = None

    def buy(self, symbol: str, notional: float, reason: str = "", rationale: str = ""):
        self.orders.append(
            {
                "symbol": symbol,
                "side": "BUY",
                "notional": notional,
                "reason": reason,
                "rationale": rationale,
            }
        )
        return self

    def sell(self, symbol: str, reason: str = "", rationale: str = ""):
        self.orders.append(
            {"symbol": symbol, "side": "SELL", "reason": reason, "rationale": rationale}
        )
        return self


class Brain(Protocol):
    """The entire contribution surface. One method.

    `tick` carries `candles`, `indicators`, `account` and `clock`. Return a
    `Decision`. Set `Decision.stop` to end the run -- that is the trading
    system's call and no one else's, which is why the backtester exposes it as
    a request rather than deciding for you.
    """

    def decide(self, tick: dict[str, Any]) -> Decision: ...


class BacktesterClient:
    """Thin HTTP client. No retries by default: a backtest should fail loudly."""

    def __init__(self, base_url: str = "http://127.0.0.1:8770", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read() or b"{}")
        except HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"backtester returned {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(
                f"cannot reach the backtester at {self.base_url}: {exc.reason}. "
                "Start it with `python3 -m quantlab_backtester.server`."
            ) from exc

    def create(self, config: dict[str, Any]) -> str:
        return self._call("POST", "/sessions", config)["backtest_id"]

    def next(self, backtest_id: str) -> dict[str, Any]:
        return self._call("GET", f"/sessions/{backtest_id}/next")

    def submit(self, backtest_id: str, decision: Decision) -> dict[str, Any]:
        return self._call(
            "POST",
            f"/sessions/{backtest_id}/orders",
            {"orders": decision.orders, "note": decision.note},
        )

    def stop(self, backtest_id: str, reason: str) -> dict[str, Any]:
        return self._call("POST", f"/sessions/{backtest_id}/stop", {"reason": reason})

    def summary(self, backtest_id: str) -> dict[str, Any]:
        return self._call("GET", f"/sessions/{backtest_id}")


def run_backtest(
    brain: Brain,
    config: dict[str, Any],
    client: BacktesterClient | None = None,
    max_ticks: int | None = None,
) -> dict[str, Any]:
    """Drive one backtest to completion and return its summary."""
    client = client or BacktesterClient()
    backtest_id = client.create(config)
    ticks = 0
    while True:
        tick = client.next(backtest_id)
        if tick.get("done"):
            break
        ticks += 1
        decision = brain.decide(tick)
        if decision.stop:
            return client.stop(backtest_id, decision.stop)
        if decision.orders or decision.note:
            client.submit(backtest_id, decision)
        if max_ticks is not None and ticks >= max_ticks:
            return client.stop(backtest_id, f"max_ticks {max_ticks} reached")
    return client.summary(backtest_id)


# --------------------------------------------------------------------------- #
# A worked example, and the smallest honest brain in the repository.


@dataclass
class MandateBrain:
    """Trend participation with the operator's drawdown mandate enforced here.

    Included as the reference contribution: it shows the whole surface without
    hiding anything in a base class. Every number is a decision and every
    decision is in this file.

    The mandate is enforced by the BRAIN, not the backtester. That is the point
    of the split -- the simulator has no view on whether a 25% loss should end a
    run, and different contributors will legitimately disagree.
    """

    maximum_drawdown: float = 0.25
    position_fraction: float = 0.04
    maximum_positions: int = 15
    take_profit: float = 0.10
    stop_loss: float = 0.35
    trend_key: str = "sma_200"
    fast_key: str = "sma_50"
    minimum_dollar_volume: float = 10_000_000.0

    def decide(self, tick: dict[str, Any]) -> Decision:
        decision = Decision()
        account = tick["account"]
        equity = account["equity"]
        initial = account["initial_capital"]

        # The mandate, checked before anything else. Measured against the
        # deposit rather than the running peak: a run that made 300% and gave
        # back half has not breached anything the operator cares about.
        if initial and equity / initial - 1 <= -self.maximum_drawdown:
            decision.stop = (
                f"drawdown mandate breached: equity {equity:.0f} against "
                f"deposit {initial:.0f}"
            )
            return decision

        positions = account["positions"]
        for symbol, holding in positions.items():
            move = holding["unrealised_pct"]
            if move >= self.take_profit:
                decision.sell(symbol, "TAKE_PROFIT", f"+{move:.1%} reached target")
            elif move <= -self.stop_loss:
                decision.sell(symbol, "STOP_LOSS", f"{move:.1%} breached stop")

        room = self.maximum_positions - len(positions) + len(decision.orders)
        if room > 0:
            budget = equity * self.position_fraction
            for symbol, indicators in sorted(tick.get("indicators", {}).items()):
                if room <= 0 or budget > account["cash"]:
                    break
                if symbol in positions:
                    continue
                close = tick["candles"][symbol]["close"]
                slow, fast = (
                    indicators.get(self.trend_key),
                    indicators.get(self.fast_key),
                )
                turnover = indicators.get("dollar_volume_20")
                # `None` means the window has not filled yet. Treating it as
                # zero would read a warm-up bar as a real signal.
                if slow is None or fast is None or turnover is None:
                    continue
                if turnover < self.minimum_dollar_volume:
                    continue
                if close > slow and close > fast:
                    decision.buy(
                        symbol,
                        budget,
                        "TREND",
                        f"close {close:.4g} above {self.fast_key} and {self.trend_key}",
                    )
                    room -= 1

        if not decision.orders:
            decision.note = f"held {len(positions)} positions, no action"
        return decision
