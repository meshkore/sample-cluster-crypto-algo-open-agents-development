"""Precomputed indicator panels, so the trading system never recomputes them.

This is deliberately boring work moved off the brain. Every value here is a
pure function of prices up to and including its own bar, computed once per
series in a single pass, and handed to the trading system already done.

**Causality is the whole contract.** The panel at bar *i* may only use bars
`0..i`. A strategy is separately forbidden from acting on bar *i* at bar *i*'s
own open -- the session enforces that by filling at the NEXT bar -- so the two
rules together mean an indicator can be read the moment its bar closes without
any lookahead.

Adding an indicator here is cheap and safe. Adding one that peeks forward would
corrupt every strategy at once, which is why `panel_for` is tested by prefix
equality: the panel computed over a truncated series must match the panel
computed over the whole one, at every cut point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Bar


@dataclass(frozen=True)
class IndicatorSpec:
    """What to compute. Kept small on purpose: every entry costs a pass."""

    sma_periods: tuple[int, ...] = (20, 50, 200)
    ema_periods: tuple[int, ...] = (12, 26)
    rsi_period: int = 14
    atr_period: int = 14
    high_low_periods: tuple[int, ...] = (20, 55, 200)
    volume_period: int = 20
    return_periods: tuple[int, ...] = (1, 7, 30)

    def keys(self) -> tuple[str, ...]:
        names: list[str] = []
        names += [f"sma_{p}" for p in self.sma_periods]
        names += [f"ema_{p}" for p in self.ema_periods]
        names += [f"rsi_{self.rsi_period}", f"atr_{self.atr_period}"]
        for p in self.high_low_periods:
            names += [f"high_{p}", f"low_{p}", f"pct_below_high_{p}"]
        names += [f"dollar_volume_{self.volume_period}"]
        names += [f"return_{p}" for p in self.return_periods]
        return tuple(names)


def _rolling_mean(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    total = 0.0
    for index, value in enumerate(values):
        total += value
        if index >= period:
            total -= values[index - period]
        out.append(total / period if index + 1 >= period else None)
    return out


def _ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    multiplier = 2 / (period + 1)
    running: float | None = None
    for index, value in enumerate(values):
        running = value if running is None else (value - running) * multiplier + running
        out.append(running if index + 1 >= period else None)
    return out


def _rsi(closes: list[float], period: int) -> list[float | None]:
    """Wilder's RSI. Seeded from the first `period` changes, then smoothed."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = losses = 0.0
    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    average_gain, average_loss = gains / period, losses / period
    for index in range(period, len(closes)):
        if index > period:
            change = closes[index] - closes[index - 1]
            average_gain = (average_gain * (period - 1) + max(change, 0.0)) / period
            average_loss = (average_loss * (period - 1) + max(-change, 0.0)) / period
        if average_loss == 0:
            out[index] = 100.0
        else:
            strength = average_gain / average_loss
            out[index] = 100 - 100 / (1 + strength)
    return out


def _atr(bars: list[Bar], period: int) -> list[float | None]:
    ranges: list[float] = []
    for index, bar in enumerate(bars):
        if index == 0:
            ranges.append(bar.high - bar.low)
            continue
        previous = bars[index - 1].close
        ranges.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous),
                abs(bar.low - previous),
            )
        )
    return _rolling_mean(ranges, period)


def _rolling_extreme(
    values: list[float], period: int, highest: bool
) -> list[float | None]:
    """O(n) rolling max/min via a monotonic deque of indices.

    The naive version is O(n*period), which at 200-bar windows over a 386-asset
    universe is the difference between a backtest that serves ticks promptly and
    one that stalls the trading system waiting for arithmetic.
    """
    out: list[float | None] = []
    window: list[int] = []
    for index, value in enumerate(values):
        while window and window[0] <= index - period:
            window.pop(0)
        while window and (
            values[window[-1]] <= value if highest else values[window[-1]] >= value
        ):
            window.pop()
        window.append(index)
        out.append(values[window[0]] if index + 1 >= period else None)
    return out


def panel_for(
    bars: list[Bar], spec: IndicatorSpec | None = None
) -> list[dict[str, Any]]:
    """One dict of indicator values per bar, aligned with `bars`.

    Values are `None` until their window is full. That is deliberate rather than
    zero-filled: a strategy comparing against zero would silently treat a
    warm-up bar as a real reading, and this laboratory has already lost a result
    to a missing value read as a number.
    """
    spec = spec or IndicatorSpec()
    closes = [bar.close for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    turnover = [bar.close * bar.volume for bar in bars]

    columns: dict[str, list[float | None]] = {}
    for period in spec.sma_periods:
        columns[f"sma_{period}"] = _rolling_mean(closes, period)
    for period in spec.ema_periods:
        columns[f"ema_{period}"] = _ema(closes, period)
    columns[f"rsi_{spec.rsi_period}"] = _rsi(closes, spec.rsi_period)
    columns[f"atr_{spec.atr_period}"] = _atr(bars, spec.atr_period)
    for period in spec.high_low_periods:
        top = _rolling_extreme(highs, period, highest=True)
        bottom = _rolling_extreme(lows, period, highest=False)
        columns[f"high_{period}"] = top
        columns[f"low_{period}"] = bottom
        columns[f"pct_below_high_{period}"] = [
            (closes[i] / value - 1) if value else None for i, value in enumerate(top)
        ]
    columns[f"dollar_volume_{spec.volume_period}"] = _rolling_mean(
        turnover, spec.volume_period
    )
    for period in spec.return_periods:
        columns[f"return_{period}"] = [
            (closes[i] / closes[i - period] - 1)
            if i >= period and closes[i - period]
            else None
            for i in range(len(closes))
        ]

    return [
        {name: column[index] for name, column in columns.items()}
        for index in range(len(bars))
    ]
