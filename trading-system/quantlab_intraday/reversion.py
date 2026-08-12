"""H-INTRA-001: buy the liquidity event, sell the reversion, leave within hours.

The whole strategy is in this file, in the same sense that `MandateBrain` puts
the whole of its own: every number is a decision and every decision is here or
in the policy it holds.

    entry   a bar closing near its low, more than `entry_displacement_atr`
            below its 20-bar VWAP, on a symbol liquid enough to matter, when
            what there is to capture exceeds `cost_multiple` round trips, and
            the symbol's volatility is not outside its own recent distribution
    exit    the anchor is reached, or the ATR-scaled target, or the ATR-scaled
            stop, or `maximum_holding_bars` have passed -- whichever is first
    size    a fixed fraction of equity at risk, divided by THIS bar's stop
            distance, so a quiet bar takes more and a violent one takes less
    stop    the run ends when the account is 25% below its peak

**What holds the whole design together is the time stop.** A reversion trade
that has not reverted within a few hours is not a slow winner, it is a wrong
read of what the bar meant -- the liquidity was not replaced because there was
nothing to replace, and the position has quietly become a directional bet the
system never intended to take. H-011 found the same shape at daily resolution
from the opposite direction: bucketed by realised duration, everything
resolving quickly made money and everything held longer lost, in both eras,
which is one of very few properties in this project whose sign does not flip
between the 2017-2021 and 2022-2025 markets. Here the stop is counted in bars,
by this brain, because `MoneyManagement.maximum_holding_days` counts days and
cannot express four hours.

**Why the drawdown abort is measured against the peak while sizing is not.**
Two different jobs, and QUANT17 is the record of what happens when one number
does both. The abort is the operator's mandate and the summary reports drawdown
from the running peak, so that is what the abort must use or a run could be
reported as breaching a limit it was never checked against. The de-leverage
ramp uses the policy's own basis, which defaults to "initial", because a
peak-driven ramp is a one-way ratchet that brought a strategy to a complete
stop for four and a half years while it reported itself legal.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from quantlab_trading.brains import register
from quantlab_trading.policy import policy_keys
from quantlab_trading.runner import Decision

from . import context, microstructure
from .moneymanagement import (
    bar_turnover_floor,
    intraday_money_management,
    position_notional,
    round_trip_cost,
)

# Every strategy knob, with its default. Kept as one dict so `parameters()`
# cannot drift from what `__init__` reads -- a knob missing from `parameters()`
# is a knob two runs can disagree on while sharing a `backtest_id`, and the
# second silently overwrites the first. That is not hypothetical; it cost this
# laboratory a recorded result.
DEFAULTS: dict[str, Any] = {
    # -- what a candidate bar looks like
    "anchor_key": "vwap_rolling",
    "atr_key": "atr_14",
    "natr_key": "natr_14",
    "rsi_key": "rsi_2",
    "slow_key": "ema_200",
    "turnover_key": "dollar_volume_20",
    "entry_displacement_atr": 1.5,
    "entry_ibs_max": 0.30,
    "entry_rsi_max": 15.0,
    # What there is to capture must beat this many round trips. At 2.0 the
    # dislocation has to be worth 0.60% before anything is bought.
    "cost_multiple": 2.0,
    # -- how the trade ends
    "target_atr": 1.0,
    "stop_atr": 2.0,
    "maximum_holding_bars": 48,  # four hours at 5m
    "exit_on_anchor": True,
    # -- when the premise does not hold. The volatility window is in DAYS, not
    # bars, so changing the interval does not silently change what "recent"
    # means -- five days is five days at 5m and at 1h.
    "volatility_quantile": 0.95,
    "volatility_window_days": 5,
    "volatility_minimum_days": 2,
    "trend_filter": "none",
    "hours": "",
    # -- the portfolio
    "maximum_positions": 3,
    "minimum_daily_turnover": 10_000_000.0,
    "bars_per_day": 288,
    "commission_bps": 10.0,
    "slippage_bps": 5.0,
    # -- the era boundary. NOT a tuning knob: it is what makes a training run
    # and a forward run two halves of one answer rather than two hypotheses.
    "trade_from": None,
}

EXIT_REASONS = ("ANCHOR", "TAKE_PROFIT", "STOP_LOSS", "TIME_STOP")


def _as_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        moment = value
    else:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@register(
    "intraday-reversion",
    "H-INTRA-001: buys 15-minute liquidity events below the rolling VWAP and "
    "exits on reversion, an ATR target, an ATR stop or a four-hour time stop.",
)
class IntradayReversionBrain:
    """The intraday system's only brain. One method the laboratory calls."""

    def __init__(self, **params: Any):
        unknown = set(params) - set(DEFAULTS) - set(policy_keys())
        if unknown:
            # A misspelled knob that is silently ignored produces a run that
            # looks like it tested something and did not. The laboratory has
            # enough ways to fool itself without adding a quiet one.
            raise ValueError(f"unknown parameters: {sorted(unknown)}")

        self.params = {
            key: params.get(key, default) for key, default in DEFAULTS.items()
        }
        self.policy = intraday_money_management(
            **{key: params[key] for key in params if key in set(policy_keys())}
        )

        self.trade_from = _as_datetime(self.params["trade_from"])
        self.hours = tuple(
            int(part) for part in str(self.params["hours"]).split(",") if part.strip()
        )
        self.round_trip = round_trip_cost(
            float(self.params["commission_bps"]), float(self.params["slippage_bps"])
        )
        self.cost_hurdle = self.round_trip * float(self.params["cost_multiple"])
        self.turnover_floor = bar_turnover_floor(
            float(self.params["minimum_daily_turnover"]),
            int(self.params["bars_per_day"]),
        )
        self.maximum_positions = min(
            int(self.params["maximum_positions"]),
            int(self.policy.maximum_concurrent_assets),
        )
        bars_per_day = int(self.params["bars_per_day"])
        self.volatility = context.VolatilityWatch(
            window=int(self.params["volatility_window_days"]) * bars_per_day,
            minimum_samples=int(self.params["volatility_minimum_days"]) * bars_per_day,
        )
        self.reset()

    # -- state ---------------------------------------------------------------- #

    def reset(self) -> None:
        """Instances are reused, so this must actually reset. Rule 2."""
        self.volatility.reset()
        self.plans: dict[str, dict[str, float]] = {}
        self.pending: dict[str, dict[str, float]] = {}
        self.held_bars: dict[str, int] = {}
        self.peak_equity = 0.0
        self.bars_seen = 0
        self.bars_traded = 0
        self.entries = 0
        self.exits: dict[str, int] = {reason: 0 for reason in EXIT_REASONS}
        self.refusals: dict[str, int] = {}

    def _refuse(self, reason: str) -> None:
        self.refusals[reason] = self.refusals.get(reason, 0) + 1

    # -- the one method a brain owes the laboratory --------------------------- #

    def decide(self, tick: dict[str, Any]) -> Decision:
        decision = Decision()
        account = tick["account"]
        equity = float(account["equity"])
        initial = float(account["initial_capital"]) or 1.0
        self.bars_seen += 1
        self.peak_equity = max(self.peak_equity, equity, initial)

        # The mandate, before anything else, and against the peak -- because
        # that is the number the summary reports and therefore the number the
        # operator's 25% means.
        peak_drawdown = 1 - equity / self.peak_equity if self.peak_equity else 0.0
        if peak_drawdown >= self.policy.maximum_drawdown:
            decision.stop = (
                f"drawdown mandate breached: equity {equity:,.0f} is "
                f"{peak_drawdown:.2%} below the peak {self.peak_equity:,.0f}"
            )
            return decision

        # The sizing ramp reads the policy's own basis, which is a different
        # question from the abort and deliberately answered differently.
        ramp_drawdown = self.policy.drawdown_against(equity, self.peak_equity, initial)

        candles = tick.get("candles", {}) or {}
        indicators = tick.get("indicators", {}) or {}
        positions = account.get("positions", {}) or {}
        moment = _as_datetime(tick.get("timestamp"))
        warming = (
            self.trade_from is not None
            and moment is not None
            and moment < self.trade_from
        )

        readings: dict[str, microstructure.Reading] = {}
        for symbol, row in indicators.items():
            candle = candles.get(symbol)
            if candle is None:
                continue
            self.volatility.observe(symbol, row.get(self.params["natr_key"]))
            reading = microstructure.read(
                symbol,
                candle,
                row,
                anchor_key=str(self.params["anchor_key"]),
                atr_key=str(self.params["atr_key"]),
                rsi_key=str(self.params["rsi_key"]),
                turnover_key=str(self.params["turnover_key"]),
            )
            if reading is not None:
                readings[symbol] = reading

        # A buy queued last tick has either filled or been refused; either way
        # the plan belongs to the position now, or to nobody.
        for symbol in list(self.pending):
            if symbol in positions:
                self.plans[symbol] = self.pending.pop(symbol)
                self.held_bars[symbol] = 0
                self.entries += 1
            else:
                self.pending.pop(symbol)

        exiting = self._exits(decision, positions, readings)
        if not warming:
            self.bars_traded += 1
            self._entries(
                decision,
                account,
                positions,
                readings,
                indicators,
                exiting,
                equity,
                ramp_drawdown,
                tick,
            )

        decision.note = self._note(warming, positions, decision)
        return decision

    # -- exits ---------------------------------------------------------------- #

    def _exits(
        self,
        decision: Decision,
        positions: dict[str, Any],
        readings: dict[str, microstructure.Reading],
    ) -> set[str]:
        """Close whatever has resolved, run out of time, or run out of rope.

        Every open position is aged on every tick, including one whose symbol
        served no bar this tick. A holding that stops printing bars would
        otherwise be held for ever by a time stop that never advances.
        """
        closing: set[str] = set()
        for symbol, holding in positions.items():
            self.held_bars[symbol] = self.held_bars.get(symbol, 0) + 1
            plan = self.plans.get(symbol)
            move = float(holding.get("unrealised_pct") or 0.0)
            reading = readings.get(symbol)

            reason = None
            if (
                self.params["exit_on_anchor"]
                and reading is not None
                and reading.displacement_pct <= 0
            ):
                reason = "ANCHOR"
            elif plan and move >= plan["target_pct"]:
                reason = "TAKE_PROFIT"
            elif plan and move <= -plan["stop_pct"]:
                reason = "STOP_LOSS"
            elif self.held_bars[symbol] >= int(self.params["maximum_holding_bars"]):
                reason = "TIME_STOP"
            if reason is None:
                continue

            decision.sell(
                symbol, reason, f"{move:+.2%} after {self.held_bars[symbol]} bars"
            )
            self.exits[reason] += 1
            closing.add(symbol)
        return closing

    # -- entries -------------------------------------------------------------- #

    def _entries(
        self,
        decision: Decision,
        account: dict[str, Any],
        positions: dict[str, Any],
        readings: dict[str, microstructure.Reading],
        indicators: dict[str, Any],
        exiting: set[str],
        equity: float,
        drawdown: float,
        tick: dict[str, Any],
    ) -> None:
        # A symbol being sold this tick is still held until the fill, so it is
        # not a candidate: the session would refuse the buy as "already
        # holding" and the refusal would look like a strategy that chose not to
        # trade.
        occupied = set(positions) | set(self.pending)
        room = self.maximum_positions - len(occupied)
        if room <= 0:
            self._refuse("no_room")
            return
        if not context.hour_allows(str(tick.get("timestamp", "")), self.hours):
            self._refuse("hour")
            return

        cash = float(account.get("cash", 0.0))
        candidates = []
        for symbol, reading in readings.items():
            if symbol in occupied or symbol in exiting:
                continue
            verdict = microstructure.qualifies(
                reading,
                minimum_displacement_atr=float(self.params["entry_displacement_atr"]),
                maximum_ibs=float(self.params["entry_ibs_max"]),
                maximum_rsi=float(self.params["entry_rsi_max"]),
                cost_hurdle_pct=self.cost_hurdle,
                minimum_turnover=self.turnover_floor,
            )
            if not verdict.ok:
                self._refuse(verdict.reason)
                continue
            row = indicators.get(symbol, {})
            if self.volatility.elevated(
                symbol,
                row.get(self.params["natr_key"]),
                float(self.params["volatility_quantile"]),
            ):
                self._refuse("volatility")
                continue
            if not context.trend_allows(
                row,
                str(self.params["trend_filter"]),
                reading.close,
                str(self.params["slow_key"]),
            ):
                self._refuse("trend")
                continue
            candidates.append(reading)

        # Most dislocated first. With three slots and five symbols the ranking
        # decides which liquidity event gets the capital, and "the biggest one"
        # is the only ordering the mechanism itself argues for.
        candidates.sort(key=lambda reading: reading.displacement_atr, reverse=True)
        for reading in candidates[:room]:
            stop_distance = float(self.params["stop_atr"]) * reading.atr / reading.close
            notional = position_notional(self.policy, equity, stop_distance, drawdown)
            if notional <= 0:
                self._refuse("size_floor")
                continue
            if notional > cash:
                # Sized against equity, paid for out of cash. Skipping rather
                # than shrinking keeps the position meaningful; the session
                # would otherwise silently truncate it to whatever cash is left
                # and the run would report a size it never took.
                self._refuse("cash")
                continue
            cash -= notional
            self.pending[reading.symbol] = {
                "target_pct": float(self.params["target_atr"])
                * reading.atr
                / reading.close,
                "stop_pct": stop_distance,
                "entry_close": reading.close,
                "entry_atr": reading.atr,
            }
            decision.buy(
                reading.symbol,
                notional,
                "LIQUIDITY_EVENT",
                f"{reading.displacement_atr:.2f} ATR ({reading.displacement_pct:.2%}) "
                f"below {self.params['anchor_key']}, IBS {reading.ibs:.2f}, "
                f"RSI {reading.rsi_fast:.0f}",
            )

    # -- reporting ------------------------------------------------------------ #

    def _note(
        self, warming: bool, positions: dict[str, Any], decision: Decision
    ) -> str:
        if warming:
            return (
                f"warming · {self.bars_seen} bars observed · "
                f"trading opens {self.trade_from:%Y-%m-%d %H:%M}"
            )
        note = f"held {len(positions)} · entries {self.entries}"
        if decision.orders:
            note += f" · {len(decision.orders)} orders"
        return note

    def diagnostics(self) -> dict[str, Any]:
        """Why the run did what it did, in counts rather than in a feeling.

        A run that takes no trades because nothing qualified and a run that
        takes no trades because a threshold is inverted look identical in the
        summary. These counters are the difference, and they are the first
        thing to read when a result is surprising in either direction.
        """
        return {
            "bars_seen": self.bars_seen,
            "bars_traded": self.bars_traded,
            "entries": self.entries,
            "exits": dict(self.exits),
            "refusals": dict(self.refusals),
            "cost_hurdle_pct": self.cost_hurdle,
            "turnover_floor": self.turnover_floor,
        }

    def parameters(self) -> dict[str, Any]:
        """Everything that makes this brain the brain it is. Fingerprint input."""
        return {
            key: value
            for key, value in self.params.items()
            if isinstance(value, (int, float, str, bool, type(None)))
        }
