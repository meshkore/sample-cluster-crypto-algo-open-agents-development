from __future__ import annotations

import math
from typing import Any, Protocol

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
        Hypothesis(
            id="H-DONCH-001",
            title="Donchian channel breakout, long side only (Turtle Trading)",
            family="donchian_breakout",
            economic_or_behavioral_story=(
                "A close making a new N-bar high reflects either genuine new "
                "information or a real shift in the supply/demand balance, and "
                "crypto's momentum literature attributes unusually long and "
                "persistent trend runs to a market still dominated by noise "
                "traders relative to informed ones. A breakout system is the "
                "simplest possible bet on that persistence continuing."
            ),
            market_mechanism=(
                "Long when close breaks above the highest high of the prior "
                "N bars (excluding the current bar); flat again once close "
                "breaks below the lowest low of the prior M bars, with M < N "
                "so the system exits faster than it enters. This is the "
                "long side of the 1980s Turtle Trading system (Richard "
                "Dennis and William Eckhardt), still the standard textbook "
                "reference for trend-following breakout systems and still "
                "used as the baseline case in recent crypto trend-following "
                "literature."
            ),
            data_required=["OHLCV"],
            features=["donchian_upper_breakout", "donchian_lower_breakout"],
            trigger="close closes above the highest high of the prior N bars",
            entry_logic="target long on a fresh N-bar high; next-bar-open fill",
            exit_logic="flat once close breaks below the lowest low of the prior M bars (M<N) — a shallower pullback that does not clear M-bar lows does not close the position",
            invalidators=[
                "cost-adjusted edge <= 0",
                "collapses to noise once N is small enough that breakouts fire on ordinary volatility rather than a genuine trend",
                "the N/M asymmetry is itself a tunable pair the sweep could curve-fit",
            ],
            time_horizon="days to weeks",
            expected_failure_modes=[
                "range-bound regimes generate repeated false breakouts (whipsaw) -- breakout systems' best-known weakness",
                "edge may concentrate in a few strongly trending years rather than holding evenly across the whole period",
                "the original system's short side is reported (secondary sources, not verified here) to lose money on Bitcoin, which is why this hypothesis only takes the long side -- but the long side's own reported edge is equally unverified until this lab's own pipeline runs it",
            ],
            novelty_claim=(
                "Not novel: this is the textbook Donchian/Turtle breakout, "
                "originated by Richard Dennis and William Eckhardt (1983) and "
                "still cited as a baseline trend-following mechanism in recent "
                "crypto momentum literature (e.g. arXiv 2009.12155, 'A Decade "
                "of Evidence of Trend Following Investing in Cryptocurrencies'). "
                "Found via a deliberate search for a mechanism with public, "
                "well-scrutinized methodology rather than an undisclosed "
                "vendor script, per the operator's request following QUANT9. "
                "The original system's ATR-sized pyramiding is not "
                "reproduced: this lab's shared portfolio engine already owns "
                "position sizing and stops centrally, and every strategy here "
                "emits a plain 0-1 signal rather than sizing itself."
            ),
            experiments_needed=[
                "walk-forward",
                "cost stress",
                "entry/exit period (N/M) perturbation",
                "regime breakdown: trending vs range-bound years",
            ],
            **common,
        ),
        Hypothesis(
            id="H-MULTI-001",
            title="Trend + momentum + order-flow majority vote",
            family="multi_factor_trend",
            economic_or_behavioral_story=(
                "No single well-known factor here (trend, momentum, volume) "
                "has cleared this lab's bar alone across nine prior "
                "hypotheses. Combining three independent, individually "
                "well-established factor families into a majority vote is "
                "the standard next move in factor investing once single "
                "factors have been exhausted: false signals in one factor "
                "are diluted by requiring agreement from a second, "
                "uncorrelated one, at the cost of never being as decisive "
                "as a single strict filter."
            ),
            market_mechanism=(
                "Three causal, independently computed votes each bar: (1) "
                "trend -- close above its N-bar SMA and that SMA still "
                "rising; (2) momentum -- RSI above a floor; (3) order-flow "
                "imbalance -- the taker-buy-volume share of total volume, "
                "averaged over a short window, exceeding its own longer-"
                "window baseline. Long when at least 2 of 3 agree; the "
                "position is not closed on a single flickering factor, only "
                "when all 3 turn against it -- the same asymmetric entry/"
                "exit principle H-DONCH-001 already established here, "
                "applied to a vote count instead of a channel width."
            ),
            data_required=["OHLCV", "taker_buy_volume"],
            features=["sma_slope", "rsi", "taker_buy_ratio_vs_baseline"],
            trigger="at least 2 of 3 factor votes (trend, momentum, order-flow) agree bullish",
            entry_logic="target long once >=2 of 3 votes agree; next-bar-open fill",
            exit_logic="flat only once all 3 votes turn against the position (0 of 3) -- 1 or 2 dissenting votes alone do not close it",
            invalidators=[
                "cost-adjusted edge <= 0",
                "the 3 votes are not actually independent (RSI and SMA slope both derive from the same price series), so the 'majority vote' may be diluting noise less than it looks",
                "trading on 2-of-3 rather than requiring consensus increases trade count at the direct cost of the per-trade edge -- more trades is not itself evidence of a better strategy",
            ],
            time_horizon="days to weeks",
            expected_failure_modes=[
                "taker_buy_volume is a coarse, OHLCV-level proxy for aggressor imbalance, not real order-book depth or actual market-maker positioning -- there is no L2 data in this pipeline, so this factor may simply be adding noise dressed up as a signal",
                "regime transitions where trend and momentum flip together but order-flow lags (or vice versa) could produce whipsaw exactly at turning points",
                "the asymmetric exit (0-of-3 required) borrowed from H-DONCH-001 may hold losing positions too long if it turns out that lesson does not transfer from a single-factor breakout system to a multi-factor vote",
            ],
            novelty_claim=(
                "Not novel as a concept -- multi-factor combination is a "
                "standard technique once single factors are exhausted "
                "(factor investing, ensemble trading systems). Built after a "
                "deliberate operator request to stop testing single "
                "isolated factors and combine this lab's own established, "
                "individually-tested factor families (trend, momentum, "
                "volume/order-flow) into one candidate, rather than search "
                "for one more untested external mechanism. No machine-"
                "learning model is used: a fitted classifier over these "
                "same features was considered and deliberately rejected for "
                "this first pass, since this lab's causal-replay engine has "
                "no train/inference split to fit one without a real risk of "
                "look-ahead leakage that a fixed-rule vote does not carry. "
                "A learned combiner remains a reasonable next step if this "
                "rule-based version clears Phase 1."
            ),
            experiments_needed=[
                "walk-forward",
                "cost stress",
                "vote-threshold perturbation (2-of-3 vs 3-of-3)",
                "factor ablation: each of the 3 factors alone vs the vote, on identical folds",
            ],
            **common,
        ),
        Hypothesis(
            id="H-REGIME-001",
            title="Regime-switching: trend-following in bull markets, oversold bounces in bear markets",
            family="regime_switching",
            economic_or_behavioral_story=(
                "A single rule applied uniformly across bull and bear "
                "markets fights its own mechanism half the time: trend-"
                "following whipsaws in a downtrend, and mean-reversion "
                "fades a real bull run. Splitting the decision into 'what "
                "regime is this' first, then a *different* rule per regime, "
                "is the standard way real systematic desks avoid forcing "
                "one mechanism to do two jobs — directly evolving H-MULTI-"
                "001 per the operator's explicit request for a two-part "
                "bull/bear structure rather than a single blended vote."
            ),
            market_mechanism=(
                "The 200-bar SMA and its own slope is the textbook regime "
                "filter: bull when close sits above a rising 200-bar SMA, "
                "bear otherwise. Inside a bull regime, a short-term trend + "
                "momentum confirmation opens a full-confidence long, held "
                "until both turn against it. Inside a bear regime, the "
                "system does not simply go flat: it takes a smaller, "
                "explicitly lower-confidence long only on a sharp RSI "
                "oversold reading (a bounce trade, not a trend trade), "
                "closed once RSI recovers to neutral. A position from "
                "either branch is closed immediately if the regime itself "
                "flips — the regime call overrides whichever sub-signal is "
                "currently open."
            ),
            data_required=["OHLCV"],
            features=["regime_sma_slope", "trend_confirmation", "rsi_oversold_bounce"],
            trigger="200-bar SMA regime call, then a regime-specific entry rule",
            entry_logic="bull regime: full-confidence long on trend+momentum agreement; bear regime: reduced-confidence long only on RSI oversold",
            exit_logic="a position closes if the regime itself flips (regime overrides the open sub-signal), or its own branch's exit fires (bull: trend and momentum both turn; bear: RSI recovers to neutral), or the stop-loss/take-profit brackets fire",
            invalidators=[
                "cost-adjusted edge <= 0",
                "the 200-bar regime filter itself lags real turning points by design, so both branches can be acting on a stale regime call right at the transition",
                "the bear-regime bounce branch is exactly the exhaustion-reversal mechanism (H-REV-001) already tested here and not yet promoted -- if it failed standalone, wrapping it in a regime filter does not automatically fix it",
            ],
            time_horizon="days to weeks",
            expected_failure_modes=[
                "whipsaw at regime transitions: both branches can open and immediately close a position around the same few bars where the 200-bar SMA call is genuinely ambiguous",
                "the reduced bear-regime confidence (0.5) is a hand-set number, not fitted -- an arbitrary risk dial dressed up as money management",
                "still a bigger backtest number here is not evidence it survives 2026 forward or a real market -- it is the same claim H-MULTI-001 made, now with a second moving part instead of one",
            ],
            novelty_claim=(
                "Not novel as a technique: regime-conditional systems (trade "
                "differently above/below a long moving average) are a "
                "standard part of systematic trading, not a discovery. "
                "Built as a direct evolution of H-MULTI-001, per the "
                "operator's explicit request the same day: identify the "
                "major bull/bear trend explicitly and give each its own "
                "rule, rather than one blended vote for both. H-MULTI-001 "
                "itself is left as its own recorded result, not silently "
                "replaced -- this is a second, distinct hypothesis to "
                "compare against it, not an edit to what was already run."
            ),
            experiments_needed=[
                "walk-forward",
                "cost stress",
                "regime-filter period perturbation (100/150/200/250 bars)",
                "head-to-head against H-MULTI-001 and against H-REV-001 alone on identical folds",
            ],
            **common,
        ),
        Hypothesis(
            id="H-SMARSI-001",
            title="Hourly moving-average trend with an RSI momentum gate",
            family="sma_rsi_trend",
            economic_or_behavioral_story=(
                "Deliberately the simplest complete rule in this lab: two "
                "moving averages and one RSI. It exists to separate two "
                "questions that every result here has so far confounded — "
                "'does the machinery execute trades on candle data' and "
                "'does the signal have edge'. A rule this plain has no room "
                "left to hide an implementation fault, so whatever it "
                "produces is attributable to the signal and to money "
                "management, not to indicator complexity. It is also the "
                "baseline any more elaborate family must beat to justify "
                "its extra moving parts; none of the eight families tested "
                "before it were ever measured against a floor this low."
            ),
            market_mechanism=(
                "Three conditions, all required to open: (1) the fast SMA is "
                "above the slow SMA, the classic trend state; (2) RSI is "
                "above a floor, so momentum confirms rather than contradicts "
                "the trend; (3) close is above the fast SMA, so price itself "
                "confirms instead of the averages alone. Confidence is "
                "binary 1.0 — the signal decides direction only, and every "
                "sizing decision is left entirely to the money-management "
                "layer (volatility target, risk per trade, position cap, "
                "stop/target brackets, volume participation). That "
                "separation is the point: a graded confidence would let a "
                "policy's minimum-confidence threshold silently veto entries "
                "and be mistaken for the signal failing."
            ),
            data_required=["OHLCV"],
            features=["sma_fast", "sma_slow", "rsi"],
            trigger="fast SMA above slow SMA, RSI above its floor, and close above the fast SMA",
            entry_logic="open at full confidence only when all three conditions hold simultaneously",
            exit_logic="close when the fast SMA falls back below the slow SMA (trend gone) or RSI exceeds its ceiling (momentum exhausted), or the money-management stop-loss/take-profit brackets fire",
            invalidators=[
                "cost-adjusted edge <= 0: at hourly resolution a moving-average cross fires often enough that commission and slippage, not direction, can decide the outcome",
                "if a parameter sweep only produces a positive result at one narrow corner of the grid, that is a fitted artifact and not an edge",
                "moving-average crossovers are among the most widely published and most heavily arbitraged rules in existence; the prior that a bare one has surviving edge is low, and that prior is the honest starting position here",
            ],
            time_horizon="hours to days",
            expected_failure_modes=[
                "whipsaw in ranging markets: the cross flips repeatedly and every flip pays costs in both directions",
                "the RSI ceiling exits the strongest part of a real trend precisely because it is strong, capping the upside that would pay for the whipsaw losses",
                "hourly candles multiply trade count by roughly 24x against the daily universe, which raises statistical confidence and total cost drag at the same time",
            ],
            novelty_claim=(
                "Zero novelty, claimed as a feature rather than hidden: an "
                "SMA cross with an RSI filter is textbook material and is "
                "almost certainly already arbitraged. It is built here as a "
                "measurable baseline and as the object of a parameter search, "
                "because a search needs a small parameter space to mean "
                "anything, and because the operator's own point stands — a "
                "system this simple should demonstrably fire hundreds of "
                "trades on real candles, and if this lab cannot show that, "
                "the problem was never the strategy."
            ),
            experiments_needed=[
                "parameter sweep over fast/slow SMA and the RSI band on pre-2026 data only",
                "walk-forward",
                "cost stress at 2x and 4x commission",
                "head-to-head against buy-and-hold on the identical hourly window",
            ],
            **common,
        ),
        Hypothesis(
            id="H-ROUTER-001",
            title="Market-wide regime detector routing three independently tunable branches",
            family="regime_router",
            economic_or_behavioral_story=(
                "The operator's four-piece design: name the major trend "
                "first, then run a rule chosen for that trend, so each piece "
                "can be improved without disturbing the others. The regime "
                "call is market-wide -- a composite of six long-history "
                "majors plus breadth -- and never the traded asset's own "
                "chart, which is what separates it from H-REGIME-001 "
                "(QUANT12): that one filtered each asset by its own 200-bar "
                "SMA and consequently traded 8 assets out of 386."
            ),
            market_mechanism=(
                "A causal BULL/SIDEWAYS/BEAR label with hysteresis gates "
                "which of three branches is live. Bull runs the H-SMARSI-001 "
                "trend rule; sideways runs Kotegawa's 25-day deviation-rate "
                "reversion; bear runs a strict confirmed-advance rule and "
                "never buys weakness. Each branch reads its own parameter "
                "prefix and each regime carries an exposure weight, so the "
                "detector, the three rules and the exposure policy are four "
                "separately searchable objects rather than one blended one."
            ),
            data_required=["OHLCV", "reference basket OHLCV"],
            features=["composite_index", "breadth", "regime_label"],
            trigger="the live branch's own entry condition, evaluated only while its regime holds",
            entry_logic="open at the branch's confidence scaled by that regime's exposure weight",
            exit_logic="the branch's own exit, or a forced flat bar whenever the regime label changes",
            invalidators=[
                "measured, and currently failing: on the pre-2026 five-asset hourly basket the router returns +211.2% against the single trend rule's +432.4% at the same drawdown, so routing subtracts rather than adds",
                "gating the control by regime is efficiency-neutral (39.6 against 37.9 return per unit exposure), which says the labels do not concentrate return into the good regimes",
                "the cycle sample is 2-3 tops and bottoms in the whole Binance era, so any search over the detector's own parameters is fitting a handful of events no matter how many bars it sweeps",
                "the reference basket is survivorship-biased: all six constituents are still listed, so the composite tilts toward BULL",
            ],
            time_horizon="hours to weeks, with regime episodes lasting months",
            expected_failure_modes=[
                "the trend-following regime call arrives late by construction, so BULL collects the end of advances -- measured: SIDEWAYS outranks BULL on forward return",
                "two of the three branches are weaker rules than the one they displace, so every hour spent in them is a worse hour of trading",
                "the deviation branch is high-efficiency but low-capacity: 164 trades in nine years across five majors, because a 25% collapse below the 25-day average is rare in a narrow universe",
                "switching costs a forced flat bar at every handover, which is paid whether or not the new regime is right",
            ],
            novelty_claim=(
                "No novelty in the components -- a 200-period trend filter, "
                "a breakout, a moving-average deviation -- and none claimed. "
                "What is new here is that the regime call is a separately "
                "scored artifact with its own scorecard rather than a hidden "
                "term inside a strategy, so 'the regime was right' becomes a "
                "checkable statement."
            ),
            experiments_needed=[
                "per-branch parameter sweep at the declared basket scope, one branch at a time",
                "walk-forward",
                "head-to-head against H-SMARSI-001 on identical bars, costs and policy",
                "detector parameter perturbation (trend 150/200/250, confirmation 10/20/40)",
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


class _DonchianBreakout:
    """H-DONCH-001: the long side of the classic Turtle Trading breakout.

    Enter on a fresh N-bar high, exit on a fresh M-bar low (M<N). The
    asymmetry is the point: a shallower pullback than an M-bar low must not
    close a position a genuine N-bar breakout opened, or this collapses into
    a much noisier system that exits on every minor dip.
    """

    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self) -> None:
        self.active = False

    def on_bar(self, bars: list[Bar]) -> float:
        entry_period = int(self.params.get("entry_period", 20))
        exit_period = int(self.params.get("exit_period", 10))
        i = len(bars) - 1
        if i < entry_period:
            return 0.0
        close = bars[i].close
        entry_window = bars[max(0, i - entry_period) : i]
        upper = max(bar.high for bar in entry_window)
        if close > upper:
            self.active = True
        if self.active:
            exit_window = bars[max(0, i - exit_period) : i]
            lower = min(bar.low for bar in exit_window) if exit_window else close
            if close < lower:
                self.active = False
        return 1.0 if self.active else 0.0


def _sma(bars: list[Bar], i: int, period: int) -> float:
    window = bars[max(0, i - period + 1) : i + 1]
    return _mean([bar.close for bar in window])


def _rsi(bars: list[Bar], i: int, period: int) -> float:
    window = bars[max(0, i - period) : i + 1]
    gains = losses = 0.0
    for previous, current in zip(window, window[1:]):
        change = current.close - previous.close
        if change > 0:
            gains += change
        else:
            losses += -change
    steps = len(window) - 1
    if steps <= 0:
        return 50.0
    avg_gain, avg_loss = gains / steps, losses / steps
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def _taker_ratio(bars: list[Bar], i: int, period: int) -> float:
    """Share of volume on the taker-buy side, averaged over `period` bars.

    The only aggressor-imbalance proxy available from public OHLCV klines --
    not real order-book depth, not literal market-maker positioning.
    """
    window = bars[max(0, i - period + 1) : i + 1]
    ratios = [
        bar.taker_buy_volume / bar.volume
        for bar in window
        if bar.taker_buy_volume is not None and bar.volume
    ]
    return _mean(ratios) if ratios else 0.5


class _MultiFactorTrend:
    """H-MULTI-001: majority vote across trend, momentum, and order-flow.

    Entry needs >=2 of 3 votes; once open, the position survives any single
    dissenting factor and closes only once all 3 turn against it -- the
    same asymmetric entry/exit principle as H-DONCH-001 (_DonchianBreakout),
    applied to a vote count instead of a channel width.
    """

    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self) -> None:
        self.active = False

    def on_bar(self, bars: list[Bar]) -> float:
        trend_period = int(self.params.get("trend_period", 50))
        rsi_period = int(self.params.get("rsi_period", 14))
        flow_short = int(self.params.get("flow_short_period", 5))
        flow_long = int(self.params.get("flow_long_period", 20))
        rsi_floor = float(self.params.get("rsi_floor", 50.0))
        min_votes = int(self.params.get("min_votes", 2))
        i = len(bars) - 1
        warmup = max(trend_period, rsi_period, flow_long + flow_short)
        if i < warmup:
            return 0.0
        trend_up = (
            bars[i].close
            > _sma(bars, i, trend_period)
            > _sma(bars, i - 1, trend_period)
        )
        momentum_up = _rsi(bars, i, rsi_period) > rsi_floor
        flow_up = _taker_ratio(bars, i, flow_short) > _taker_ratio(
            bars, i - flow_short, flow_long
        )
        votes = int(trend_up) + int(momentum_up) + int(flow_up)
        if votes >= min_votes:
            self.active = True
        elif votes == 0:
            self.active = False
        return (votes / 3.0) if self.active else 0.0


