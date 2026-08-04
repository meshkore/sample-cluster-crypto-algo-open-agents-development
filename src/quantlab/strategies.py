from __future__ import annotations

import math
from typing import Protocol

from .hmm_regime import GaussianHMM
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
            id="H-REGIME-001",
            title="Regime-gated long-only via dependency-free Gaussian HMM",
            family="regime_gated",
            economic_or_behavioral_story=(
                "Crypto markets alternate between persistent bull/bear/range "
                "regimes; a Gaussian HMM fitted on daily log-returns recovers "
                "the current regime, and gating long entries on the smoothed "
                "bull posterior cuts the whipsaw trades that bare momentum "
                "signals take near transitions."
            ),
            market_mechanism=(
                "Regime persistence is a real, measurable property of crypto "
                "spot (bull and bear legs last weeks); the HMM posterior is a "
                "causal, smoothed probability of being in each regime, so a "
                "long entry authorized only above a bull-posterior threshold "
                "with a minimum dwell filters transition noise without "
                "lookahead."
            ),
            data_required=["OHLCV"],
            features=[
                "log_return",
                "hmm_bull_posterior",
                "regime_dwell",
            ],
            trigger="smoothed bull posterior exceeds entry threshold with dwell >= minimum_dwell",
            entry_logic=(
                "long when bull posterior > 0.55 AND dwell >= 3; signal "
                "confidence is the continuous smoothed posterior, so the "
                "shared-capital allocator ranks regime conviction against "
                "other families instead of a flat 0/1 gate"
            ),
            exit_logic=(
                "flat when smoothed bull posterior < 0.45, or the "
                "stop-loss/take-profit brackets fire"
            ),
            invalidators=[
                "cost-adjusted edge <= 0 after slippage 5bps + commission 10bps",
                "regime calls do not beat unconditional benchmark in 2026 forward",
                "collapses to buy-and-hold in bull-heavy samples",
            ],
            time_horizon="weeks",
            expected_failure_modes=[
                "regime flicker on short timeframes",
                "EM degeneracy (state collapse) without k-means init",
                "regime labels sticky near transitions (false confidence)",
                "walk-forward overfit on dwell/threshold",
            ],
            novelty_claim=(
                "First strategy family in this codebase driven by a "
                "dependency-free Gaussian HMM (Baum-Welch EM, k-means++ "
                "init, stdlib-only); continuous smoothed-posterior confidence "
                "implements regime-confident decay weighting."
            ),
            experiments_needed=[
                "walk-forward",
                "cost stress",
                "head-to-head against volume_climax on identical folds",
                "dwell/threshold perturbation",
                "regime-conditional return decomposition",
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


class _RegimeGated:
    """Regime-gated long-only via a dependency-free Gaussian HMM.

    A 3-state Gaussian HMM (stdlib-only, k-means++ init, Baum-Welch EM) is
    refit periodically on the trailing log-returns; the smoothed bull
    posterior of the *latest* bar is the signal. The gate is the continuous
    posterior itself (not a 0/1 label), so near-transition bars are
    down-weighted instead of snapped on/off — the regime-confidence decay
    weighting suggested by the QuantLab reviewers. A minimum-dwell counter
    suppresses flicker.
    """

    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self) -> None:
        self._last_fit = 0
        self._dwell = 0
        self._model = None

    def on_bar(self, bars: list[Bar]) -> float:
        fit_window = int(self.params.get("fit_window", 120))
        refit_every = int(self.params.get("refit_every", 20))
        entry_threshold = float(self.params.get("entry_threshold", 0.55))
        exit_threshold = float(self.params.get("exit_threshold", 0.45))
        min_dwell = int(self.params.get("min_dwell", 3))
        n_states = int(self.params.get("n_states", 3))
        seed = int(self.params.get("seed", 42))

        i = len(bars) - 1
        if i < fit_window:
            return 0.0
        window = bars[i - fit_window + 1 : i + 1]
        closes = [b.close for b in window]
        # Refit periodically (not every bar) to keep the loop cheap; the
        # HMM itself is deterministic under the seeded RNG.
        if self._model is None or (i - self._last_fit) >= refit_every:
            model = GaussianHMM(n_states=n_states, seed=seed).fit(closes)
            self._model = model.sorted_by_mean()
            self._last_fit = i
        post = self._model.posterior(closes)
        bull = post[-1][2]  # index 2 == highest-mean state after sorting
        # Minimum dwell: only commit once bull has persisted a few bars.
        if bull >= exit_threshold:
            self._dwell += 1
        else:
            self._dwell = 0
        if self._dwell < min_dwell:
            return 0.0
        if bull < entry_threshold:
            return 0.0
        return min(1.0, bull)


def build_strategy(family: str, params: dict[str, float | int]) -> CausalStrategy:
    strategies = {
        "volatility_expansion": _Momentum,
        "volume_climax": _Reversal,
        "trade_abstention": _Abstention,
        "trend_persistence": _TrendPersistence,
        "regime_gated": _RegimeGated,
    }
    if family not in strategies:
        raise ValueError(f"unknown strategy family: {family}")
    return strategies[family](params)
