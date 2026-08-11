"""A deliberately small four-module system using volume, RSI and averages.

The detector and the three trading branches use the same small vocabulary but
answer different questions.  The detector measures the liquid market's
breadth; it never inspects the portfolio.  The branches decide what to own
after the market label is known.  All inputs are columns served by the frozen
backtester, so this module derives no indicators and every decision made on bar
N still fills at the open of bar N+1.

This is H-CODEX-VRMA-001.  Its fixed, round thresholds are a hypothesis, not an
optimised result.  They must be judged before 2026 and may only see the locked
forward window once if that historical gate passes.
"""

from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Any, Iterable

from .brains import register
from .policy import policy_keys
from .regime import MarketRegime
from .regime_system import FourModuleBrain, SymbolState


def _number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value else None


def _volume_ratio(candle: dict[str, Any], row: dict[str, Any]) -> float | None:
    ratio = _number(row, "volume_ratio_20")
    if ratio is not None:
        return ratio
    average = _number(row, "volume_sma_20")
    if not average or average <= 0:
        return None
    return float(candle["volume"]) / average


class BreadthRegimeDetector:
    """Classify the major regime from the current liquid universe.

    Equal-weight breadth avoids two defects in the old reference basket: a
    fixed list of today's survivors and one large coin dominating a composite.
    Five-bar confirmation is hysteresis, not lookahead: a label changes only
    after five already-closed bars have agreed.
    """

    def __init__(
        self,
        bull_breadth: float = 0.50,
        bear_breadth: float = 0.50,
        bull_rsi: float = 52.0,
        bear_rsi: float = 48.0,
        confirmation_bars: int = 5,
        minimum_assets: int = 3,
    ):
        if not 0 <= bull_breadth <= 1 or not 0 <= bear_breadth <= 1:
            raise ValueError("breadth thresholds must be in [0, 1]")
        if confirmation_bars < 1 or minimum_assets < 1:
            raise ValueError("confirmation_bars and minimum_assets must be positive")
        self.bull_breadth = float(bull_breadth)
        self.bear_breadth = float(bear_breadth)
        self.bull_rsi = float(bull_rsi)
        self.bear_rsi = float(bear_rsi)
        self.confirmation_bars = int(confirmation_bars)
        self.minimum_assets = int(minimum_assets)
        self.reset()

    def reset(self) -> None:
        self.regime = MarketRegime.UNKNOWN
        self.pending = MarketRegime.UNKNOWN
        self.pending_bars = 0
        self.episode_age = 0
        self.depth = 0.0
        self.last_bull_breadth = 0.0
        self.last_bear_breadth = 0.0
        self.last_median_rsi: float | None = None
        self.last_assets = 0
        self.observations = 0
        self.counts: Counter[str] = Counter()

    def observe(
        self,
        candles: dict[str, dict[str, Any]],
        indicators: dict[str, dict[str, Any]],
        symbols: Iterable[str],
    ) -> MarketRegime:
        bull = bear = 0
        rsis: list[float] = []
        for symbol in sorted(symbols):
            candle = candles.get(symbol)
            row = indicators.get(symbol) or {}
            if candle is None:
                continue
            fast = _number(row, "sma_50")
            slow = _number(row, "sma_200")
            rsi = _number(row, "rsi_14")
            if fast is None or slow is None or rsi is None:
                continue
            close = float(candle["close"])
            bull += close > slow and fast > slow
            bear += close < slow and fast < slow
            rsis.append(rsi)

        total = len(rsis)
        self.last_assets = total
        if total < self.minimum_assets:
            self.pending = MarketRegime.UNKNOWN
            self.pending_bars = 0
            return self.regime

        self.observations += 1
        self.last_bull_breadth = bull / total
        self.last_bear_breadth = bear / total
        self.last_median_rsi = median(rsis)
        self.depth = self.last_bear_breadth
        if (
            self.last_bull_breadth >= self.bull_breadth
            and self.last_median_rsi >= self.bull_rsi
        ):
            candidate = MarketRegime.BULL
        elif (
            self.last_bear_breadth >= self.bear_breadth
            and self.last_median_rsi <= self.bear_rsi
        ):
            candidate = MarketRegime.BEAR
        else:
            candidate = MarketRegime.SIDEWAYS

        if candidate is self.regime:
            self.pending = candidate
            self.pending_bars = 0
            self.episode_age += 1
        else:
            if candidate is self.pending:
                self.pending_bars += 1
            else:
                self.pending = candidate
                self.pending_bars = 1
            if self.pending_bars >= self.confirmation_bars:
                self.regime = candidate
                self.pending_bars = 0
                self.episode_age = 1
        self.counts[self.regime.value] += 1
        return self.regime

    def summary(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "assets": self.last_assets,
            "bull_breadth": self.last_bull_breadth,
            "bear_breadth": self.last_bear_breadth,
            "median_rsi": self.last_median_rsi,
            "episode_age": self.episode_age,
            "observations": self.observations,
            "counts": dict(self.counts),
        }

    def separation(self) -> dict[str, Any]:
        return {}