class _RegimeSwitching:
    """H-REGIME-001: a 200-bar SMA regime call gates two different rules --
    full-confidence trend+momentum in a bull regime, reduced-confidence RSI
    oversold bounces in a bear regime. The regime call itself overrides
    whichever sub-signal is currently open: a bull trend position does not
    ride into a confirmed bear regime, and a bear bounce does not linger
    once the regime turns bullish again.
    """

    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self) -> None:
        self.active = False
        self.mode: str | None = None

    def on_bar(self, bars: list[Bar]) -> float:
        regime_period = int(self.params.get("regime_period", 200))
        trend_period = int(self.params.get("trend_period", 20))
        rsi_period = int(self.params.get("rsi_period", 14))
        oversold = float(self.params.get("oversold_rsi", 30.0))
        bull_confidence = float(self.params.get("bull_confidence", 1.0))
        bear_confidence = float(self.params.get("bear_confidence", 0.5))
        i = len(bars) - 1
        warmup = max(regime_period, trend_period, rsi_period) + 1
        if i < warmup:
            return 0.0
        bull_regime = (
            bars[i].close
            > _sma(bars, i, regime_period)
            > _sma(bars, i - 1, regime_period)
        )
        rsi = _rsi(bars, i, rsi_period)

        if bull_regime:
            if self.mode == "bear":
                self.active, self.mode = False, None
            trend_up = (
                bars[i].close
                > _sma(bars, i, trend_period)
                > _sma(bars, i - 1, trend_period)
            )
            momentum_up = rsi > 50.0
            if not self.active and trend_up and momentum_up:
                self.active, self.mode = True, "bull"
            elif self.mode == "bull" and not trend_up and not momentum_up:
                self.active, self.mode = False, None
        else:
            if self.mode == "bull":
                self.active, self.mode = False, None
            if not self.active and rsi < oversold:
                self.active, self.mode = True, "bear"
            elif self.mode == "bear" and rsi > 50.0:
                self.active, self.mode = False, None

        if not self.active:
            return 0.0
        return bull_confidence if self.mode == "bull" else bear_confidence


