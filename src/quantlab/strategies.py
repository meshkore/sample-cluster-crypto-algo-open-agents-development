from __future__ import annotations

import math
from typing import Protocol

from .models import Bar, Hypothesis


def initial_hypotheses(mode: str) -> list[Hypothesis]:
    common = {
        "research_mode": mode,
        "market_context": "liquid crypto spot",
        "regime": "all; validate by regime",
    }
    return [
        Hypothesis(
            id="H-MOM-001",
            title="Persistent return after volatility-normalized breakout",
            family="volatility_expansion",
            economic_or_behavioral_story="Slow information diffusion can continue after a range escape.",
            market_mechanism="A close above the prior range with non-extreme volatility represents information arrival rather than a one-tick breach.",
            data_required=["OHLCV"],
            features=["lagged_close_return", "prior_20_bar_high", "rolling_range"],
            trigger="close[t] > max(close[t-20:t]) and range volatility is bounded",
            entry_logic="target long after trigger; next-open fill",
            exit_logic="exit after close below 10-bar mean",
            invalidators=[
                "cost-adjusted edge <= 0",
                "parameter cliff",
                "single-regime dependence",
            ],
            time_horizon="days to weeks",
            expected_failure_modes=[
                "false breakouts",
                "crowded momentum",
                "gap execution",
            ],
            novelty_claim="Uses an explicit abstention band around unstable volatility.",
            experiments_needed=["walk-forward", "cost stress", "lookback perturbation"],
            **common,
        ),
        Hypothesis(
            id="H-REV-001",
            title="Volume-climax exhaustion reversal",
            family="volume_climax",
            economic_or_behavioral_story="Urgent one-sided flow can exhaust short-term liquidity and mean-revert.",
            market_mechanism="A large negative return on exceptional lagged volume is followed by stabilization when forced sellers are exhausted.",
            data_required=["OHLCV", "taker volume"],
            features=["lagged_return", "relative_volume", "taker_imbalance"],
            trigger="return[t] is unusually negative and volume[t] exceeds trailing baseline",
            entry_logic="target long after climax close",
            exit_logic="time stop or recovery to trailing mean",
            invalidators=[
                "continued information-driven selloff",
                "insufficient trades",
                "volume leakage",
            ],
            time_horizon="one to five bars",
            expected_failure_modes=[
                "catching falling knives",
                "regime shift",
                "bad open fill",
            ],
            novelty_claim="Requires exhaustion magnitude and a deterministic short holding period.",
            experiments_needed=[
                "crash-regime split",
                "execution delay",
                "remove best trades",
            ],
            **common,
        ),
        Hypothesis(
            id="H-ABS-001",
            title="Volatility gate for trend abstention",
            family="trade_abstention",
            economic_or_behavioral_story="Trend signals lose value in noise-dominated or panic regimes.",
            market_mechanism="Intermediate realized volatility permits price discovery while extremes represent stasis or disorder.",
            data_required=["OHLCV"],
            features=["fast_slow_mean_gap", "realized_volatility"],
            trigger="fast mean exceeds slow mean only inside volatility band",
            entry_logic="long only when trend and authorization gate agree",
            exit_logic="flat when either condition fails",
            invalidators=[
                "gate only curve-fits exposure",
                "turnover offsets benefit",
                "narrow thresholds",
            ],
            time_horizon="days",
            expected_failure_modes=[
                "volatility clustering",
                "late exits",
                "reduced sample",
            ],
            novelty_claim="Treats abstention as a separate authorization rule.",
            experiments_needed=[
                "gate ablation",
                "volatility-band perturbation",
                "regime transfer",
            ],
            **common,
        ),
        Hypothesis(
            id="H-TSM-001",
            title="Volatility-scaled trend persistence outranks a bare price breakout",
            family="trend_persistence",
            economic_or_behavioral_story=(
                "Underreaction to information makes prices drift for weeks after it "
                "arrives; time-series momentum scaled by realized volatility is the "
                "documented way that drift survives costs (Moskowitz, Ooi & Pedersen, "
                "2012), because a quiet grinding move is a better continuation signal "
                "than a single large, noisy print."
            ),
            market_mechanism=(
                "A high ratio of mean daily return to its own standard deviation "
                "over the lookback window reflects sustained one-sided demand rather "
                "than a spike that a level-breakout rule would also trigger on and "
                "then give back."
            ),
            data_required=["OHLCV"],
            features=[
                "rolling_log_return_mean",
                "rolling_log_return_std",
                "trend_t_statistic",
            ],
            trigger="the rolling t-statistic of daily log returns over the lookback clears an entry threshold",
            entry_logic=(
                "confidence rises linearly from 0 at the entry threshold to 1 at a "
                "ceiling t-statistic, unlike the other three families' flat 0/1 "
                "signal — the shared-capital allocator ranks candidates by "
                "confidence, so a graded signal should let it prefer the strongest "
                "trend among today's eligible assets instead of treating a bare "
                "pass the same as an emphatic one"
            ),
            exit_logic="flat once the t-statistic falls back under the confidence floor, or the stop-loss/take-profit brackets fire",
            invalidators=[
                "cost-adjusted edge <= 0",
                "collapses to an ordinary moving-average crossover once tuned",
                "documented mainly in strongly trending macro regimes and may not transfer to every 2017-2025 crypto regime",
            ],
            time_horizon="weeks",
            expected_failure_modes=[
                "choppy, mean-reverting regimes generate repeated near-threshold entries that get stopped out",
                "a sharp V-shaped recovery whipsaws the exit band before the position can compound",
                "lookback length is a free parameter the sweep could still curve-fit",
            ],
            novelty_claim=(
                "The first continuous-confidence signal in this codebase; the other "
                "three all return exactly 0.0 or 1.0. Also the first test of whether "
                "portfolio.py's confidence-ranked entry queue does anything when "
                "given a graded signal instead of a flat one."
            ),
            experiments_needed=[
                "walk-forward",
                "cost stress",
                "lookback perturbation",
                "head-to-head against volatility_expansion on identical folds",
            ],
            **common,
        ),
        Hypothesis(
            id="H-STA-001",
            title="SuperTrend flip, authorized only inside a strong-trend ADX regime",
            family="supertrend_adx",
            economic_or_behavioral_story=(
                "A volatility-banded trend-following stop (SuperTrend) marks *where* "
                "price has broken its recent range; ADX independently marks *whether* "
                "the market is actually trending versus chopping sideways. Neither "
                "alone is new — the pairing's claim is that gating one on the other "
                "removes the flips that fire during range-bound noise, which is "
                "where a bare SuperTrend crossover is known to whipsaw."
            ),
            market_mechanism=(
                "SuperTrend's own band (mid-price plus/minus an ATR multiple, with "
                "the band only ever tightening toward price, never loosening) flips "
                "from bearish to bullish when close breaks above it; that flip is "
                "acted on only when ADX over the same window clears a trend-strength "
                "floor, so a flip inside a directionless regime — where ADX is low — "
                "is read as noise rather than signal."
            ),
            data_required=["OHLCV"],
            features=[
                "supertrend_band",
                "supertrend_bullish_flip",
                "adx",
            ],
            trigger="close crosses above the SuperTrend band on the same bar ADX clears its threshold",
            entry_logic="target long on a bullish SuperTrend flip while ADX is above the threshold; next-open fill",
            exit_logic="flat when SuperTrend flips bearish, or the stop-loss/take-profit brackets fire — ADX gates the entry flip only, not the hold, so a position already open is not vetoed retroactively by ADX dipping while it runs",
            invalidators=[
                "cost-adjusted edge <= 0",
                "the ADX gate mainly reduces trade count without improving the survivors",
                "collapses to plain SuperTrend once the ADX threshold is tuned near zero",
            ],
            time_horizon="days",
            expected_failure_modes=[
                "ADX rises only after the move that would have been profitable has already happened, so the gate is late as often as it is protective",
                "a fast V-shaped reversal flips SuperTrend twice in quick succession, and both flips clear the ADX floor because ADX itself is still catching up from the prior move",
                "ATR multiplier and ADX threshold are two free parameters the sweep could curve-fit together",
            ],
            novelty_claim=(
                "Found as the named signal pair inside a third-party TradingView "
                "script ('0DTE Scalper v4 — Kalman SuperTrend and ADX Volatility "
                "Waves', open-source listing) and reimplemented independently from "
                "the public description alone, not the vendor source, per "
                "QUANT9. Two deliberate deviations from that script, both because "
                "they do not transfer to this lab's invariants: the '0DTE' framing "
                "is a same-day options-expiry concept with no analogue in long-only "
                "daily-bar spot, so it is dropped entirely; and the vendor's stated "
                "'Kalman' pre-filter on price is not reproduced because the public "
                "description does not specify it precisely enough to reimplement "
                "honestly — this is plain SuperTrend, not Kalman-filtered SuperTrend. "
                "The vendor's Squeeze Momentum, MACD and dynamic TP/SL layers are "
                "also dropped: SuperTrend + ADX is evaluated as its own hypothesis, "
                "not a partial port of a five-indicator system nobody here can "
                "audit end to end."
            ),
            experiments_needed=[
                "walk-forward",
                "cost stress",
                "ADX threshold and ATR multiplier perturbation",
                "ADX-gate ablation (plain SuperTrend vs SuperTrend+ADX on identical folds)",
            ],
            **common,
        ),
    ]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((x - mean) ** 2 for x in values) / (len(values) - 1))


