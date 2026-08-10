"""Precomputed indicators, so no strategy ever computes one.

The operator's requirement: every candle arrives with its indicators already
done, and a brain reads values rather than deriving them. This module is that
catalogue -- roughly eighty columns across trend, momentum, volatility, volume,
structure and trend strength -- computed once per series and served with the
tick.

**Why the formulas are written out instead of imported.** A TA library would be
a pip dependency computing the numbers that decide trades, in a project that is
stdlib-only and whose contributions arrive as pull requests with dependencies
inspected. These formulas are standard and each is tested; a dependency would be
faster to write and much harder to audit.

**Why the panel is columnar.** The obvious shape is a dict per bar. At 386
assets, 3,276 bars and eighty columns that is roughly a hundred million dict
entries -- several gigabytes of Python objects for one backtest. Columns are
`array('d')`, about a megabyte per symbol, and `IndicatorPanel.at()` builds the
single dict a tick actually needs.

**Causality is the contract.** Every column at bar *i* is a function of bars
`0..i` only. Combined with the session filling at the *next* bar, an indicator
can be read the moment its own bar closes with no lookahead. `panel_for` is
tested by prefix equality: the panel over a truncated series must match the
panel over the whole one at every cut point.

**Warm-up is `None`, never zero.** A rule comparing against zero would read a
half-formed window as a real reading. `IndicatorPanel.warmup_bars` says how many
bars must pass before every column is trustworthy, so a session can skip them
outright rather than trusting every brain to check.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass, field
from typing import Any, Iterable
import hashlib
import json
import math

from .models import Bar

NAN = float("nan")


def _blank(size: int) -> array:
    return array("d", [NAN]) * size if size else array("d")


def _is_value(x: float) -> bool:
    return not math.isnan(x)


# --------------------------------------------------------------------------- #
# primitives


def _sma(values: list[float], period: int) -> array:
    out = _blank(len(values))
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= period:
            total -= values[i - period]
        if i + 1 >= period:
            out[i] = total / period
    return out


def _ema(values: list[float], period: int) -> array:
    out = _blank(len(values))
    k = 2 / (period + 1)
    running = None
    for i, v in enumerate(values):
        running = v if running is None else (v - running) * k + running
        if i + 1 >= period:
            out[i] = running
    return out


def _wilder(values: list[float], period: int) -> array:
    """Wilder's smoothing: the average behind RSI, ATR, ADX and MFI."""
    out = _blank(len(values))
    if len(values) < period:
        return out
    running = sum(values[:period]) / period
    out[period - 1] = running
    for i in range(period, len(values)):
        running = (running * (period - 1) + values[i]) / period
        out[i] = running
    return out


def _wma(values: list[float], period: int) -> array:
    out = _blank(len(values))
    weights = list(range(1, period + 1))
    denominator = sum(weights)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        out[i] = sum(v * w for v, w in zip(window, weights)) / denominator
    return out


def _stdev(values: list[float], period: int) -> array:
    out = _blank(len(values))
    total = squares = 0.0
    for i, v in enumerate(values):
        total += v
        squares += v * v
        if i >= period:
            old = values[i - period]
            total -= old
            squares -= old * old
        if i + 1 >= period:
            mean = total / period
            out[i] = math.sqrt(max(0.0, squares / period - mean * mean))
    return out


def _extreme(values: list[float], period: int, highest: bool) -> array:
    """O(n) rolling max/min via a monotonic deque.

    The naive form is O(n*period) and, at 200-bar windows over a 386-asset
    universe, is the difference between a backfill that finishes and one that
    does not.
    """
    out = _blank(len(values))
    window: list[int] = []
    head = 0
    for i, v in enumerate(values):
        while len(window) > head and window[head] <= i - period:
            head += 1
        while len(window) > head and (
            values[window[-1]] <= v if highest else values[window[-1]] >= v
        ):
            window.pop()
        window.append(i)
        if i + 1 >= period:
            out[i] = values[window[head]]
    return out