class _SMARSITrend:
    """H-SMARSI-001: two moving averages and one RSI -- nothing else.

    Three conditions, all required to enter; two, either sufficient, to
    exit. Confidence is binary 1.0 rather than graded, which is a deliberate
    choice and not a simplification: a graded signal is multiplied by the
    money-management layer's `minimum_confidence` threshold, so a policy
    demanding 0.75 silently vetoes a 0.667 signal and the strategy looks
    inert when it is actually being blocked. Emitting 1.0 puts every sizing
    decision where it belongs -- in money management -- and makes this
    family's trade count a measurement of the signal alone.
    """

    def __init__(self, params):
        self.params = params
        self.reset()

    def reset(self) -> None:
        self.active = False

    def on_bar(self, bars: list[Bar]) -> float:
        fast_period = int(self.params.get("fast_period", 20))
        slow_period = int(self.params.get("slow_period", 50))
        rsi_period = int(self.params.get("rsi_period", 14))
        rsi_floor = float(self.params.get("rsi_floor", 50.0))
        rsi_ceiling = float(self.params.get("rsi_ceiling", 75.0))
        i = len(bars) - 1
        if i < max(fast_period, slow_period, rsi_period):
            return 0.0
        fast = _sma(bars, i, fast_period)
        slow = _sma(bars, i, slow_period)
        rsi = _rsi(bars, i, rsi_period)
        trend_up = fast > slow
        if self.active:
            # Exit is asymmetric with entry -- the position survives losing
            # the price confirmation and closes only on the trend itself
            # turning or momentum running out, so an ordinary pullback
            # inside a live trend does not churn the position.
            if not trend_up or rsi > rsi_ceiling:
                self.active = False
        elif trend_up and rsi_floor < rsi <= rsi_ceiling and bars[i].close > fast:
            # Entry requires RSI inside the band, not merely above the floor.
            # Testing only the floor makes the ceiling exit self-defeating: a
            # strong trend pins RSI above the ceiling, so the position closes
            # and the very next bar re-opens it, paying costs on every bar for
            # no change in exposure.
            self.active = True
        return 1.0 if self.active else 0.0


