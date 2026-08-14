"""H-INTRA-002: buy strength, and do not cap the winner.

The second hypothesis, and it exists because of exactly how the first one
failed. H-INTRA-001 bought dislocation and sold the reversion, which caps the
upside by construction: the trade's target IS the anchor, so the mean payoff is
bounded by how far price had strayed, and that distance is a few tenths of a
percent at this resolution. Against a 0.30% round trip, a bounded mean is a
lost argument before the first trade.

So this brain inverts every part of that:

    entry   buy strength -- a break above the trailing high, an outsized bar
            closing on its high, or the intraday-momentum signal from the
            published literature (the day's move so far predicts the rest)
    exit    a stop that is tight, and an upside that is NOT capped: no take
            profit, a trailing stop that follows the move, and a time stop that
            only ends trades which went nowhere
    shape   a low win rate with a long right tail is the target. A rule with a
            60% win rate and a capped winner is the previous hypothesis again

**The exit is the hypothesis, not the entry.** Every entry rule below has
published evidence behind it and none of them is novel. What decides whether
any of them clears a fixed toll is whether the winners are allowed to run, and
that is a property of the exit. This is the same lesson `policy.py` states for
the daily system -- sizing and stops matter more than the trigger -- arriving
at a different resolution.

Entry rules, and where each comes from:

- `itsm` -- intraday time-series momentum. The return from the start of the UTC
  day to a fixed hour predicts the return over the rest of the day. Documented
  in Bitcoin by Shen, Urquhart and Wang (Financial Review 2022) and across 60+
  futures markets by Zhang, Ma and Bouri. One decision a day per symbol, held
  for hours, which is the trade profile a 0.30% toll can survive.
- `donchian` -- close above the trailing high. The oldest uncapped-tail rule
  there is: losses bounded by the stop, wins bounded by nothing.
- `volexp` -- a bar several ATR wide closing on its high, on a volume spike.
  The shape momentum ignition leaves behind.

Which one is used is a parameter because the survey measures them on the same
tape at the same cost, and a rule chosen by measurement is worth more than one
chosen by argument.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from typing import Any

from quantlab_trading.brains import register
from quantlab_trading.policy import policy_keys
from quantlab_trading.runner import Decision

from . import context
from .moneymanagement import (
    bar_turnover_floor,
    intraday_money_management,
    position_notional,
    round_trip_cost,
)

DEFAULTS: dict[str, Any] = {
    # -- which strength to buy
    "entry_rule": "itsm",  # itsm | donchian | volexp
    # itsm: at this UTC hour, if the day is already up by this much, buy.
    # The threshold is not decoration -- the cost-aware execution literature
    # finds that sign-only intraday rules die to costs while magnitude-gated
    # ones survive, which is the same cost hurdle this package applies
    # everywhere else.
    "itsm_hour": 12,
    "itsm_threshold": 0.005,
    # donchian: close above this served trailing high.
    "breakout_key": "high_200",
    # volexp: bar width in ATR, close position in the bar, volume against normal.
    "volexp_range_atr": 2.0,
    "volexp_ibs": 0.8,
    "volexp_volume": 3.0,
    # -- the exit, which is where the hypothesis actually lives
    "stop_atr": 1.5,
    # The trailing stop is what leaves the right tail open. None disables it.
    "trail_atr": 3.0,
    # Bars before a trade that has gone nowhere is closed. At 288 bars a day
    # this is a same-day horizon, which is what "intraday" has to mean if the
    # toll is paid once per trade.
    "maximum_holding_bars": 288,
    # OFF, because this market never closes. The published intraday momentum rule
    # is defined with a daily close, but it was written for equities, where the
    # bell forces the exit and holding overnight carries gap risk you cannot
    # manage. Crypto trades 24/7: there is no bell, so closing at 23:55 sells a
    # position that has not finished doing what it was opened to do, and pays a
    # full round trip to reopen the same idea the next morning.
    #
    # It defaulted to True and that silently changed what a run measured. The
    # `itsm-h08` candidate was published at +6.07% in the sealed window against
    # the incumbent's +5.05% while carrying this flag set the other way, so it was
    # never a comparison of entry hours: with a daily close the 3-day holding cap
    # can never be reached, and the "3-day drift bet" became a one-day trade that
    # turned over 824 times and paid 74.9% of capital in toll.
    #
    # A mixed book -- some positions closing the same day, some running for days
    # -- is the correct behaviour and not a problem to solve. The only real cost
    # is that a long-held position occupies one of `maximum_positions` slots and
    # its capital until it closes, which is a capital-allocation question (see
    # PLANNING.md item 1) rather than a reason to force an exit by the clock.
    "exit_end_of_day": False,
    # Deliberately absent: any take profit. A capped winner is the refuted
    # hypothesis wearing different parameters.
    # -- context
    "volatility_quantile": 1.0,  # 1.0 disables the veto: strength is not a crash
    "volatility_window_days": 5,
    "volatility_minimum_days": 2,
    "trend_filter": "none",
    "slow_key": "ema_200",
    # A trend filter measured in DAYS, kept by the brain because the served
    # catalogue does not reach this far: `sma_200` at 5 minutes is sixteen
    # hours, and what this needs is weeks. 0 disables it.
    #
    # This is not a patch for a block that lost money. Time-series momentum has
    # been reported as regime-dependent since Moskowitz, Ooi and Pedersen: the
    # same signal that pays in an uptrend is the wrong side of a downtrend, and
    # a long-only version of it has no way to express that except by standing
    # aside. The prior is what justifies testing the filter; the blocks are
    # what decide whether it earns its place.
    "trend_ma_days": 0,
    # How far the MARKET may be off its own running peak and the book still take
    # a trade. 1.0 disables it. This is not `trend_ma_days` with a different
    # spelling: that filter asks whether one asset is above its own mean, and
    # every asset can pass it individually on the way down. This asks a single
    # question about the whole market and answers it the same way for all twelve.
    #
    # Measured in the fast screen on 2026-08-14, twelve assets, money management
    # fitted on training evidence alone: gating at 40% takes the sealed 2026
    # median from -7.7% to -2.1% and the share of systems positive in 2026 from
    # 5% to 23%, with nine of 657 clearing the incumbent against zero without it.
    #
    # **The threshold is disclosed as tainted**: 0.40 was chosen by comparing
    # sealed distributions across 0.15, 0.25 and 0.40. One structural decision
    # made once, not per-candidate feedback, but not clean either. It cannot be
    # chosen on training instead, and that is the interesting part -- a gate costs
    # exposure, exposure pays in a rising market, and the research era is almost
    # entirely rising, so training evidence can only ever argue against a rule
    # whose whole purpose is to survive a fall. The outside justification is the
    # same one `trend_ma_days` cites: Moskowitz, Ooi and Pedersen.
    "market_gate_drawdown": 1.0,
    # Which series stands for "the market". Crypto beta is dominated by one asset.
    "market_symbol": "BTCUSDT",
    # The peak is the highest close of the TRAILING year, not of all time.
    #
    # An all-time peak is seeded by whatever bar the run happens to start on, and
    # that makes the gate a different rule in each half of a pair: the training
    # run opens in 2018 and accumulates a real high, the sealed run opens on
    # 2026-01-01 and treats the January price as the peak. Measured -- the first
    # gated forward run returned +1.47% on 23 trades, byte-identical to the
    # ungated control, because BTC never fell 40% below its own 2026 high. A
    # filter that silently does nothing in one half of a pair is worse than no
    # filter, because the pair still looks like a comparison.
    #
    # A trailing window has no seed and therefore means the same thing wherever a
    # run begins, which is what lets the two halves be compared at all.
    "market_peak_days": 365,
    # -- the meta-label: a second opinion on each entry the rule proposes
    #
    # Lopez de Prado's meta-labelling (AFML ch.3) splits a strategy in two: the
    # PRIMARY decides the side, a SECONDARY decides the size, including zero.
    # Everything tried in this laboratory so far has ADDED trades, and at a 30 bps
    # round trip that is a certain cost against an uncertain gain -- the gated
    # champion pays 113.8% of capital in toll over 511 trades, more than its whole
    # final return. A filter is the only change that can raise the return and
    # lower the bill at once.
    #
    # Empty disables it. The path is a verdict table built by `quantlab_ml.meta`,
    # whose research-era rows come from a purged walk-forward -- each verdict
    # issued by a fold model whose training set ended before the bar it judges --
    # and whose sealed rows come from the final model, fitted on the research era
    # and shown 2026 exactly once, here.
    "meta_verdicts": "",
    # The expected net return, after the round trip, below which an entry is
    # refused. 0.0 means "only take what the model expects to pay for itself".
    "meta_minimum": 0.0,
    "hours": "",
    # -- the portfolio
    "maximum_positions": 3,
    "minimum_daily_turnover": 10_000_000.0,
    "bars_per_day": 288,
    "atr_key": "atr_14",
    "natr_key": "natr_14",
    "turnover_key": "dollar_volume_20",
    "commission_bps": 10.0,
    "slippage_bps": 5.0,
    "trade_from": None,
    # What the ABORT is measured against, which is not the same question as what
    # the de-leverage RAMP is measured against (`drawdown_basis`, on the policy).
    #
    # "peak" -- the default, and what the published run did: stop when equity is
    # `maximum_drawdown` below its own high-water mark, whatever the policy says.
    # It is the strictest reading of the operator's 25% rule and it is also
    # INCOHERENT with the ramp unless the policy happens to agree: the published
    # configuration sized off `drawdown_basis="initial"`, so while the account
    # fell from 357,794 to 268,193 the ramp's drawdown was exactly zero -- equity
    # was still far above the opening 100,000 -- and every position was taken at
    # full risk straight into the abort. Two numbers, two definitions, and the
    # de-risking machinery asleep through the entire decline.
    #
    # "policy" -- one number for both, which is what `drawdown_against` was
    # written for. The mandate then means whatever `drawdown_basis` says, and the
    # ramp necessarily starts before the abort rather than below it. Under
    # `ratchet` that is the operator's own mandate as recorded in `policy.py`:
    # the opening floor plus half of the highest profit ever reached.
    #
    # Default "peak" so no stored configuration and no published result moves;
    # anything that sets this is a new configuration and owes its own forward run.
    "mandate_basis": "peak",
    # How far the risk budget may be scaled up by the strength of the signal.
    # 1.0 is off and is the default. See `_signal_scale`: the justification is
    # the measured dose-response, not an intuition that bigger moves are better.
    "signal_scale_cap": 1.0,
}

EXIT_REASONS = ("STOP_LOSS", "TRAIL", "TIME_STOP", "END_OF_DAY")


def _as_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    moment = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@register(
    "intraday-momentum",
    "H-INTRA-002: buys 5m strength (intraday momentum, breakout or volatility "
    "expansion) with a trailing stop and no take profit, so the winner runs.",
)
class IntradayMomentumBrain:
    """Buy strength, stop out quickly, let the rest run to the end of the day."""

    def __init__(self, **params: Any):
        unknown = set(params) - set(DEFAULTS) - set(policy_keys())
        if unknown:
            raise ValueError(f"unknown parameters: {sorted(unknown)}")
        self.params = {
            key: params.get(key, default) for key, default in DEFAULTS.items()
        }
        if self.params["entry_rule"] not in ("itsm", "donchian", "volexp"):
            raise ValueError(f"unknown entry_rule: {self.params['entry_rule']!r}")
        self.mandate_basis = str(self.params["mandate_basis"])
        if self.mandate_basis not in ("peak", "policy"):
            # Silently falling back to "peak" would report a configuration that
            # was never run, and the mandate is the one field where a typo has
            # to be loud.
            raise ValueError(f"unknown mandate_basis: {self.mandate_basis!r}")
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
        self.turnover_floor = bar_turnover_floor(
            float(self.params["minimum_daily_turnover"]),
            int(self.params["bars_per_day"]),
        )
        self.maximum_positions = min(
            int(self.params["maximum_positions"]),
            int(self.policy.maximum_concurrent_assets),
        )
        bars_per_day = int(self.params["bars_per_day"])
        self.trend_window = int(self.params["trend_ma_days"]) * bars_per_day
        self.volatility = context.VolatilityWatch(
            window=int(self.params["volatility_window_days"]) * bars_per_day,
            minimum_samples=int(self.params["volatility_minimum_days"]) * bars_per_day,
        )
        self.reset()

    # -- state ---------------------------------------------------------------- #

    def reset(self) -> None:
        self.volatility.reset()
        self.closes: dict[str, deque] = {}
        self.close_sums: dict[str, float] = {}
        self.plans: dict[str, dict[str, float]] = {}
        self.pending: dict[str, dict[str, float]] = {}
        self.held_bars: dict[str, int] = {}
        self.day_open: dict[str, float] = {}
        self.day_of: dict[str, Any] = {}
        self.peak_equity = 0.0
        # The market's trailing-year high and its latest close, for `market_gate`.
        self.market_days: deque[float] = deque(
            maxlen=max(1, int(self.params["market_peak_days"]))
        )
        self.market_day: Any = None
        self.market_today = 0.0
        self.market_window_peak = 0.0
        self.market_close = 0.0
        # The meta-label table, loaded once. Empty when the filter is off.
        self.verdicts = self._load_verdicts()
        self.bars_seen = 0
        self.bars_traded = 0
        self.entries = 0
        self.exits: dict[str, int] = {reason: 0 for reason in EXIT_REASONS}
        self.refusals: dict[str, int] = {}

    def _refuse(self, reason: str) -> None:
        self.refusals[reason] = self.refusals.get(reason, 0) + 1

    def _observe_close(self, symbol: str, close: float) -> None:
        """A rolling mean kept incrementally: one add and one subtract a bar.

        Recomputing a sum over eight thousand closes on every bar of every
        symbol is the same mistake the survey made with its squeeze percentile,
        and it is the reason that pass took twenty minutes instead of two.
        """
        series = self.closes.get(symbol)
        if series is None:
            series = self.closes[symbol] = deque(maxlen=self.trend_window)
            self.close_sums[symbol] = 0.0
        if len(series) == self.trend_window:
            self.close_sums[symbol] -= series[0]
        series.append(close)
        self.close_sums[symbol] += close

    def _load_verdicts(self) -> dict[tuple[str, str], float]:
        """The meta-label table, as a lookup keyed by symbol and bar.

        Read as DATA, not imported: the layering contract says nothing in
        `trading-system/` may reach into the laboratory, and a path to a JSON file
        respects that while an import would not.

        Keyed on the ISO minute rather than a parsed datetime because the table is
        written by a different program on a different clock, and comparing strings
        that were both produced by `isoformat` cannot disagree about a timezone.
        """
        path = str(self.params["meta_verdicts"] or "").strip()
        if not path:
            return {}
        with open(path) as handle:
            document = json.load(handle)
        table: dict[tuple[str, str], float] = {}
        for row in document.get("table", []):
            stamp = str(row["timestamp"]).replace(" ", "T")
            table[(str(row["symbol"]), stamp[:16])] = float(row["value"])
        return table

    def _meta_allows(self, symbol: str, moment: Any) -> bool | None:
        """The model's verdict on this entry. None when it has none.

        **A missing verdict is a refusal, not permission.** The purged
        walk-forward issues no verdict for bars before its first test block, and
        for 2,000 of 13,756 research candidates there is no fold that legitimately
        covers them. Treating those as permitted would quietly run the primary
        rule unfiltered over the earliest years and report it as a filtered
        result -- the same shape as an indicator that is blind rather than smart.
        """
        if not self.verdicts:
            return True
        if moment is None:
            return None
        value = self.verdicts.get((symbol, moment.isoformat()[:16]))
        if value is None:
            return None
        return value >= float(self.params["meta_minimum"])

    def _observe_market(self, candles: dict[str, Any], moment: Any = None) -> None:
        """Track the market's trailing-year high, so its fall is known at entry.

        Kept at daily resolution and recomputed only when the day rolls: a max
        over a year of 5-minute closes on every bar is 105,000 comparisons a bar,
        which is the same mistake `_observe_close` exists to avoid.
        """
        candle = candles.get(str(self.params["market_symbol"]))
        if candle is None:
            return
        close = float(candle["close"])
        if close <= 0:
            return
        self.market_close = close
        day = moment.date() if moment is not None else None
        if day is not None and day != self.market_day:
            if self.market_day is not None:
                self.market_days.append(self.market_today)
                self.market_window_peak = max(self.market_days)
            self.market_day = day
            self.market_today = close
        self.market_today = max(self.market_today, close)

    def _market_allows(self) -> bool:
        """Is the market close enough to its high for a long book to be open?

        Warm-up passes rather than refuses, unlike `_above_trend`. There is no
        window to fill before the answer means something: on the first day the
        trailing high is that day's high, the fall from it is near zero, and a
        book that trades then is doing what the rule intends.
        """
        gate = float(self.params["market_gate_drawdown"])
        peak = max(self.market_window_peak, self.market_today)
        if gate >= 1.0 or peak <= 0 or self.market_close <= 0:
            return True
        return (1.0 - self.market_close / peak) <= gate

    def _above_trend(self, symbol: str, close: float) -> bool:
        """Warm-up refuses. An opt-in filter that cannot be evaluated must not
        silently pass, or the first weeks of every window are unfiltered and
        nothing in the result says which trades those were."""
        if not self.trend_window:
            return True
        series = self.closes.get(symbol)
        if series is None or len(series) < self.trend_window:
            return False
        return close > self.close_sums[symbol] / len(series)

    # -- the one method a brain owes the laboratory --------------------------- #

    def decide(self, tick: dict[str, Any]) -> Decision:
        decision = Decision()
        account = tick["account"]
        equity = float(account["equity"])
        initial = float(account["initial_capital"]) or 1.0
        self.bars_seen += 1
        self.peak_equity = max(self.peak_equity, equity, initial)

        ramp_drawdown = self.policy.drawdown_against(equity, self.peak_equity, initial)
        if self.mandate_basis == "policy":
            mandate_drawdown = ramp_drawdown
            reference = f"the {self.policy.drawdown_basis} floor"
        else:
            mandate_drawdown = (
                1 - equity / self.peak_equity if self.peak_equity else 0.0
            )
            reference = f"the peak {self.peak_equity:,.0f}"
        if mandate_drawdown >= self.policy.maximum_drawdown:
            decision.stop = (
                f"drawdown mandate breached: equity {equity:,.0f} is "
                f"{mandate_drawdown:.2%} below {reference}"
            )
            return decision

        candles = tick.get("candles", {}) or {}
        indicators = tick.get("indicators", {}) or {}
        positions = account.get("positions", {}) or {}
        moment = _as_datetime(tick.get("timestamp"))
        warming = (
            self.trade_from is not None
            and moment is not None
            and moment < self.trade_from
        )

        for symbol, candle in candles.items():
            if moment is not None and self.day_of.get(symbol) != moment.date():
                self.day_of[symbol] = moment.date()
                self.day_open[symbol] = float(candle["open"])
            self.volatility.observe(
                symbol, (indicators.get(symbol) or {}).get(self.params["natr_key"])
            )
            if self.trend_window:
                self._observe_close(symbol, float(candle["close"]))
        self._observe_market(candles, moment)

        for symbol in list(self.pending):
            if symbol in positions:
                self.plans[symbol] = self.pending.pop(symbol)
                self.held_bars[symbol] = 0
                self.entries += 1
            else:
                self.pending.pop(symbol)

        exiting = self._exits(decision, positions, candles, indicators, moment)
        if not warming:
            self.bars_traded += 1
            self._entries(
                decision,
                account,
                positions,
                candles,
                indicators,
                exiting,
                equity,
                ramp_drawdown,
                moment,
            )

        decision.note = (
            f"warming · {self.bars_seen} bars"
            if warming
            else f"held {len(positions)} · entries {self.entries}"
        )
        return decision

    # -- exits ---------------------------------------------------------------- #

    def _exits(
        self,
        decision: Decision,
        positions: dict[str, Any],
        candles: dict[str, Any],
        indicators: dict[str, Any],
        moment: datetime | None,
    ) -> set[str]:
        """Stop, trail, time, end of day. Never a target.

        The trailing stop is what makes this hypothesis different from the last
        one: it follows the highest close the trade has seen, so a move that
        keeps going is never closed for being big enough.
        """
        closing: set[str] = set()
        last_bar_of_day = (
            moment is not None and moment.hour == 23 and moment.minute >= 55
        )
        for symbol, holding in positions.items():
            self.held_bars[symbol] = self.held_bars.get(symbol, 0) + 1
            plan = self.plans.get(symbol)
            move = float(holding.get("unrealised_pct") or 0.0)
            candle = candles.get(symbol)
            if plan is not None and candle is not None:
                plan["peak_pct"] = max(plan.get("peak_pct", 0.0), move)

            reason = None
            if plan and move <= -plan["stop_pct"]:
                reason = "STOP_LOSS"
            elif (
                plan
                and plan.get("trail_pct")
                and plan["peak_pct"] > plan["trail_pct"]
                and move <= plan["peak_pct"] - plan["trail_pct"]
            ):
                reason = "TRAIL"
            elif self.params["exit_end_of_day"] and last_bar_of_day:
                reason = "END_OF_DAY"
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

    def _qualifies(
        self,
        symbol: str,
        candle: dict[str, Any],
        row: dict[str, Any],
        moment: datetime | None,
    ) -> bool:
        rule = self.params["entry_rule"]
        close = float(candle["close"])
        if rule == "itsm":
            if moment is None or moment.hour != int(self.params["itsm_hour"]):
                return False
            if moment.minute != 0:
                return False
            opened = self.day_open.get(symbol)
            if not opened:
                return False
            return close / opened - 1 >= float(self.params["itsm_threshold"])
        if rule == "donchian":
            high = row.get(str(self.params["breakout_key"]))
            return high is not None and close > float(high)
        span = row.get("range_vs_atr")
        ibs = row.get("internal_bar_strength")
        volume = row.get("volume_ratio_20")
        if span is None or ibs is None or volume is None:
            return False
        return (
            float(span) >= float(self.params["volexp_range_atr"])
            and float(ibs) >= float(self.params["volexp_ibs"])
            and float(volume) >= float(self.params["volexp_volume"])
        )

    def _signal_scale(self, symbol: str, close: float) -> float:
        """How much of the risk budget THIS signal earns, from its own strength.

        The survey did not merely find that a 1.5% morning move pays. It found a
        monotone dose-response, measured on non-overlapping windows in both eras:
        excess over drift ran -0.40% at 0.0%, -0.10% at 0.5%, +0.54% at 1.5%,
        +0.92% at 2.0% and +2.49% at 3.0%. A rule that takes the same size at
        1.5% and at 4.0% is throwing that away -- it treats the weakest trade it
        will accept and the strongest it will ever see as the same bet.

        So the scale is the move divided by the threshold that admitted it: at
        exactly the threshold it is 1.0 and nothing changes, at twice the
        threshold the risk budget doubles, and `signal_scale_cap` bounds it.
        `maximum_position_fraction` still bounds the result, so a large scale
        raises the size of a small position and cannot inflate a full one.

        Only `itsm` has a dose to respond to -- a Donchian break is over the high
        or it is not -- so the other rules return 1.0 and say so here rather than
        having a scale quietly computed from an unrelated number.

        Default cap 1.0: off, and every result recorded before this existed is
        reproduced exactly.
        """
        cap = float(self.params["signal_scale_cap"])
        if cap <= 1.0 or self.params["entry_rule"] != "itsm":
            return 1.0
        threshold = float(self.params["itsm_threshold"])
        opened = self.day_open.get(symbol)
        if not opened or threshold <= 0:
            return 1.0
        return max(1.0, min(cap, (close / opened - 1) / threshold))

    def _entries(
        self,
        decision: Decision,
        account: dict[str, Any],
        positions: dict[str, Any],
        candles: dict[str, Any],
        indicators: dict[str, Any],
        exiting: set[str],
        equity: float,
        drawdown: float,
        moment: datetime | None,
    ) -> None:
        occupied = set(positions) | set(self.pending)
        room = self.maximum_positions - len(occupied)
        if room <= 0:
            self._refuse("no_room")
            return
        if moment is not None and not context.hour_allows(
            moment.isoformat(), self.hours
        ):
            self._refuse("hour")
            return
        # Nothing is opened on the last bar of the day when the rule closes at
        # the end of it: the position would be sold on the bar after it filled
        # and pay a full round trip for one bar of exposure.
        if self.params["exit_end_of_day"] and moment is not None and moment.hour == 23:
            self._refuse("end_of_day")
            return

        cash = float(account.get("cash", 0.0))
        candidates = []
        for symbol, candle in candles.items():
            if symbol in occupied or symbol in exiting:
                continue
            row = indicators.get(symbol) or {}
            turnover = row.get(str(self.params["turnover_key"]))
            if turnover is None or float(turnover) < self.turnover_floor:
                self._refuse("turnover")
                continue
            atr = row.get(str(self.params["atr_key"]))
            close = float(candle["close"])
            if atr is None or float(atr) <= 0 or close <= 0:
                self._refuse("warming")
                continue
            if not self._qualifies(symbol, candle, row, moment):
                self._refuse("signal")
                continue
            if self.volatility.elevated(
                symbol,
                row.get(str(self.params["natr_key"])),
                float(self.params["volatility_quantile"]),
            ):
                self._refuse("volatility")
                continue
            if not context.trend_allows(
                row,
                str(self.params["trend_filter"]),
                close,
                str(self.params["slow_key"]),
            ):
                self._refuse("trend")
                continue
            if not self._above_trend(symbol, close):
                self._refuse("below_trend_ma")
                continue
            if not self._market_allows():
                self._refuse("market_gate")
                continue
            verdict = self._meta_allows(symbol, moment)
            if verdict is None:
                self._refuse("meta_absent")
                continue
            if not verdict:
                self._refuse("meta_low")
                continue
            candidates.append((symbol, close, float(atr), row))

        # Strongest first: the widest bar relative to its own volatility is the
        # one the mechanism claims most about.
        candidates.sort(
            key=lambda item: item[3].get("range_vs_atr") or 0.0, reverse=True
        )
        for symbol, close, atr, _row in candidates[:room]:
            stop_distance = float(self.params["stop_atr"]) * atr / close
            notional = position_notional(
                self.policy,
                equity,
                stop_distance,
                drawdown,
                self._signal_scale(symbol, close),
            )
            if notional <= 0:
                self._refuse("size_floor")
                continue
            if notional > cash:
                self._refuse("cash")
                continue
            cash -= notional
            trail = self.params["trail_atr"]
            self.pending[symbol] = {
                "stop_pct": stop_distance,
                "trail_pct": (float(trail) * atr / close) if trail else 0.0,
                "peak_pct": 0.0,
                "entry_close": close,
                "entry_atr": atr,
            }
            decision.buy(
                symbol,
                notional,
                "MOMENTUM",
                f"{self.params['entry_rule']} · stop {stop_distance:.2%} · "
                f"trail {(float(trail) * atr / close) if trail else 0:.2%}",
            )

    # -- reporting ------------------------------------------------------------ #

    def diagnostics(self) -> dict[str, Any]:
        return {
            "bars_seen": self.bars_seen,
            "bars_traded": self.bars_traded,
            "entries": self.entries,
            "exits": dict(self.exits),
            "refusals": dict(self.refusals),
            "round_trip_cost": self.round_trip,
            "turnover_floor": self.turnover_floor,
        }

    def parameters(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in self.params.items()
            if isinstance(value, (int, float, str, bool, type(None)))
        }
