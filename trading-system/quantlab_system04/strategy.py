"""cushion-scaled-trend: a long-only trend sleeve whose SIZE is the cushion.

The incumbent captures the crypto trend premium with a single sleeve and a
fixed 30-day hold. This proposal keeps the same premium -- long-only time-series
momentum, documented since Moskowitz, Ooi & Pedersen (2012) and confirmed in
Bitcoin -- and changes the two things that are NOT the entry, because this
laboratory's own record says the entry is the least of it:

  1. Diversify the sleeve across the majors instead of betting one. A basket of
     trends that turn at different times has a shallower drawdown than any one
     of them, so the drawdown budget -- the real constraint here -- binds less
     often and the sleeve can stay invested through a forward window that
     trends.

  2. Size every entry by the CUSHION rather than a fixed fraction. Cushion is
     equity above a floor that ratchets up with the peak (Time-Invariant
     Portfolio Protection, Estep & Kritzman 1988; the CPPI family of Black &
     Jones 1987 and Perold & Sharpe 1988). Risk taken scales with the distance
     to the floor: near a fresh high the sleeve is fully invested, and as
     equity falls toward the floor the target exposure shrinks convexly to
     zero, reaching cash BEFORE the 25% abort rather than at it. The mandate is
     then honoured by construction, not by a stop that fires after the damage.

The convex de-risk is delivered discretely -- whole positions exited on a trend
break or when the shrinking target no longer fits -- because a SELL here closes
a position in full and trimming by selling-then-rebuying would pay the toll
twice. Discrete exits keep turnover low, which is the only way a 0.30% round
trip is survivable at all: entries happen at trend starts, top-ups only as the
cushion genuinely grows, exits at trend breaks. A handful of round trips per
symbol per year, each capturing a multi-percent trend leg, clears the toll with
room to spare.

Assumption stated for the record: this is written for DAILY bars (the incumbent
is `itsm-30d`, a 30-day hold that only parses as days, and 24 trades across a
2026 that is ~225 sessions is a daily cadence). The windows are counted in
bars; on any other resolution the mechanism still computes, only the horizon
changes.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any

from quantlab_trading.brains import register
from quantlab_trading.runner import Decision
from quantlab_intraday.moneymanagement import intraday_money_management


DEFAULTS: dict[str, Any] = {
    # -- the trend premium (entry/hold), self-computed from closes so no served
    #    indicator name can make the module fail to load.
    "trend_window": 90,     # bars in the trailing mean that defines "in trend"
    "mom_window": 30,       # bars for the confirming absolute-momentum return
    "entry_momentum": 0.0,  # required trailing return to OPEN (mild; the MA leads)
    "exit_band": 0.04,      # hold until close < mean*(1-band): hysteresis cuts churn
    # -- the sizing hypothesis: cushion above a ratcheting floor
    "drawdown_budget": 0.20,  # floor = (1-budget)*peak; kept inside the 0.25 mandate
    "multiplier": 6.0,        # CPPI multiplier on the cushion fraction
    "max_total_fraction": 1.0,   # never lever; the most that can ever be deployed
    "max_position_fraction": 0.40,
    "max_positions": 3,
    # -- turnover control
    "add_band": 0.25,     # top up only when current < (1-band) of target
    "derisk_band": 0.10,  # drop a whole position only when overshoot exceeds this
    "cash_safety": 0.98,  # never try to spend the last of the cash
    # -- the mandate
    "maximum_drawdown": 0.25,
    # -- pairing: warm the means always, only TRADE on/after this instant.
    "trade_from": None,
}


def _as_datetime(value: Any) -> "datetime | None":
    if value in (None, ""):
        return None
    moment = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@register(
    "cushion-scaled-trend",
    "Long-only trend basket across the majors, each entry sized by the cushion "
    "above a peak-ratcheting floor (TIPP/CPPI), exits whole on a trend break.",
)
class CushionScaledTrendBrain:
    """Buy the majors that are trending, size the book by how far it is above a
    floor that follows the high-water mark, and step out whole when either the
    trend or the cushion says to."""

    def __init__(self, **params: Any):
        self.params = {
            key: params.get(key, default) for key, default in DEFAULTS.items()
        }
        self.trend_window = int(self.params["trend_window"])
        self.mom_window = int(self.params["mom_window"])
        if self.mom_window >= self.trend_window:
            # The momentum reference is read from the trend deque; it must fit.
            self.mom_window = self.trend_window - 1
        self.entry_momentum = float(self.params["entry_momentum"])
        self.exit_band = float(self.params["exit_band"])
        self.drawdown_budget = float(self.params["drawdown_budget"])
        self.multiplier = float(self.params["multiplier"])
        self.max_total_fraction = float(self.params["max_total_fraction"])
        self.max_position_fraction = float(self.params["max_position_fraction"])
        self.max_positions = int(self.params["max_positions"])
        self.add_band = float(self.params["add_band"])
        self.derisk_band = float(self.params["derisk_band"])
        self.cash_safety = float(self.params["cash_safety"])
        self.trade_from = _as_datetime(self.params["trade_from"])

        # REQUIRED by the contract: the harness serialises this and reads
        # `maximum_drawdown` from it.
        self.policy = intraday_money_management(
            maximum_drawdown=float(self.params["maximum_drawdown"]),
            maximum_position_fraction=self.max_position_fraction,
            maximum_concurrent_assets=self.max_positions,
        )
        self.max_drawdown = float(self.policy.maximum_drawdown)
        self.min_order = float(self.policy.minimum_order_notional)

        self.closes: dict[str, deque] = {}
        self.close_sums: dict[str, float] = {}
        self.pending: dict[str, int] = {}
        self.peak_equity = 0.0
        self.bars_seen = 0
        self.entries = 0
        self.exits = 0
        self.adds = 0

    # -- rolling trailing mean, kept incrementally --------------------------- #

    def _observe(self, symbol: str, close: float) -> None:
        series = self.closes.get(symbol)
        if series is None:
            series = self.closes[symbol] = deque(maxlen=self.trend_window)
            self.close_sums[symbol] = 0.0
        if len(series) == self.trend_window:
            self.close_sums[symbol] -= series[0]
        series.append(close)
        self.close_sums[symbol] += close

    def _mean(self, symbol: str) -> "float | None":
        series = self.closes.get(symbol)
        if series is None or len(series) < self.trend_window:
            return None
        return self.close_sums[symbol] / len(series)

    def _momentum(self, symbol: str, close: float) -> float:
        series = self.closes.get(symbol)
        if series is None or len(series) <= self.mom_window:
            return 0.0
        reference = series[-(self.mom_window + 1)]
        return close / reference - 1.0 if reference > 0 else 0.0

    # -- the one method a brain owes the laboratory -------------------------- #

    def decide(self, tick: dict[str, Any]) -> Decision:
        decision = Decision()
        account = tick.get("account", {}) or {}
        equity = float(account.get("equity", 0.0) or 0.0)
        initial = float(account.get("initial_capital", 0.0) or 0.0) or 1.0
        cash = float(account.get("cash", equity) or 0.0)
        positions = account.get("positions", {}) or {}
        self.bars_seen += 1
        self.peak_equity = max(self.peak_equity, equity, initial)

        # The mandate, measured against the peak -- the operator's 25% rule.
        drawdown = 1.0 - equity / self.peak_equity if self.peak_equity else 0.0
        if drawdown >= self.max_drawdown:
            decision.stop = (
                f"drawdown mandate breached: equity {equity:,.0f} is "
                f"{drawdown:.2%} below the peak {self.peak_equity:,.0f}"
            )
            return decision

        candles = tick.get("candles", {}) or {}
        moment = _as_datetime(tick.get("timestamp"))
        trading = self.trade_from is None or (
            moment is not None and moment >= self.trade_from
        )

        prices: dict[str, float] = {}
        for symbol, candle in candles.items():
            close = float(candle["close"])
            prices[symbol] = close
            self._observe(symbol, close)

        # Age the pending buys: a buy shows up as a position on a later bar.
        for symbol in list(self.pending):
            if symbol in positions:
                self.pending.pop(symbol)
            else:
                self.pending[symbol] += 1
                if self.pending[symbol] > 3:
                    self.pending.pop(symbol)

        # Which warmed symbols are in trend (hysteresis on hold vs entry).
        in_trend: dict[str, float] = {}
        for symbol, close in prices.items():
            mean = self._mean(symbol)
            if mean is None:
                continue
            momentum = self._momentum(symbol, close)
            held = symbol in positions or symbol in self.pending
            if held:
                qualifies = close > mean * (1.0 - self.exit_band)
            else:
                qualifies = close > mean and momentum >= self.entry_momentum
            if qualifies:
                in_trend[symbol] = momentum

        # The cushion: how far equity sits above a floor that ratchets with the
        # peak. Target exposure is the multiplier on that cushion, never levered.
        floor = (1.0 - self.drawdown_budget) * self.peak_equity
        cushion_fraction = max(0.0, (equity - floor) / equity) if equity > 0 else 0.0
        target_total = min(self.max_total_fraction, self.multiplier * cushion_fraction)

        ranked = sorted(in_trend, key=lambda s: in_trend[s], reverse=True)
        selected = ranked[: self.max_positions]
        selected_set = set(selected)
        per_symbol_target = (
            min(self.max_position_fraction, target_total / len(selected))
            if selected
            else 0.0
        )

        def current_notional(symbol: str) -> float:
            holding = positions.get(symbol) or {}
            price = prices.get(symbol)
            quantity = holding.get("quantity")
            if price is None or quantity is None:
                # No candle this bar, or an unpriced holding: fall back to book
                # value so it is neither force-sold nor double-counted wrongly.
                average = holding.get("average_price")
                if quantity is not None and average is not None:
                    return float(quantity) * float(average)
                return 0.0
            return float(quantity) * float(price)

        # 1) Exit whole: a held symbol whose trend broke, or which fell out of
        #    the top `max_positions`. Only act on symbols we can actually price
        #    this bar -- an unpriced holding is held, not blindly dumped.
        for symbol in list(positions):
            if symbol not in prices:
                continue
            if symbol not in selected_set:
                where = "TREND_EXIT" if symbol not in in_trend else "CAP_ROTATION"
                decision.sell(symbol, where, f"{self._momentum(symbol, prices[symbol]):+.2%} trailing")
                self.exits += 1

        # 2) De-risk: if the cushion shrank so the still-held book overshoots the
        #    target, drop whole positions weakest-first until it fits.
        deployed = {
            s: current_notional(s)
            for s in selected
            if s in positions and s not in self.pending
        }
        deployed_total = sum(deployed.values())
        if equity > 0 and deployed_total / equity > target_total + self.derisk_band:
            for symbol in sorted(deployed, key=lambda s: in_trend.get(s, 0.0)):
                if deployed_total / equity <= target_total + self.derisk_band:
                    break
                decision.sell(symbol, "DE_RISK", f"cushion {cushion_fraction:.2%}")
                self.exits += 1
                deployed_total -= deployed[symbol]
                selected_set.discard(symbol)

        # 3) Enter / top up, cushion permitting. Never commit past the cash on
        #    hand; track committed cash across this bar's buys.
        if trading and target_total > 0.0 and per_symbol_target > 0.0:
            budget = max(0.0, cash * self.cash_safety)
            for symbol in selected:
                if symbol not in selected_set:
                    continue  # dropped by the de-risk pass above
                if symbol in self.pending:
                    continue  # a buy is already in flight
                target_value = per_symbol_target * equity
                held_value = current_notional(symbol) if symbol in positions else 0.0
                want = target_value - held_value
                if symbol not in positions:
                    if want < self.min_order:
                        continue
                else:
                    # Top up only when the position has fallen well short of its
                    # target, so an uptrend is pressed without churning.
                    if held_value >= target_value * (1.0 - self.add_band):
                        continue
                    if want < self.min_order:
                        continue
                spend = min(want, budget)
                if spend < self.min_order:
                    continue
                reason = "ENTRY" if symbol not in positions else "TOP_UP"
                decision.buy(
                    symbol,
                    spend,
                    reason,
                    f"target {per_symbol_target:.1%} of equity, cushion {cushion_fraction:.2%}",
                )
                budget -= spend
                self.pending[symbol] = 0
                if symbol in positions:
                    self.adds += 1
                else:
                    self.entries += 1

        held_count = len(positions)
        decision.note = (
            f"{'warming' if not trading else 'live'} · held {held_count} · "
            f"target {target_total:.0%} · cushion {cushion_fraction:.1%} · "
            f"in-trend {len(in_trend)} · entries {self.entries}"
        )
        return decision

    # -- required fingerprints ---------------------------------------------- #

    def parameters(self) -> dict:
        return {
            key: value
            for key, value in self.params.items()
            if isinstance(value, (int, float, str, bool, type(None)))
        }

    def diagnostics(self) -> dict:
        return {
            "bars_seen": self.bars_seen,
            "entries": self.entries,
            "adds": self.adds,
            "exits": self.exits,
            "peak_equity": self.peak_equity,
        }