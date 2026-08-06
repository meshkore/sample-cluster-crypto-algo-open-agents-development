"""What the strategy has to beat.

A long-only crypto strategy returning +0.2% over seven months has said nothing
until you know what holding the asset returned over the same seven months. This
laboratory ran for months with no benchmark anywhere in it, which is why a
strategy that mostly sat in cash could be published as the best one: with
nothing to compare against, the ranking could not tell caution from skill.

Two references, both long-only, both paying the same costs the strategy pays:

* **Buy and hold BTC** — the thing anyone can do without a laboratory.
* **Equal weight** — the same capital spread evenly across every asset the
  strategy was allowed to trade, rebalanced never. This is the harder and
  fairer comparison, because it holds the strategy's own universe.

Both are computed from the same bars over the same window, so the difference
is attributable to the strategy rather than to a different sample.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from .models import Bar


BTC = "BTCUSDT"


def _window(bars: list[Bar], start: datetime, end: datetime) -> list[Bar]:
    return [bar for bar in bars if start <= bar.timestamp <= end]


def _hold_return(
    bars: list[Bar], commission_bps: float, slippage_bps: float
) -> Optional[float]:
    """Return of buying at the first open and selling at the last close.

    Costs are charged on both sides, exactly as the strategy pays them, so the
    comparison is not quietly rigged in the benchmark's favour.
    """
    if len(bars) < 2:
        return None
    entry = bars[0].open * (1 + slippage_bps / 10_000)
    exit_price = bars[-1].close * (1 - slippage_bps / 10_000)
    if entry <= 0:
        return None
    gross = exit_price / entry
    fees = (commission_bps / 10_000) * 2
    return gross * (1 - fees) - 1


def buy_and_hold(
    bars_by_symbol: dict[str, list[Bar]],
    start: datetime,
    end: datetime,
    commission_bps: float = 10.0,
    slippage_bps: float = 5.0,
    symbol: str = BTC,
) -> Optional[float]:
    bars = _window(bars_by_symbol.get(symbol) or [], start, end)
    return _hold_return(bars, commission_bps, slippage_bps)


def equal_weight(
    bars_by_symbol: dict[str, list[Bar]],
    start: datetime,
    end: datetime,
    commission_bps: float = 10.0,
    slippage_bps: float = 5.0,
    symbols: Optional[Iterable[str]] = None,
) -> Optional[float]:
    """Equal capital in every tradable asset, held to the end.

    An asset with too little history in the window is skipped rather than
    counted as flat: pretending an unlisted asset returned zero is the
    survivorship bias this benchmark exists to expose, not to commit.
    """
    universe = list(symbols if symbols is not None else bars_by_symbol.keys())
    returns = []
    for name in universe:
        held = _hold_return(
            _window(bars_by_symbol.get(name) or [], start, end),
            commission_bps,
            slippage_bps,
        )
        if held is not None:
            returns.append(held)
    if not returns:
        return None
    return sum(returns) / len(returns)


def evaluate(
    bars_by_symbol: dict[str, list[Bar]],
    start: datetime,
    end: datetime,
    strategy_return: Optional[float],
    commission_bps: float = 10.0,
    slippage_bps: float = 5.0,
    symbols: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    """Both references and the strategy's excess over the harder one."""
    hold = buy_and_hold(bars_by_symbol, start, end, commission_bps, slippage_bps)
    even = equal_weight(
        bars_by_symbol, start, end, commission_bps, slippage_bps, symbols
    )
    available = [value for value in (hold, even) if value is not None]
    # Beat the better of the two, so a strategy cannot look good merely by
    # picking the weaker comparison.
    reference = max(available) if available else None
    excess = (
        None
        if reference is None or strategy_return is None
        else strategy_return - reference
    )
    return {
        "buy_and_hold": hold,
        "equal_weight": even,
        "reference": reference,
        "reference_name": None
        if reference is None
        else ("buy_and_hold" if reference == hold else "equal_weight"),
        "excess_return": excess,
    }