class BullVolumeRsiBranch:
    """Buy a liquid pullback only while all three averages still rise."""

    def __init__(self, params: dict[str, Any]):
        self.rsi_floor = float(params.get("bull_rsi_floor", 45.0))
        self.rsi_ceiling = float(params.get("bull_rsi_ceiling", 65.0))
        self.volume_floor = float(params.get("bull_volume_floor", 1.0))

    def evaluate(self, candle, row, state: SymbolState) -> bool:
        short = _number(row, "sma_20")
        medium = _number(row, "sma_50")
        long = _number(row, "sma_200")
        rsi = _number(row, "rsi_14")
        volume = _volume_ratio(candle, row)
        if None in (short, medium, long, rsi, volume):
            return state.active
        close = float(candle["close"])
        if state.active:
            state.active = close >= medium and rsi >= 42.0 and rsi <= 78.0
        else:
            state.active = bool(
                close > medium
                and short > medium > long
                and self.rsi_floor <= rsi <= self.rsi_ceiling
                and volume >= self.volume_floor
            )
        return state.active


class SidewaysVolumeRsiBranch:
    """Buy a participation-confirmed range low and sell at the short mean."""

    def __init__(self, params: dict[str, Any]):
        self.entry_rsi = float(params.get("sideways_entry_rsi", 35.0))
        self.exit_rsi = float(params.get("sideways_exit_rsi", 58.0))
        self.volume_floor = float(params.get("sideways_volume_floor", 1.2))

    def evaluate(self, candle, row, state: SymbolState) -> bool:
        short = _number(row, "sma_20")
        rsi = _number(row, "rsi_14")
        volume = _volume_ratio(candle, row)
        if None in (short, rsi, volume):
            return state.active
        close = float(candle["close"])
        if state.active:
            state.active = close < short and rsi < self.exit_rsi
        else:
            state.active = bool(
                close < short and rsi <= self.entry_rsi and volume >= self.volume_floor
            )
        return state.active


class BearAbsoluteStrengthBranch:
    """Stay in cash unless one asset contradicts the bear market with strength."""

    def __init__(self, params: dict[str, Any]):
        self.rsi_floor = float(params.get("bear_rsi_floor", 52.0))
        self.rsi_ceiling = float(params.get("bear_rsi_ceiling", 68.0))
        self.volume_floor = float(params.get("bear_volume_floor", 1.5))

    def evaluate(self, candle, row, state: SymbolState) -> bool:
        short = _number(row, "sma_20")
        medium = _number(row, "sma_50")
        long = _number(row, "sma_200")
        rsi = _number(row, "rsi_14")
        volume = _volume_ratio(candle, row)
        if None in (short, medium, long, rsi, volume):
            return state.active
        close = float(candle["close"])
        if state.active:
            state.active = close >= short and rsi >= 48.0
        else:
            state.active = bool(
                close > short > medium > long
                and self.rsi_floor <= rsi <= self.rsi_ceiling
                and volume >= self.volume_floor
            )
        return state.active