# The control. Every candidate is measured against this exact configuration
# under identical bars, costs and money management, so the difference is
# attributable to the signal and nothing else.
#
# Nine families were evaluated in this laboratory with no control at all, and
# the result was nine absolute numbers that could not be compared to anything:
# "+36.97% Phase-1" from a three-factor vote had no interpretation, because
# nobody could say whether the three factors earned it or whether two moving
# averages under the same policy would have produced the same curve. An
# absolute return measures the signal, the policy, the market regime and the
# asset selection at once. A difference against a fixed control measures the
# signal.
#
# H-SMARSI-001 is the control precisely because it is the least interesting
# rule available: two SMAs and one RSI, zero novelty claimed. A candidate that
# cannot beat it has not earned its extra moving parts.
BASELINE_FAMILY = "sma_rsi_trend"
BASELINE_PARAMS: dict[str, float | int] = {
    "fast_period": 50,
    "slow_period": 200,
    "rsi_period": 14,
    "rsi_floor": 55.0,
    "rsi_ceiling": 90.0,
}


# Families that cannot be built from an asset's own bars alone because their
# rule depends on the state of the wider market. The caller has to supply a
# `MarketContext`; there is no default, because the only honest default is a
# refusal (see `_RegimeRouter`).
MARKET_CONTEXT_FAMILIES = frozenset({"regime_router"})