def _true_range(bars: list[Bar]) -> list[float]:
    out = []
    for i, bar in enumerate(bars):
        if i == 0:
            out.append(bar.high - bar.low)
            continue
        previous = bars[i - 1].close
        out.append(
            max(bar.high - bar.low, abs(bar.high - previous), abs(bar.low - previous))
        )
    return out


def _rsi(closes: list[float], period: int) -> array:
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    average_gain = _wilder(gains, period)
    average_loss = _wilder(losses, period)
    out = _blank(len(closes))
    for i in range(1, len(closes)):
        gain, loss = average_gain[i - 1], average_loss[i - 1]
        if not _is_value(gain) or not _is_value(loss):
            continue
        out[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return out


# --------------------------------------------------------------------------- #
# the catalogue


@dataclass(frozen=True)
class IndicatorSpec:
    """Which indicators to compute. Changing this changes the cache key."""

    sma_periods: tuple[int, ...] = (5, 10, 20, 50, 100, 200)
    ema_periods: tuple[int, ...] = (9, 12, 21, 26, 50, 200)
    wma_periods: tuple[int, ...] = (20,)
    # 2 is Connors': a two-bar RSI is driven to its floor by two down closes,
    # which is the shortest oversold signal that exists. 7/14/21 all measure a
    # pullback; only this one measures the bar you would actually bounce from.
    rsi_periods: tuple[int, ...] = (2, 7, 14, 21)
    atr_periods: tuple[int, ...] = (14, 20)
    stdev_periods: tuple[int, ...] = (20,)
    channel_periods: tuple[int, ...] = (20, 55, 200)
    return_periods: tuple[int, ...] = (1, 5, 20, 60, 252)
    volume_periods: tuple[int, ...] = (20, 50)
    macd: tuple[int, int, int] = (12, 26, 9)
    bollinger: tuple[int, float] = (20, 2.0)
    keltner: tuple[int, float] = (20, 2.0)
    stochastic: tuple[int, int] = (14, 3)
    adx_period: int = 14
    cci_period: int = 20
    mfi_period: int = 14
    aroon_period: int = 25
    vortex_period: int = 14
    williams_period: int = 14
    cmf_period: int = 20
    force_period: int = 13
    supertrend: tuple[int, float] = (10, 3.0)
    ichimoku: tuple[int, int] = (9, 26)

    def cache_key(self) -> str:
        payload = json.dumps(self.__dict__, sort_keys=True, default=list)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]

    def warmup_bars(self) -> int:
        """Bars before every column is trustworthy: the longest window here.

        A 200-day average is wrong for its first 200 bars and right afterwards,
        so a session that starts at bar 0 hands the brain values that look like
        readings and are not.
        """
        return max(
            [
                *self.sma_periods,
                *self.ema_periods,
                *self.wma_periods,
                *self.rsi_periods,
                *self.atr_periods,
                *self.stdev_periods,
                *self.channel_periods,
                *self.return_periods,
                *self.volume_periods,
                self.macd[1] + self.macd[2],
                self.bollinger[0],
                self.keltner[0],
                self.stochastic[0] + self.stochastic[1],
                self.adx_period * 2,
                self.cci_period,
                self.mfi_period,
                self.aroon_period,
                self.vortex_period,
                self.williams_period,
                self.cmf_period,
                self.force_period,
                self.supertrend[0],
                self.ichimoku[1] * 2,
            ]
        )


@dataclass
class IndicatorPanel:
    """Columnar indicator values, aligned with the bars they were built from."""

    names: tuple[str, ...]
    columns: dict[str, array]
    length: int
    warmup_bars: int = 0
    spec_key: str = ""
    _order: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._order = list(self.names)

    def at(self, index: int) -> dict[str, Any]:
        """The one dict a tick needs. `None` where a window has not filled."""
        if not 0 <= index < self.length:
            raise IndexError(index)
        return {
            name: (None if math.isnan(v) else v)
            for name in self._order
            if (v := self.columns[name][index]) is not None
        }

    def ready_at(self, index: int) -> bool:
        return index >= self.warmup_bars