class BullParticipationBranch:
    """Enter established trends only when fresh volume confirms momentum."""

    def __init__(self, params: dict[str, Any]):
        self.volume_floor = float(params.get("v2_bull_volume_floor", 1.5))
        self.rsi_floor = float(params.get("v2_bull_rsi_floor", 55.0))
        self.rsi_ceiling = float(params.get("v2_bull_rsi_ceiling", 68.0))

    def evaluate(self, candle, row, state: SymbolState) -> bool:
        short = _number(row, "sma_20")
        medium = _number(row, "sma_50")
        long = _number(row, "sma_200")
        rsi = _number(row, "rsi_14")
        volume = _volume_ratio(candle, row)
        if None in (short, medium, long, rsi, volume):
            return state.active
        close = float(candle["close"])
        if state.active:
            state.active = close >= short and rsi >= 48.0
        else:
            state.active = bool(
                close > short > medium > long
                and self.rsi_floor <= rsi <= self.rsi_ceiling
                and volume >= self.volume_floor
            )
        return state.active


class SidewaysBreakoutBranch:
    """Trade the range exit, never the falling knife inside the range."""

    def __init__(self, params: dict[str, Any]):
        self.volume_floor = float(params.get("v2_sideways_volume_floor", 1.5))
        self.rsi_floor = float(params.get("v2_sideways_rsi_floor", 55.0))
        self.rsi_ceiling = float(params.get("v2_sideways_rsi_ceiling", 70.0))

    def evaluate(self, candle, row, state: SymbolState) -> bool:
        short = _number(row, "sma_20")
        medium = _number(row, "sma_50")
        rsi = _number(row, "rsi_14")
        volume = _volume_ratio(candle, row)
        previous_close = state.previous_candle.get("close")
        previous_short = _number(state.previous, "sma_20")
        if None in (short, medium, rsi, volume):
            return state.active
        close = float(candle["close"])
        if state.active:
            state.active = close >= short and rsi >= 47.0
        else:
            crossed = (
                previous_close is not None
                and previous_short is not None
                and float(previous_close) <= previous_short
                and close > short
            )
            state.active = bool(
                crossed
                and short >= medium
                and self.rsi_floor <= rsi <= self.rsi_ceiling
                and volume >= self.volume_floor
            )
        return state.active


class BearReclaimBranch:
    """Buy only an asset that reclaims its cycle average on exceptional volume."""

    def __init__(self, params: dict[str, Any]):
        self.volume_floor = float(params.get("v2_bear_volume_floor", 2.0))
        self.rsi_floor = float(params.get("v2_bear_rsi_floor", 55.0))
        self.rsi_ceiling = float(params.get("v2_bear_rsi_ceiling", 68.0))

    def evaluate(self, candle, row, state: SymbolState) -> bool:
        medium = _number(row, "sma_50")
        long = _number(row, "sma_200")
        rsi = _number(row, "rsi_14")
        volume = _volume_ratio(candle, row)
        previous_close = state.previous_candle.get("close")
        previous_long = _number(state.previous, "sma_200")
        if None in (medium, long, rsi, volume):
            return state.active
        close = float(candle["close"])
        if state.active:
            state.active = close >= medium and rsi >= 50.0
        else:
            reclaimed = (
                previous_close is not None
                and previous_long is not None
                and float(previous_close) <= previous_long
                and close > long
            )
            state.active = bool(
                reclaimed
                and medium > long
                and self.rsi_floor <= rsi <= self.rsi_ceiling
                and volume >= self.volume_floor
            )
        return state.active