class CausalStrategy(Protocol):
    def reset(self) -> None: ...
    def on_bar(self, observed: list[Bar]) -> float: ...


class _Momentum:
    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self) -> None:
        self.active = False

    def on_bar(self, bars: list[Bar]) -> float:
        lookback, exit_window = (
            int(self.params.get("lookback", 20)),
            int(self.params.get("exit_window", 10)),
        )
        i = len(bars) - 1
        if i < max(lookback, exit_window):
            return 0.0
        returns = [
            math.log(bars[j].close / bars[j - 1].close)
            for j in range(i - lookback + 1, i + 1)
        ]
        if bars[i].close > max(b.close for b in bars[i - lookback : i]) and _std(
            returns
        ) < float(self.params.get("max_vol", 0.04)):
            self.active = True
        elif bars[i].close < _mean([b.close for b in bars[i - exit_window : i]]):
            self.active = False
        return 1.0 if self.active else 0.0


class _Reversal:
    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self) -> None:
        self.remaining = 0

    def on_bar(self, bars: list[Bar]) -> float:
        window, holding = (
            int(self.params.get("volume_window", 20)),
            int(self.params.get("holding", 3)),
        )
        i = len(bars) - 1
        if i < window:
            return 0.0
        ret = bars[i].close / bars[i - 1].close - 1
        relative_volume = bars[i].volume / _mean(
            [b.volume for b in bars[i - window : i]]
        )
        if ret < float(
            self.params.get("return_threshold", -0.025)
        ) and relative_volume > float(self.params.get("volume_multiple", 1.5)):
            self.remaining = holding
        target = 1.0 if self.remaining > 0 else 0.0
        self.remaining = max(0, self.remaining - 1)
        return target


