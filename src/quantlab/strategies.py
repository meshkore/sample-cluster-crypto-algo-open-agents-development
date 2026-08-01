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


def build_strategy(family: str, params: dict[str, float | int]) -> CausalStrategy:
    strategies = {
        "volatility_expansion": _Momentum,
        "volume_climax": _Reversal,
        "trade_abstention": _Abstention,
    }
    if family not in strategies:
        raise ValueError(f"unknown strategy family: {family}")
    return strategies[family](params)