def build_strategy(
    family: str,
    params: dict[str, float | int],
    context: Any = None,
) -> CausalStrategy:
    """Build a strategy, optionally with a view of the wider market.

    `context` is accepted by every family and consumed by almost none: the
    single-asset families ignore it entirely, so every existing call site keeps
    working unchanged and every stored result stays reproducible. Only the
    families in `MARKET_CONTEXT_FAMILIES` read it, and they fail loudly when it
    is missing rather than falling back to a single-asset approximation.
    """
    strategies = {
        "volatility_expansion": _Momentum,
        "volume_climax": _Reversal,
        "trade_abstention": _Abstention,
        "trend_persistence": _TrendPersistence,
        "supertrend_adx": _SuperTrendADX,
        "donchian_breakout": _DonchianBreakout,
        "multi_factor_trend": _MultiFactorTrend,
        "regime_switching": _RegimeSwitching,
        "sma_rsi_trend": _SMARSITrend,
    }
    if family in MARKET_CONTEXT_FAMILIES:
        # Imported here rather than at module scope: regime_system reads the
        # shared indicator vocabulary (_sma, _rsi) from this module, so a
        # top-level import would close a cycle.
        from .regime_system import _RegimeRouter

        return _RegimeRouter(params, context)
    if family not in strategies:
        raise ValueError(f"unknown strategy family: {family}")
    return strategies[family](params)