class _Abstention:
    def __init__(self, params):
        self.params = params

    def reset(self) -> None:
        pass

    def on_bar(self, bars: list[Bar]) -> float:
        fast, slow = int(self.params.get("fast", 8)), int(self.params.get("slow", 30))
        vol_window, i = int(self.params.get("vol_window", 15)), len(bars) - 1
        if i < max(slow, vol_window):
            return 0.0
        returns = [
            math.log(bars[j].close / bars[j - 1].close)
            for j in range(i - vol_window + 1, i + 1)
        ]
        vol = _std(returns)
        trend = _mean([b.close for b in bars[i - fast + 1 : i + 1]]) > _mean(
            [b.close for b in bars[i - slow + 1 : i + 1]]
        )
        authorized = (
            float(self.params.get("min_vol", 0.004))
            <= vol
            <= float(self.params.get("max_vol", 0.03))
        )
        return 1.0 if trend and authorized else 0.0


class _TrendPersistence:
    """Volatility-scaled time-series momentum.

    The other three families read price level (a new high, a fast/slow mean
    gap): this one reads the t-statistic of the mean daily log return over the
    lookback, so a quiet grind and a volatile spike that covers the same
    distance are no longer the same signal. Confidence is graded rather than
    binary, which matters here specifically because portfolio.py ranks same-day
    candidates by confidence when capital is scarce — a flat 0/1 signal can
    never express "this trend is stronger than that one", a graded one can.
    """

    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self) -> None:
        pass

    def on_bar(self, bars: list[Bar]) -> float:
        lookback = int(self.params.get("lookback", 30))
        i = len(bars) - 1
        if i < lookback:
            return 0.0
        window = bars[i - lookback + 1 : i + 1]
        returns = [
            math.log(window[j].close / window[j - 1].close)
            for j in range(1, len(window))
        ]
        if len(returns) < 2:
            return 0.0
        vol = _std(returns)
        if vol < 1e-9:
            return 0.0
        t_stat = (_mean(returns) / vol) * math.sqrt(len(returns))
        threshold = float(self.params.get("entry_threshold", 1.0))
        ceiling = float(self.params.get("confidence_ceiling", 3.0))
        if t_stat <= threshold:
            return 0.0
        return min(1.0, (t_stat - threshold) / max(1e-9, ceiling - threshold))


def _true_range(bars: list[Bar], i: int) -> float:
    tr = bars[i].high - bars[i].low
    if i > 0:
        tr = max(
            tr,
            abs(bars[i].high - bars[i - 1].close),
            abs(bars[i].low - bars[i - 1].close),
        )
    return tr