def _catalogue(bars: list[Bar], spec: IndicatorSpec) -> dict[str, array]:
    n = len(bars)
    opens = [b.open for b in bars]
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    volumes = [b.volume for b in bars]
    typical = [(h + low + c) / 3 for h, low, c in zip(highs, lows, closes)]
    turnover = [c * v for c, v in zip(closes, volumes)]
    ranges = _true_range(bars)
    columns: dict[str, array] = {}

    # -- trend --------------------------------------------------------------- #
    for p in spec.sma_periods:
        columns[f"sma_{p}"] = _sma(closes, p)
    for p in spec.ema_periods:
        columns[f"ema_{p}"] = _ema(closes, p)
    for p in spec.wma_periods:
        columns[f"wma_{p}"] = _wma(closes, p)
    # 20 is here for Kotegawa. He traded the 25-day moving-average deviation
    # rate -- buying 20-35% BELOW it and exiting as price reverted -- and the
    # nearest window this catalogue holds is 20 days. The 50 and 200 versions
    # measure trend position; only a short one measures dislocation, and a
    # dislocation is what a bounce trade is about.
    for p in (20, 50, 200):
        source = columns.get(f"sma_{p}")
        if source is None:
            continue
        distance = _blank(n)
        for i in range(n):
            if _is_value(source[i]) and source[i]:
                distance[i] = closes[i] / source[i] - 1
        columns[f"distance_to_sma_{p}"] = distance

    fast, slow, signal_period = spec.macd
    fast_ema, slow_ema = _ema(closes, fast), _ema(closes, slow)
    macd = _blank(n)
    for i in range(n):
        if _is_value(fast_ema[i]) and _is_value(slow_ema[i]):
            macd[i] = fast_ema[i] - slow_ema[i]
    signal = _ema([v if _is_value(v) else 0.0 for v in macd], signal_period)
    histogram = _blank(n)
    for i in range(n):
        if _is_value(macd[i]) and _is_value(signal[i]):
            histogram[i] = macd[i] - signal[i]
    columns["macd"] = macd
    columns["macd_signal"] = signal
    columns["macd_hist"] = histogram

    # -- momentum ------------------------------------------------------------ #
    for p in spec.rsi_periods:
        columns[f"rsi_{p}"] = _rsi(closes, p)

    k_period, d_period = spec.stochastic
    top = _extreme(highs, k_period, True)
    bottom = _extreme(lows, k_period, False)
    stoch_k = _blank(n)
    for i in range(n):
        if _is_value(top[i]) and _is_value(bottom[i]):
            span = top[i] - bottom[i]
            stoch_k[i] = 50.0 if span == 0 else (closes[i] - bottom[i]) / span * 100
    columns["stoch_k"] = stoch_k
    columns["stoch_d"] = _sma([v if _is_value(v) else 0.0 for v in stoch_k], d_period)

    w_high = _extreme(highs, spec.williams_period, True)
    w_low = _extreme(lows, spec.williams_period, False)
    williams = _blank(n)
    for i in range(n):
        if _is_value(w_high[i]) and _is_value(w_low[i]):
            span = w_high[i] - w_low[i]
            williams[i] = 0.0 if span == 0 else (w_high[i] - closes[i]) / span * -100
    columns["williams_r"] = williams

    typical_sma = _sma(typical, spec.cci_period)
    cci = _blank(n)
    for i in range(spec.cci_period - 1, n):
        mean = typical_sma[i]
        window = typical[i - spec.cci_period + 1 : i + 1]
        deviation = sum(abs(v - mean) for v in window) / spec.cci_period
        if deviation:
            cci[i] = (typical[i] - mean) / (0.015 * deviation)
    columns["cci"] = cci

    for p in spec.return_periods:
        column = _blank(n)
        for i in range(p, n):
            if closes[i - p]:
                column[i] = closes[i] / closes[i - p] - 1
        columns[f"return_{p}"] = column

    # -- volatility ---------------------------------------------------------- #
    for p in spec.atr_periods:
        atr = _wilder(ranges, p)
        columns[f"atr_{p}"] = atr
        natr = _blank(n)
        for i in range(n):
            if _is_value(atr[i]) and closes[i]:
                natr[i] = atr[i] / closes[i]
        columns[f"natr_{p}"] = natr
    for p in spec.stdev_periods:
        columns[f"stdev_{p}"] = _stdev(closes, p)

    bb_period, bb_mult = spec.bollinger
    bb_mid, bb_sd = _sma(closes, bb_period), _stdev(closes, bb_period)
    upper, lower, width, percent_b = _blank(n), _blank(n), _blank(n), _blank(n)
    for i in range(n):
        if _is_value(bb_mid[i]) and _is_value(bb_sd[i]):
            upper[i] = bb_mid[i] + bb_mult * bb_sd[i]
            lower[i] = bb_mid[i] - bb_mult * bb_sd[i]
            if bb_mid[i]:
                width[i] = (upper[i] - lower[i]) / bb_mid[i]
            span = upper[i] - lower[i]
            percent_b[i] = 0.5 if span == 0 else (closes[i] - lower[i]) / span
    columns["bb_mid"] = bb_mid
    columns["bb_upper"] = upper
    columns["bb_lower"] = lower
    columns["bb_width"] = width
    columns["bb_percent_b"] = percent_b

    kc_period, kc_mult = spec.keltner
    kc_mid, kc_atr = _ema(closes, kc_period), _wilder(ranges, kc_period)
    kc_up, kc_down = _blank(n), _blank(n)
    for i in range(n):
        if _is_value(kc_mid[i]) and _is_value(kc_atr[i]):
            kc_up[i] = kc_mid[i] + kc_mult * kc_atr[i]
            kc_down[i] = kc_mid[i] - kc_mult * kc_atr[i]
    columns["keltner_mid"] = kc_mid
    columns["keltner_upper"] = kc_up
    columns["keltner_lower"] = kc_down

    # -- structure ----------------------------------------------------------- #
    for p in spec.channel_periods:
        channel_top = _extreme(highs, p, True)
        channel_bottom = _extreme(lows, p, False)
        columns[f"high_{p}"] = channel_top
        columns[f"low_{p}"] = channel_bottom
        middle, below = _blank(n), _blank(n)
        for i in range(n):
            if _is_value(channel_top[i]) and _is_value(channel_bottom[i]):
                middle[i] = (channel_top[i] + channel_bottom[i]) / 2
            if _is_value(channel_top[i]) and channel_top[i]:
                below[i] = closes[i] / channel_top[i] - 1
        columns[f"mid_{p}"] = middle
        columns[f"pct_below_high_{p}"] = below

    running_high, drawdown = _blank(n), _blank(n)
    peak = closes[0] if closes else NAN
    for i, close in enumerate(closes):
        peak = max(peak, close)
        running_high[i] = peak
        drawdown[i] = close / peak - 1 if peak else NAN
    columns["running_high"] = running_high
    columns["drawdown_from_high"] = drawdown

    # -- what the bar itself did --------------------------------------------- #
    #
    # The rule language compares columns; it has no division and it refuses to
    # compare `high` against `low` in the same bar, because that is arithmetic
    # about what a candle is rather than a signal. The consequence went
    # unnoticed for seventy-three iterations: NOTHING about the shape of a
    # candle was expressible. The loop could say "price is 30% below its
    # average" and could not say "and it closed at the top of its range" --
    # which is the entire difference between a bounce and a falling knife.
    #
    # These are continuous, not pattern flags. `internal_bar_strength` at 0.9
    # IS a hammer without anyone having to agree on what a hammer is, and a
    # threshold the search can move beats a definition it cannot.
    ibs, body, upper_wick, lower_wick = _blank(n), _blank(n), _blank(n), _blank(n)
    for i in range(n):
        span = highs[i] - lows[i]
        if span <= 0:
            # A bar that did not move has no anatomy. NAN rather than 0.5, so a
            # rule reading it gets "unknown" and stands aside instead of being
            # handed the midpoint as though it were a measurement.
            continue
        ibs[i] = (closes[i] - lows[i]) / span
        top, bottom = max(opens[i], closes[i]), min(opens[i], closes[i])
        body[i] = (top - bottom) / span
        upper_wick[i] = (highs[i] - top) / span
        lower_wick[i] = (bottom - lows[i]) / span
    columns["internal_bar_strength"] = ibs
    columns["body_fraction"] = body
    columns["upper_wick_fraction"] = upper_wick
    columns["lower_wick_fraction"] = lower_wick

    # How wide this bar is against normal. Capitulation arrives on a range
    # several times the average, and `natr` cannot say that: it is the average
    # itself, not this bar against it.
    span_ratio = _blank(n)
    reference = columns.get("atr_14")
    if reference is not None:
        for i in range(n):
            if _is_value(reference[i]) and reference[i]:
                span_ratio[i] = (highs[i] - lows[i]) / reference[i]
    columns["range_vs_atr"] = span_ratio

    # Consecutive closes in one direction. Two down days is what drives RSI(2)
    # to zero in Connors' setup, and a count is the one thing a stateless
    # comparison language can never derive for itself.
    down_streak, up_streak = _blank(n), _blank(n)
    down = up = 0
    for i in range(n):
        if i == 0:
            down = up = 0
        elif closes[i] < closes[i - 1]:
            down, up = down + 1, 0
        elif closes[i] > closes[i - 1]:
            down, up = 0, up + 1
        else:
            down = up = 0
        down_streak[i], up_streak[i] = down, up
    columns["down_streak"] = down_streak
    columns["up_streak"] = up_streak

    # The one two-bar pattern worth naming, because it cannot be approximated
    # by anything above: today's body covering yesterday's, after a down bar.
    engulfing = _blank(n)
    for i in range(n):
        if i == 0:
            engulfing[i] = 0.0
            continue
        was_down = closes[i - 1] < opens[i - 1]
        is_up = closes[i] > opens[i]
        covers = closes[i] >= opens[i - 1] and opens[i] <= closes[i - 1]
        engulfing[i] = 1.0 if (was_down and is_up and covers) else 0.0
    columns["bullish_engulfing"] = engulfing

    # How stale the recent low is. A bounce bought on the bar that made the low
    # is a different trade from one bought eight bars later, and the search had
    # no way to tell them apart.
    since_low = _blank(n)
    window = 20
    for i in range(n):
        start = max(0, i - window + 1)
        lowest, at = lows[start], start
        for j in range(start, i + 1):
            if lows[j] <= lowest:
                lowest, at = lows[j], j
        since_low[i] = i - at
    columns["bars_since_low_20"] = since_low

    # -- trend strength ------------------------------------------------------ #
    plus_dm, minus_dm = [0.0], [0.0]
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    period = spec.adx_period
    atr_adx = _wilder(ranges, period)
    plus_smoothed, minus_smoothed = _wilder(plus_dm, period), _wilder(minus_dm, period)
    di_plus, di_minus, dx = _blank(n), _blank(n), _blank(n)
    for i in range(n):
        if _is_value(atr_adx[i]) and atr_adx[i]:
            if _is_value(plus_smoothed[i]):
                di_plus[i] = 100 * plus_smoothed[i] / atr_adx[i]
            if _is_value(minus_smoothed[i]):
                di_minus[i] = 100 * minus_smoothed[i] / atr_adx[i]
        if _is_value(di_plus[i]) and _is_value(di_minus[i]):
            total = di_plus[i] + di_minus[i]
            dx[i] = 0.0 if total == 0 else 100 * abs(di_plus[i] - di_minus[i]) / total
    columns["di_plus"] = di_plus
    columns["di_minus"] = di_minus
    columns["adx"] = _wilder([v if _is_value(v) else 0.0 for v in dx], period)

    aroon = spec.aroon_period
    aroon_up, aroon_down, aroon_osc = _blank(n), _blank(n), _blank(n)
    for i in range(aroon, n):
        window_high = highs[i - aroon : i + 1]
        window_low = lows[i - aroon : i + 1]
        since_high = aroon - window_high.index(max(window_high))
        since_low = aroon - window_low.index(min(window_low))
        aroon_up[i] = 100 * (aroon - since_high) / aroon
        aroon_down[i] = 100 * (aroon - since_low) / aroon
        aroon_osc[i] = aroon_up[i] - aroon_down[i]
    columns["aroon_up"] = aroon_up
    columns["aroon_down"] = aroon_down
    columns["aroon_osc"] = aroon_osc

    vm_plus, vm_minus = [0.0], [0.0]
    for i in range(1, n):
        vm_plus.append(abs(highs[i] - lows[i - 1]))
        vm_minus.append(abs(lows[i] - highs[i - 1]))
    sum_tr = _sma(ranges, spec.vortex_period)
    sum_plus = _sma(vm_plus, spec.vortex_period)
    sum_minus = _sma(vm_minus, spec.vortex_period)
    vi_plus, vi_minus = _blank(n), _blank(n)
    for i in range(n):
        if _is_value(sum_tr[i]) and sum_tr[i]:
            if _is_value(sum_plus[i]):
                vi_plus[i] = sum_plus[i] / sum_tr[i]
            if _is_value(sum_minus[i]):
                vi_minus[i] = sum_minus[i] / sum_tr[i]
    columns["vortex_plus"] = vi_plus
    columns["vortex_minus"] = vi_minus

    st_period, st_mult = spec.supertrend
    st_atr = _wilder(ranges, st_period)
    supertrend, direction = _blank(n), _blank(n)
    line, trend = NAN, 1.0
    for i in range(n):
        if not _is_value(st_atr[i]):
            continue
        basis = (highs[i] + lows[i]) / 2
        upper_band = basis + st_mult * st_atr[i]
        lower_band = basis - st_mult * st_atr[i]
        if not _is_value(line):
            line, trend = lower_band, 1.0
        elif trend > 0:
            line = max(lower_band, line)
            if closes[i] < line:
                trend, line = -1.0, upper_band
        else:
            line = min(upper_band, line)
            if closes[i] > line:
                trend, line = 1.0, lower_band
        supertrend[i] = line
        direction[i] = trend
    columns["supertrend"] = supertrend
    columns["supertrend_direction"] = direction

    for name, length in (("tenkan", spec.ichimoku[0]), ("kijun", spec.ichimoku[1])):
        ich_high = _extreme(highs, length, True)
        ich_low = _extreme(lows, length, False)
        line_column = _blank(n)
        for i in range(n):
            if _is_value(ich_high[i]) and _is_value(ich_low[i]):
                line_column[i] = (ich_high[i] + ich_low[i]) / 2
        columns[f"ichimoku_{name}"] = line_column

    # -- volume -------------------------------------------------------------- #
    for p in spec.volume_periods:
        columns[f"volume_sma_{p}"] = _sma(volumes, p)
        columns[f"dollar_volume_{p}"] = _sma(turnover, p)

    # This bar's volume against its own average, as a first-class quantity.
    # The language can already build `volume > volume_sma_20 * 3` -- that
    # comparison is how the only strategy with a positive 2026 result works --
    # but only ever as a comparison, never as a number a rule can bound from
    # BOTH sides. "Between two and four times normal", which is what separates
    # a climax from a listing pump, was not sayable.
    volume_ratio = _blank(n)
    average_volume = columns.get("volume_sma_20")
    if average_volume is not None:
        for i in range(n):
            if _is_value(average_volume[i]) and average_volume[i]:
                volume_ratio[i] = volumes[i] / average_volume[i]
    columns["volume_ratio_20"] = volume_ratio

    obv = _blank(n)
    running = 0.0
    for i in range(n):
        if i:
            if closes[i] > closes[i - 1]:
                running += volumes[i]
            elif closes[i] < closes[i - 1]:
                running -= volumes[i]
        obv[i] = running
    columns["obv"] = obv

    money_flow_volume = []
    for i in range(n):
        span = highs[i] - lows[i]
        multiplier = (
            0.0
            if span == 0
            else ((closes[i] - lows[i]) - (highs[i] - closes[i])) / span
        )
        money_flow_volume.append(multiplier * volumes[i])
    accumulation = _blank(n)
    running = 0.0
    for i in range(n):
        running += money_flow_volume[i]
        accumulation[i] = running
    columns["accumulation_distribution"] = accumulation

    cmf_flow = _sma(money_flow_volume, spec.cmf_period)
    cmf_volume = _sma(volumes, spec.cmf_period)
    cmf = _blank(n)
    for i in range(n):
        if _is_value(cmf_flow[i]) and _is_value(cmf_volume[i]) and cmf_volume[i]:
            cmf[i] = cmf_flow[i] / cmf_volume[i]
    columns["chaikin_money_flow"] = cmf

    positive, negative = [0.0], [0.0]
    for i in range(1, n):
        flow = typical[i] * volumes[i]
        positive.append(flow if typical[i] > typical[i - 1] else 0.0)
        negative.append(flow if typical[i] < typical[i - 1] else 0.0)
    positive_sum = _sma(positive, spec.mfi_period)
    negative_sum = _sma(negative, spec.mfi_period)
    mfi = _blank(n)
    for i in range(n):
        if _is_value(positive_sum[i]) and _is_value(negative_sum[i]):
            mfi[i] = (
                100.0
                if negative_sum[i] == 0
                else 100 - 100 / (1 + positive_sum[i] / negative_sum[i])
            )
    columns["money_flow_index"] = mfi

    force = [0.0] + [(closes[i] - closes[i - 1]) * volumes[i] for i in range(1, n)]
    columns["force_index"] = _ema(force, spec.force_period)

    vw_period = spec.volume_periods[0]
    numerator = _sma([t * v for t, v in zip(typical, volumes)], vw_period)
    denominator = _sma(volumes, vw_period)
    vwap = _blank(n)
    for i in range(n):
        if _is_value(numerator[i]) and _is_value(denominator[i]) and denominator[i]:
            vwap[i] = numerator[i] / denominator[i]
    columns["vwap_rolling"] = vwap

    return columns


def panel_for(bars: list[Bar], spec: IndicatorSpec | None = None) -> IndicatorPanel:
    spec = spec or IndicatorSpec()
    columns = _catalogue(bars, spec)
    return IndicatorPanel(
        names=tuple(columns),
        columns=columns,
        length=len(bars),
        warmup_bars=min(spec.warmup_bars(), max(len(bars) - 1, 0)),
        spec_key=spec.cache_key(),
    )


def column_names(spec: IndicatorSpec | None = None) -> tuple[str, ...]:
    """The catalogue, without a real series. Three bars is enough for shape."""
    from datetime import datetime, timedelta, timezone

    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    sample = [
        Bar(
            timestamp=start + timedelta(days=i),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
        )
        for i in range(3)
    ]
    return panel_for(sample, spec).names


def panel_from_columns(
    names: Iterable[str],
    columns: dict[str, array],
    length: int,
    warmup: int,
    key: str,
) -> IndicatorPanel:
    return IndicatorPanel(
        names=tuple(names),
        columns=columns,
        length=length,
        warmup_bars=warmup,
        spec_key=key,
    )
