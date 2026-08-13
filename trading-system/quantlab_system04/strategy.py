"""Generation four: the entry bar measured in volatility, not in percent.

**The hypothesis, and it is aimed at one measured failure.** The incumbent
(`intraday-itsm-30d`, +5.05% in the sealed 2026 window) enters when a major
opens the day with a move above a FIXED 3% threshold. Forensics on its forward
run counted the refusals: the entry condition was refused 319,662 times in 2026
and the trend filter only ten. The bar was not wrong, it was *fixed* -- a 3%
morning move is an ordinary event in a violent year and a rare one in a quiet
one, so the same number is a different rule in every regime, and in 2026 it was
a rule that almost never fired. Three trades in seven and a half months.

So: the same mechanism with the threshold expressed in units of the asset's own
recent volatility. `entry_sigma = 1.5` means "a morning move one and a half
times larger than this asset's typical daily swing", which is the same
SELECTIVITY in a quiet year and a violent one. That is the whole claim.

**Falsifiable, and here is what would refute it.** If the volatility-normalised
bar is genuinely regime-neutral, its trade count per year should be roughly
stable across the eight training years, and the sealed 2026 window should fire
at a rate near its training rate rather than collapsing to near-zero the way the
fixed bar did. It is refuted if the sealed window trades fewer than ten times,
or if the training run cannot hold the 25% mandate.

**Where the pieces come from.** Time-series (per-asset) momentum rather than
cross-sectional ranking, because the AUT ACFR study of this exact market found
time-series momentum earning roughly 32% annually against 15% for
cross-sectional with more than double the Sharpe. Inverse-volatility sizing from
Moreira & Muir's volatility-managed portfolios -- and used only to SIZE, never as
the signal, because their own out-of-sample versions earn lower
certainty-equivalent returns when the scaling is asked to carry the edge.

**What is deliberately NOT here.** No parameter fitted on 2026, no second entry
rule, no ensemble. One mechanism, one changed idea against the incumbent, so a
result attributes to something.

**The toll is the design constraint.** A round trip costs 0.30% of notional. This
holds positions for days and exits on a volatility-scaled trailing stop rather
than at the close, so a winning trade is asked to cover 30 bps once over a
multi-day move instead of once per session.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any

from quantlab_intraday.moneymanagement import (
    bar_turnover_floor,
    intraday_money_management,
    position_notional,
)
from quantlab_trading.brains import register
from quantlab_trading.runner import Decision

DAY = 288  # five-minute bars in a day


def _moment(value: Any) -> datetime | None:
    """The bar's timestamp. It arrives as an ISO STRING, not a datetime.

    Stated here because assuming otherwise cost a whole attempt: a strategy
    called `.date()` on it and died on the first bar after a full research pass.
    """
    if value in (None, ""):
        return None
    moment = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


class _State:
    """What the brain remembers per symbol. Nothing here reads a future bar."""

    def __init__(self, trend_days: int, sigma_days: int):
        self.day = None  # the UTC date currently open
        self.day_open = 0.0
        self.daily_closes: deque[float] = deque(maxlen=max(trend_days, 1))
        # Daily RETURNS, kept separately from the closes because the trend wants
        # a level and the volatility wants a dispersion, and the two want
        # different windows.
        self.daily_returns: deque[float] = deque(maxlen=max(sigma_days, 2))
        self.previous_day_close = 0.0
        self.last_close = 0.0
        self.peak_close = 0.0  # the high-water close since entry, for the trail
        self.held_bars = 0
        self.entry_sigma_day = 0.0  # sigma at entry, so the trail does not drift


@register(
    "vol-normalised-tsmom",
    "time-series momentum with a volatility-normalised entry bar, inverse-vol "
    "sizing and a volatility-scaled trailing stop",
)
class VolatilityNormalisedMomentum:
    def __init__(self, **params: Any):
        self.params = {
            # The entry bar, in units of the asset's own daily volatility. This
            # is the ONE idea being tested against the incumbent's fixed 3%.
            "entry_sigma": 1.5,
            # Trend gate: close above the mean of the last N daily closes. The
            # incumbent's filter refused only ten bars in 2026, so it is not
            # what broke, and it is kept unchanged on purpose.
            "trend_days": 30,
            # The window the daily-return volatility is measured over, and the
            # minimum samples before an entry is allowed at all.
            "sigma_days": 30,
            "minimum_sigma_days": 10,
            # Exits.
            "trail_sigma": 3.0,  # trailing stop, in daily sigma below the peak
            "stop_atr": 6.0,  # initial stop distance, in ATR, for SIZING
            "maximum_holding_bars": 4032,  # fourteen days
            # Book.
            "maximum_positions": 3,
            # NOT a preference -- forced, and the same trap `momentum.py`
            # documents. Sizing divides the risk budget by the stop distance.
            # With a 6 x natr stop that distance is ~3.2%, so the incumbent's
            # 0.05 asks for 156% of equity, `maximum_position_fraction` silently
            # truncates it to 30%, and the inverse-volatility scaling never
            # operates at all -- every position identical, nothing saying so.
            # Measured: that is exactly what the first run did, and three 30%
            # positions held fourteen days through 2021 breached the mandate at
            # 25.33%. At 0.006 a 3.2% stop takes ~19% and the scaling is live in
            # both directions.
            "risk_per_trade": 0.006,
            "maximum_position_fraction": 0.30,
            "minimum_daily_turnover": 10_000_000.0,
            # The mandate is the operator's, not a knob to tune.
            "maximum_drawdown": 0.25,
            "drawdown_deleverage_start": 0.10,
            "drawdown_basis": "peak",
            # Column names, so a rename is one edit.
            "atr_key": "natr_14",
            "turnover_key": "dollar_volume_20",
            "minimum_position_fraction": 0.02,
            "bars_per_day": DAY,
        }
        self.params.update(params)

        self.policy = intraday_money_management(
            risk_per_trade=float(self.params["risk_per_trade"]),
            maximum_position_fraction=float(self.params["maximum_position_fraction"]),
            maximum_concurrent_assets=int(self.params["maximum_positions"]),
            maximum_drawdown=float(self.params["maximum_drawdown"]),
            drawdown_basis=str(self.params["drawdown_basis"]),
            drawdown_deleverage_start=float(self.params["drawdown_deleverage_start"]),
        )

        # $10M a day is ~$35k per five-minute bar. Comparing a per-bar figure
        # against the DAILY floor rejected 714,878 bars in the first run -- the
        # single largest refusal reason, and entirely an accounting mistake.
        self.turnover_floor = bar_turnover_floor(
            float(self.params["minimum_daily_turnover"]),
            int(self.params["bars_per_day"]),
        )

        self.state: dict[str, _State] = {}
        self.peak_equity = 0.0
        self.bars_seen = 0
        self.bars_traded = 0
        self.entries = 0
        self.clamped = 0
        self.exits: dict[str, int] = {}
        # Why entries were refused, counted. This is the diagnostic that named
        # the incumbent's failure -- without it the 2026 collapse looked like
        # bad luck rather than a bar that never fired.
        self.refusals: dict[str, int] = {}

    # -- the harness contract ------------------------------------------------- #

    def parameters(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in self.params.items()
            if isinstance(value, (int, float, str, bool, type(None)))
        }

    def diagnostics(self) -> dict[str, Any]:
        return {
            "bars_seen": self.bars_seen,
            "bars_traded": self.bars_traded,
            "entries": self.entries,
            "sized_at_the_cap": self.clamped,
            "exits": dict(self.exits),
            "refusals": dict(self.refusals),
            "round_trip_cost": 0.003,
        }

    # -- helpers -------------------------------------------------------------- #

    def _refuse(self, reason: str) -> None:
        self.refusals[reason] = self.refusals.get(reason, 0) + 1

    def _sigma_day(self, state: _State) -> float:
        """This asset's typical daily move, MEASURED from its own daily returns.

        THE VERSION THIS REPLACES, because the mistake is instructive and it was
        caught before it cost a run. The obvious estimate is `natr_14 * sqrt(288)`
        -- a per-bar ATR scaled to a day by the square-root-of-time rule. On BTC
        that gives 9.07%. The true standard deviation of BTC's daily returns over
        3,059 days is 3.58%. The estimate is 2.5x too large, because ATR measures
        the average bar RANGE and intraday movement is largely noise that does
        not accumulate into net displacement the way an independent random walk
        would. An entry bar of `1.5 * 9.07% = 13.6%` would essentially never
        fire -- which is precisely the incumbent's failure reproduced, with a
        different number.

        So this measures rather than infers: the standard deviation of the last
        `sigma_days` daily closes-to-closes. It needs no scaling assumption, and
        it re-estimates as the regime changes, which is the entire point of the
        hypothesis.
        """
        returns = state.daily_returns
        if len(returns) < max(int(self.params["minimum_sigma_days"]), 2):
            return 0.0
        n = len(returns)
        mean = sum(returns) / n
        variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
        return variance**0.5

    def _stop_distance(self, indicators: dict[str, Any]) -> float:
        """How far the stop sits, in price fraction, for SIZING only.

        This is what ATR is genuinely good for -- the width of recent bars -- and
        it is used only to divide the risk budget, never to set the entry bar.
        """
        per_bar = indicators.get(self.params["atr_key"])
        if per_bar is None:
            return 0.0
        value = float(per_bar)
        if value > 1.0:  # served as a percentage rather than a fraction
            value = value / 100.0
        return float(self.params["stop_atr"]) * value

    def _trend_mean(self, state: _State) -> float | None:
        if len(state.daily_closes) < max(int(self.params["trend_days"]) // 2, 2):
            return None
        return sum(state.daily_closes) / len(state.daily_closes)

    # -- the one method that matters ------------------------------------------ #

    def decide(self, tick: dict[str, Any]) -> Decision:
        decision = Decision()
        self.bars_seen += 1

        account = tick["account"]
        equity = float(account["equity"])
        initial = float(account["initial_capital"]) or 1.0
        self.peak_equity = max(self.peak_equity, equity, initial)

        # THE MANDATE, against the high-water mark. Checked before anything else
        # so a breach cannot be masked by a profitable exit on the same bar.
        drawdown = 1.0 - equity / self.peak_equity if self.peak_equity else 0.0
        if drawdown >= float(self.params["maximum_drawdown"]):
            decision.stop = (
                f"drawdown mandate breached: equity {equity:,.0f} is "
                f"{drawdown:.2%} below the peak {self.peak_equity:,.0f}"
            )
            return decision

        candles = tick.get("candles", {}) or {}
        indicators = tick.get("indicators", {}) or {}
        positions = account.get("positions", {}) or {}
        moment = _moment(tick.get("timestamp"))
        today = moment.date() if moment is not None else None

        trending = 0

        for symbol, candle in sorted(candles.items()):
            close = float(candle["close"])
            column = indicators.get(symbol) or {}
            state = self.state.setdefault(
                symbol,
                _State(int(self.params["trend_days"]), int(self.params["sigma_days"])),
            )

            # A new UTC day: file yesterday's close into the trend history and
            # open today. Done before any decision, so the day return below is
            # measured from this day's open and never from yesterday's.
            if today is not None and state.day != today:
                if state.last_close:
                    if state.previous_day_close:
                        state.daily_returns.append(
                            state.last_close / state.previous_day_close - 1.0
                        )
                    state.previous_day_close = state.last_close
                    state.daily_closes.append(state.last_close)
                state.day = today
                state.day_open = float(candle["open"])
            state.last_close = close
            if not state.day_open:
                state.day_open = close

            sigma_day = self._sigma_day(state)
            mean = self._trend_mean(state)
            if mean is not None and close > mean:
                trending += 1

            # ---- holding: trail, trend loss, or time -------------------------
            if symbol in positions:
                state.held_bars += 1
                state.peak_close = max(state.peak_close, close)
                trail = state.entry_sigma_day * float(self.params["trail_sigma"])
                if trail > 0 and close <= state.peak_close * (1.0 - trail):
                    decision.sell(symbol, reason="trailing stop")
                    self.exits["trail"] = self.exits.get("trail", 0) + 1
                    state.held_bars = 0
                elif mean is not None and close < mean:
                    decision.sell(symbol, reason="trend lost")
                    self.exits["trend"] = self.exits.get("trend", 0) + 1
                    state.held_bars = 0
                elif state.held_bars >= int(self.params["maximum_holding_bars"]):
                    decision.sell(symbol, reason="held long enough")
                    self.exits["time"] = self.exits.get("time", 0) + 1
                    state.held_bars = 0
                continue

            # ---- entry -------------------------------------------------------
            if len(positions) + len(decision.orders) >= int(
                self.params["maximum_positions"]
            ):
                self._refuse("book full")
                continue
            if sigma_day <= 0:
                self._refuse("daily volatility still warming up")
                continue
            if mean is None:
                self._refuse("trend history warming up")
                continue
            if close <= mean:
                self._refuse("below the trend mean")
                continue
            turnover = column.get(self.params["turnover_key"])
            if turnover is None or float(turnover) < self.turnover_floor:
                self._refuse("too thin to trade")
                continue

            # THE CHANGED IDEA. The bar is `entry_sigma` daily sigmas, not a
            # fixed percentage, so it means the same thing in every regime.
            day_return = close / state.day_open - 1.0 if state.day_open else 0.0
            if day_return < float(self.params["entry_sigma"]) * sigma_day:
                self._refuse("move smaller than the volatility bar")
                continue

            # Inverse-volatility sizing: the risk budget divided by the live
            # ATR stop distance, so a violent asset takes a smaller position for
            # the same risk. `drawdown` feeds the policy's de-leverage ramp.
            stop_distance = self._stop_distance(column)
            if stop_distance <= 0:
                self._refuse("no ATR for sizing")
                continue
            notional = position_notional(
                self.policy, equity, stop_distance, drawdown
            )
            # Recorded because a silently-clamped size is invisible in every
            # other metric: if this counter equals the entry count, the ATR
            # scaling did nothing and the strategy is flat-sized.
            cap = float(self.params["maximum_position_fraction"]) * equity
            if notional >= cap * 0.999:
                self.clamped += 1
            if notional <= 0:
                self._refuse("sized to nothing by the policy")
                continue

            decision.buy(
                symbol,
                notional,
                reason=(
                    f"day move {day_return:.2%} cleared "
                    f"{self.params['entry_sigma']}x sigma ({sigma_day:.2%})"
                ),
            )
            self.entries += 1
            state.peak_close = close
            state.held_bars = 0
            state.entry_sigma_day = sigma_day

        if decision.orders:
            self.bars_traded += 1

        # The monitor reads the regime off the first token of the note, so it is
        # a label the chart can colour rather than prose.
        regime = "BULL" if trending >= max(len(candles) // 2, 1) else "SIDEWAYS"
        decision.note = (
            f"{regime} · {trending}/{len(candles)} above their {self.params['trend_days']}"
            f"-day mean · {len(positions)} held"
        )
        return decision