@register(
    "codex-volume-rsi-regime",
    "Full-universe breadth routes simple volume, RSI and moving-average branches.",
)
class CodexVolumeRsiRegimeBrain(FourModuleBrain):
    """H-CODEX-VRMA-001: simple signals, wide liquid universe, cash-first bear."""

    def __init__(self, **params: Any):
        defaults = {
            "trade_reference": True,
            "minimum_daily_quote_volume": 10_000_000.0,
            "tradeable_assets": 100,
            "risk_per_trade": 0.01,
            "risk_distance_pct": 0.08,
            "maximum_position_fraction": 0.10,
            "maximum_concurrent_assets": 8,
            "stop_loss_pct": 0.08,
            "take_profit_pct": 0.20,
            "maximum_holding_days": 45,
            "maximum_drawdown": 0.30,
            "drawdown_deleverage_start": 0.10,
            "drawdown_deleverage_end": 0.25,
            "drawdown_basis": "peak",
        }
        merged = {**defaults, **params}
        super().__init__(**merged)
        self.params = merged
        self.detector = BreadthRegimeDetector(
            bull_breadth=float(merged.get("detector_bull_breadth", 0.50)),
            bear_breadth=float(merged.get("detector_bear_breadth", 0.50)),
            bull_rsi=float(merged.get("detector_bull_rsi", 52.0)),
            bear_rsi=float(merged.get("detector_bear_rsi", 48.0)),
            confirmation_bars=int(merged.get("detector_confirmation_bars", 5)),
            minimum_assets=int(merged.get("detector_minimum_assets", 3)),
        )
        self.rule_names = {
            MarketRegime.BULL: "volume-rsi-trend",
            MarketRegime.SIDEWAYS: "volume-rsi-reversion",
            MarketRegime.BEAR: "volume-rsi-absolute-strength",
        }
        self.branches = {
            MarketRegime.BULL: BullVolumeRsiBranch(merged),
            MarketRegime.SIDEWAYS: SidewaysVolumeRsiBranch(merged),
            MarketRegime.BEAR: BearAbsoluteStrengthBranch(merged),
        }
        self.weights = {
            MarketRegime.BULL: float(merged.get("bull_weight", 1.0)),
            MarketRegime.SIDEWAYS: float(merged.get("sideways_weight", 0.70)),
            MarketRegime.BEAR: float(merged.get("bear_weight", 0.50)),
        }
        self.reset()

    def _observe_market(self, moment, candles, indicators) -> MarketRegime:
        del moment
        symbols = self.universe.tradeable(indicators)
        return self.detector.observe(candles, indicators, symbols)

    def _permitted(self, market: MarketRegime) -> bool:
        return market is not MarketRegime.UNKNOWN

    def parameters(self) -> dict[str, Any]:
        described = {
            key: value
            for key, value in sorted(self.params.items())
            if isinstance(value, (int, float, str, bool, type(None)))
            and key not in policy_keys()
        }
        described["hypothesis"] = "H-CODEX-VRMA-001"
        described["detector"] = "liquid-universe-ma-breadth-rsi"
        return described

    def diagnostics(self) -> dict[str, Any]:
        return {
            "hypothesis": "H-CODEX-VRMA-001",
            "rules": {regime.value: name for regime, name in self.rule_names.items()},
            "weights": {
                regime.value: weight for regime, weight in self.weights.items()
            },
            "policy": {key: getattr(self.policy, key) for key in policy_keys()},
            "universe": self.universe.describe(),
            "detector": self.detector.summary(),
        }


@register(
    "codex-volume-rsi-regime-v2",
    "Breadth-routed volume/RSI/MA continuation with a cash-first bear reclaim.",
)
class CodexVolumeRsiRegimeV2Brain(CodexVolumeRsiRegimeBrain):
    """H-CODEX-VRMA-002: remove dip buying and bound correlated gap risk."""

    def __init__(self, **params: Any):
        defaults = {
            "risk_per_trade": 0.005,
            "risk_distance_pct": 0.10,
            "maximum_position_fraction": 0.05,
            "minimum_position_fraction": 0.02,
            "maximum_concurrent_assets": 6,
            "stop_loss_pct": 0.12,
            "take_profit_pct": 0.20,
            "maximum_holding_days": 30,
        }
        merged = {**defaults, **params}
        super().__init__(**merged)
        self.params = merged
        self.rule_names = {
            MarketRegime.BULL: "volume-rsi-participation",
            MarketRegime.SIDEWAYS: "volume-rsi-breakout",
            MarketRegime.BEAR: "volume-rsi-cycle-reclaim",
        }
        self.branches = {
            MarketRegime.BULL: BullParticipationBranch(merged),
            MarketRegime.SIDEWAYS: SidewaysBreakoutBranch(merged),
            MarketRegime.BEAR: BearReclaimBranch(merged),
        }
        self.weights = {
            MarketRegime.BULL: float(merged.get("bull_weight", 1.0)),
            MarketRegime.SIDEWAYS: float(merged.get("sideways_weight", 0.70)),
            MarketRegime.BEAR: float(merged.get("bear_weight", 0.50)),
        }
        self.reset()

    def parameters(self) -> dict[str, Any]:
        described = super().parameters()
        described["hypothesis"] = "H-CODEX-VRMA-002"
        described["implementation_version"] = 2
        return described

    def diagnostics(self) -> dict[str, Any]:
        described = super().diagnostics()
        described["hypothesis"] = "H-CODEX-VRMA-002"
        return described