def _average_true_range(bars: list[Bar], i: int, period: int) -> float:
    return _mean([_true_range(bars, j) for j in range(i - period + 1, i + 1)])


def _supertrend(bars: list[Bar], i: int, period: int, multiplier: float, window: int):
    """Bullish/bearish state and same-bar flip, replayed from scratch each call.

    SuperTrend is normally computed incrementally, carrying its band forward
    bar by bar forever. This codebase's strategies are pure functions of the
    observed window instead (see _TrendPersistence), so the recursive carry
    — a band only ever tightens toward price, never loosens away from it —
    is replayed over `window` bars ending at `i` rather than over full
    history. Long enough to settle past its own start-up transient; short
    enough to stay a bounded, deterministic recompute like every other
    family here.
    """
    start = max(period, i - window + 1)
    upper = lower = None
    bullish = False
    flipped_bullish = False
    for j in range(start, i + 1):
        atr = _average_true_range(bars, j, period)
        mid = (bars[j].high + bars[j].low) / 2
        basic_upper, basic_lower = mid + multiplier * atr, mid - multiplier * atr
        if upper is None:
            upper, lower = basic_upper, basic_lower
            bullish = bars[j].close > lower
            continue
        prev_close = bars[j - 1].close
        upper = basic_upper if (basic_upper < upper or prev_close > upper) else upper
        lower = basic_lower if (basic_lower > lower or prev_close < lower) else lower
        was_bullish = bullish
        if bars[j].close > upper:
            bullish = True
        elif bars[j].close < lower:
            bullish = False
        flipped_bullish = j == i and not was_bullish and bullish
    return bullish, flipped_bullish


def _adx(bars: list[Bar], i: int, period: int, window: int) -> float:
    """Wilder's ADX, approximated with plain averages over a bounded window
    rather than his infinite-history smoothing — the same windowed-recompute
    trade-off as _supertrend above, for the same reason."""
    start = max(period + 1, i - window + 1)
    dxs = []
    for k in range(start, i + 1):
        seg_start = k - period + 1
        if seg_start < 1:
            continue
        plus_dms, minus_dms, trs = [], [], []
        for j in range(seg_start, k + 1):
            up, down = bars[j].high - bars[j - 1].high, bars[j - 1].low - bars[j].low
            plus_dms.append(up if (up > down and up > 0) else 0.0)
            minus_dms.append(down if (down > up and down > 0) else 0.0)
            trs.append(_true_range(bars, j))
        atr = _mean(trs)
        if atr < 1e-9:
            continue
        plus_di, minus_di = 100 * _mean(plus_dms) / atr, 100 * _mean(minus_dms) / atr
        denom = plus_di + minus_di
        if denom < 1e-9:
            continue
        dxs.append(100 * abs(plus_di - minus_di) / denom)
    return _mean(dxs) if dxs else 0.0


class _SuperTrendADX:
    """SuperTrend flip, acted on only inside a strong-trend ADX regime.

    See H-STA-001: the entry trigger is SuperTrend's own bullish flip: it
    fires exactly once, on the bar the band is crossed, not on every bar the
    trend happens to still be bullish — otherwise this would re-enter a
    position it never exited. ADX authorizes that flip rather than gating
    every bar, so a strong trend that started before ADX caught up is not
    retroactively vetoed once the position is already open.
    """

    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self) -> None:
        self.active = False

    def on_bar(self, bars: list[Bar]) -> float:
        atr_period = int(self.params.get("atr_period", 10))
        adx_period = int(self.params.get("adx_period", 14))
        multiplier = float(self.params.get("multiplier", 3.0))
        threshold = float(self.params.get("adx_threshold", 20.0))
        st_window = int(self.params.get("supertrend_window", 40))
        adx_window = int(self.params.get("adx_window", 30))
        i = len(bars) - 1
        if i < max(atr_period, adx_period) + 1:
            return 0.0
        bullish, flipped_bullish = _supertrend(
            bars, i, atr_period, multiplier, st_window
        )
        if not bullish:
            self.active = False
            return 0.0
        if flipped_bullish:
            self.active = _adx(bars, i, adx_period, adx_window) >= threshold
        return 1.0 if self.active else 0.0


def build_strategy(family: str, params: dict[str, float | int]) -> CausalStrategy:
    strategies = {
        "volatility_expansion": _Momentum,
        "volume_climax": _Reversal,
        "trade_abstention": _Abstention,
        "trend_persistence": _TrendPersistence,
        "supertrend_adx": _SuperTrendADX,
    }
    if family not in strategies:
        raise ValueError(f"unknown strategy family: {family}")
    return strategies[family](params)
