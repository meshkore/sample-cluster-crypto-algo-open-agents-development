"""Money management: every decision about how much to risk and when to quit.

This lives in the TRADING SYSTEM, not the backtester, because sizing, stops and
the drawdown mandate are *decisions* -- they are as much a hypothesis as an
entry rule, and this laboratory has repeatedly found them to matter more than
the signal. Anyone proposing a new paradigm may replace this file wholesale.

The backtester never imports this module. It accepts any object exposing the
attributes and methods used below, so a contributor can supply a completely
different policy -- volatility targeting, Kelly, fixed-fraction, a learned
sizer -- without touching the instrument that scores it. See CONTRACT.md.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any
import math


@dataclass(frozen=True)
class MoneyManagement:
    risk_per_trade: float = 0.01
    maximum_position_fraction: float = 0.25
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    minimum_confidence: float = 0.25
    long_only: bool = True
    maximum_concurrent_assets: int = 100
    minimum_order_notional: float = 10.0
    # A position must be worth taking. Once the drawdown de-leverage throttles
    # the risk budget, notional collapses toward the exchange floor and the run
    # grinds out thousands of ten-dollar trades that are pure noise: a quarter
    # of one strategy's ledger closed for less than fifty cents. Below this
    # fraction of equity the laboratory simply does not open. It only ever
    # reduces risk-taking, never increases it.
    minimum_position_fraction: float = 0.0025
    maximum_drawdown: float = 0.25
    # Retained for backwards-compatible stored policies. The binding abort is
    # always maximum_drawdown itself; a hidden lower threshold is misleading.
    drawdown_safety_buffer: float = 0.0
    volatility_target: float = 0.025
    volatility_lookback: int = 20
    # How far ABOVE target-volatility sizing a quiet asset may be scaled.
    #
    # The engine sizes by `min(cap, volatility_target / observed_vol)`. At the
    # 1.0 default that term is one-sided: it cuts a position whose asset is
    # noisier than target and does nothing for one that is quieter. Measured
    # across the universe, median 20-day volatility is 4.82% over 2018-2025
    # against a 2.5% target, so the median position is HALVED and only 8.7% of
    # observations ever reach the cap -- the clamp binds almost always, which
    # makes this a near-constant haircut rather than a risk parity control.
    #
    # Kim, Tse & Wald (2016) report that time-series momentum's performance is
    # driven by the volatility-SCALED returns rather than by the momentum signal
    # itself, and the crypto momentum-crash literature reaches the same place
    # from the other side: volatility management is what mitigates the crashes.
    # Both results describe scaling toward a target in BOTH directions. Only the
    # cutting half of that is currently implemented.
    #
    # 1.0 is the default because it reproduces the previous behaviour exactly,
    # so no stored policy and no published result moves until this is raised
    # deliberately. Raising it is a leverage decision and belongs to the
    # drawdown mandate, not to the parameter search -- see H-SIZE-001.
    #
    # NOTE ON SCOPE, and it is the whole point: `volatility_target` and this cap
    # are read by `LongOnlyPortfolioBacktester` ONLY. The four-module brain this
    # laboratory actually runs sizes through `notional_for` below, which had no
    # volatility term of any kind -- so until `volatility_sizing` is switched on,
    # NEITHER of those two fields affects a single result the loop produces.
    # Measured, not assumed: a fold sweep at cap 1.0 and cap 2.0 returned
    # 1.68/31.84/35.51/29.24 in both arms, identical to four decimals.
    volatility_scale_cap: float = 1.0
    # Size by inverse volatility -- risk parity -- rather than giving every
    # asset the same notional.
    #
    # `notional_for` sized purely off equity and confidence, so a 5%-a-day asset
    # and a 15%-a-day asset were bought in identical size and the portfolio's
    # risk collected in whichever names happened to be wildest. Measured across
    # the universe's served panels, `natr_14` runs 5.07% at the 10th percentile
    # and 14.86% at the 90th: a 2.9x spread that sizing currently ignores.
    #
    # Kim, Tse & Wald (2016) find time-series momentum's performance comes from
    # the volatility-SCALED returns rather than from the momentum signal, and
    # the crypto momentum-crash literature reports volatility management as what
    # mitigates the crashes. Both are claims about risk-adjusted return, which
    # is why the default target below is set where it is.
    volatility_sizing: bool = False
    # The volatility a position is sized AT. Deliberately defaulted to the
    # measured universe median of `natr_14`, so switching the tilt on leaves the
    # MEDIAN position size untouched and only redistributes size between quiet
    # and violent assets. That separates the risk parity effect from a plain
    # leverage increase -- the two are otherwise impossible to attribute, which
    # is the same mistake `stop_loss_pct` made by doing two jobs at once.
    volatility_sizing_target: float = 0.085
    # Which served column measures it. A parameter rather than a constant so a
    # sweep can try `natr_20` without a code change.
    volatility_sizing_column: str = "natr_14"
    # Capacity and drawdown controls. The zero/one defaults preserve existing
    # library callers; production thresholds are supplied by configuration.
    minimum_daily_quote_volume: float = 0.0
    volume_lookback: int = 20
    maximum_volume_participation: float = 1.0
    drawdown_deleverage_start: float = 0.10
    # How far price is assumed to move against a position when sizing it --
    # the denominator of `risk_budget / distance`. This used to BE
    # `stop_loss_pct`, which made the exit distance and the position size one
    # inseparable decision: widening the stop from 5% to 20% moved the exit
    # AND cut notional to a quarter, so neither effect could be attributed and
    # "wide stop, full size" could not be expressed at all. QUANT13 measured
    # the two separately at matched exposure and found the exit distance worth
    # +26.7 points on its own, which is the reason they are now separate.
    #
    # `None` means "use stop_loss_pct", so every policy already stored in the
    # database keeps its exact previous behaviour.
    risk_distance_pct: float | None = None
    # Where the de-leverage ramp reaches zero risk. This used to BE
    # `maximum_drawdown`, which gave that one number two unrelated jobs: the
    # hard abort threshold AND the far end of the sizing ramp. Raising the
    # abort from 25% to 30% to allow a deeper excursion therefore ALSO made
    # every position larger at every drawdown level along the way, so the two
    # effects could not be told apart -- the same coupling QUANT14 removed from
    # `stop_loss_pct`.
    #
    # `None` means "use maximum_drawdown", so every stored policy keeps its
    # exact previous behaviour and no historical result moves.
    drawdown_deleverage_end: float | None = None
    # What the drawdown limit is measured AGAINST. This is a mandate question,
    # not a tuning knob, and the two answers behave completely differently.
    #
    # "peak" -- the classical definition, distance below the running high-water
    # mark. It has a failure mode this laboratory walked straight into: the
    # de-leverage ramp is driven by the same number, so once equity sits near
    # the ramp's end the risk budget collapses, every candidate position falls
    # under `minimum_position_fraction`, and nothing opens. Equity then cannot
    # grow, so the peak never updates and the drawdown never shrinks. It is a
    # one-way ratchet: S00852 earned +1480% by 2021-05-19 and then held zero
    # positions for four and a half years, which is the flat line the operator
    # spotted on the equity chart. The strategy was not being cautious, it was
    # bricked.
    #
    # "initial" -- distance below the STARTING capital. The operator's mandate:
    # "I deposit 100,000 and never want to lose more than 25% of it; if it grows
    # to 400,000 and gives back 150,000 that is not a problem." The constraint
    # binds hard early, when there are no profits to risk, and relaxes as the
    # account compounds, which is what lets a winner keep running instead of
    # being throttled for having had a good year.
    # "ratchet" -- the operator's refinement, and the default worth arguing for.
    # It keeps the initial-capital floor and then STEPS IT UP as profit is made,
    # banking `profit_banked_fraction` of the highest profit ever reached. The
    # operator's own example fixes the parameter: "if it made 300,000 and gives
    # back 150,000 that is not a problem" is exactly banking half. So a run that
    # peaked at 400,000 may fall to 225,000 (75,000 base floor + half of the
    # 300,000 profit) before the mandate is breached.
    #
    # This is the only one of the three that limits BOTH real capital loss and
    # the giveback of accumulated profit, without the peak basis's ratchet bug:
    # the floor moves on peak PROFIT, not on distance from the peak, so ordinary
    # volatility never throttles the risk budget toward zero.
    drawdown_basis: str = "peak"
    profit_banked_fraction: float = 0.5
    # How long a position may stay open before it is closed regardless of what
    # the signal says. H-011 decomposed the loss and found the exit, not the
    # entry, is what bleeds: SIGNAL_EXIT closed 858 trades on the 2022-2025
    # holdout at a 10% win rate for -806,635, and 128 trades in 2026 at a 2%
    # win rate. Bucketed by realised duration the shape is identical in both
    # eras -- everything resolving inside three days makes money, everything
    # held longer loses -- which is one of the very few properties in this
    # project whose sign does NOT flip between the 2017-2021 and 2022-2025
    # markets.
    #
    # That bucketing is conditional on outcome, so it justifies testing a time
    # stop, not assuming one: cutting at day three truncates a loser at its
    # day-three loss, it does not convert it into a winner.
    #
    # `None` means no time stop, so every policy already stored in the database
    # keeps its exact previous behaviour and no historical result moves.
    maximum_holding_days: int | None = None

    def __post_init__(self) -> None:
        if 0 < self.maximum_position_fraction < self.minimum_position_fraction:
            # No position can be both above the floor and under the cap, so the
            # run opens nothing and reports a flat 0.00% as though the signal
            # found nothing. Found by sweeping a 2% cap against the configured
            # 3% floor: zero trades, no warning, four cells of a sweep wasted.
            raise ValueError(
                "maximum_position_fraction is below minimum_position_fraction, "
                "so no position size is legal and the run can never trade"
            )
        if self.drawdown_basis not in ("peak", "initial", "ratchet"):
            raise ValueError("drawdown_basis must be 'peak', 'initial' or 'ratchet'")
        if not 0.0 <= self.profit_banked_fraction < 1.0:
            # At 1.0 the floor equals the peak and no giveback is tolerated at
            # all, which reintroduces the peak basis's pathology by another name.
            raise ValueError("profit_banked_fraction must be in [0, 1)")
        if self.volatility_sizing and self.volatility_sizing_target <= 0:
            # A zero or negative target sizes every position at zero or inverts
            # the tilt, and both read downstream as "the signal found nothing".
            raise ValueError(
                "volatility_sizing_target must be greater than 0 when "
                "volatility_sizing is on"
            )
        if self.volatility_scale_cap <= 0:
            # Zero or negative would size every position at zero (or backwards),
            # which reads downstream as "the signal found nothing" rather than
            # as a misconfiguration -- the same silent-zero failure the
            # position-fraction check above exists to prevent.
            raise ValueError("volatility_scale_cap must be greater than 0")
        if self.maximum_holding_days is not None and self.maximum_holding_days < 1:
            # Zero would close every position on the bar it opened, which is not
            # a time stop but a way to pay costs for nothing.
            raise ValueError("maximum_holding_days must be at least 1, or None")

    def equity_floor(self, initial: float, peak: float) -> float:
        """The equity level at which this policy declares the mandate breached."""
        base = initial * (1 - self.maximum_drawdown)
        if self.drawdown_basis != "ratchet":
            return (
                base
                if self.drawdown_basis == "initial"
                else peak * (1 - self.maximum_drawdown)
            )
        return base + self.profit_banked_fraction * max(0.0, peak - initial)

    def drawdown_against(self, equity: float, peak: float, initial: float) -> float:
        """How far under water this policy considers the account to be.

        Expressed as a fraction so one number can drive both the abort and the
        de-leverage ramp: the reference is whatever level would put `equity` at
        the floor when the fraction reaches `maximum_drawdown`. For "peak" and
        "initial" that reduces to the obvious definitions.
        """
        if self.drawdown_basis == "peak":
            reference = peak
        elif self.drawdown_basis == "initial":
            reference = initial
        else:
            floor = self.equity_floor(initial, peak)
            reference = (
                floor / (1 - self.maximum_drawdown)
                if self.maximum_drawdown < 1
                else floor
            )
        if reference <= 0:
            return 0.0
        return max(0.0, 1 - equity / reference)

    @property
    def sizing_distance(self) -> float:
        """The distance used to size a position, independent of the exit."""
        distance = (
            self.stop_loss_pct
            if self.risk_distance_pct is None
            else self.risk_distance_pct
        )
        if not 0 < distance < 1:
            raise ValueError("risk_distance_pct must be in (0, 1)")
        return distance

    @property
    def deleverage_end(self) -> float:
        """The drawdown at which the sizing ramp reaches zero risk."""
        end = (
            self.maximum_drawdown
            if self.drawdown_deleverage_end is None
            else self.drawdown_deleverage_end
        )
        if end < self.drawdown_deleverage_start:
            # Equal start and end is legitimate and in use: it collapses the
            # ramp to a step, which is how a policy switches de-leveraging off
            # entirely. Only an inverted ramp is meaningless.
            raise ValueError(
                "drawdown_deleverage_end must not be below drawdown_deleverage_start"
            )
        return end

    def risk_multiplier(self, drawdown: float) -> float:
        """How much of the risk budget survives at this drawdown. The ramp.

        Linear from full size at `drawdown_deleverage_start` to nothing at
        `deleverage_end`. Collapsing the two to the same number turns the ramp
        into a step, which is how a policy switches de-leveraging off.

        This is the piece the operator separated from the abort threshold: the
        ramp still ends at 25% while the mandate aborts at 30%, so a run may
        keep breathing past the point where it stops adding risk.
        """
        start, end = self.drawdown_deleverage_start, self.deleverage_end
        if drawdown <= start:
            return 1.0
        if drawdown >= end:
            return 0.0
        if end <= start:
            return 0.0
        return 1.0 - (drawdown - start) / (end - start)

    def volatility_scale(self, volatility: float | None) -> float:
        """How far to lean into, or away from, one asset's own volatility.

        `1.0` -- size it exactly as before -- whenever the tilt is off, the
        column is missing, or the value is not usable. A missing measurement is
        an absence of information, and the only honest response to that is to
        change nothing rather than to guess a direction.
        """
        if not self.volatility_sizing or volatility is None:
            return 1.0
        try:
            observed = float(volatility)
        except (TypeError, ValueError):
            return 1.0
        if observed <= 0 or observed != observed:  # NaN fails its own equality
            return 1.0
        return min(self.volatility_scale_cap, self.volatility_sizing_target / observed)

    def notional_for(
        self,
        equity: float,
        confidence: float,
        drawdown: float = 0.0,
        volatility: float | None = None,
    ) -> float:
        """What to buy, in quote currency. Zero means "not worth taking".

        Risk-budget sizing: a fraction of equity is put at risk, and the
        position is that budget divided by how far price is assumed to move
        against it. `sizing_distance` is deliberately NOT the stop: QUANT13
        measured the exit distance and the position size separately at matched
        exposure and found the exit worth +26.7 points on its own, which cannot
        even be expressed while one number does both jobs.

        Returning 0.0 rather than a tiny number is the point of the floor. Once
        the ramp throttles the budget, notional collapses toward the exchange
        minimum and a run grinds out thousands of ten-dollar trades that are
        pure noise -- a quarter of one strategy's ledger closed for less than
        fifty cents.
        """
        if equity <= 0 or confidence < self.minimum_confidence:
            return 0.0
        multiplier = self.risk_multiplier(drawdown)
        if multiplier <= 0:
            return 0.0
        budget = (
            equity
            * self.risk_per_trade
            * confidence
            * multiplier
            * self.volatility_scale(volatility)
        )
        notional = budget / self.sizing_distance
        notional = min(notional, equity * self.maximum_position_fraction)
        if notional < max(
            equity * self.minimum_position_fraction, self.minimum_order_notional
        ):
            return 0.0
        return notional

    @property
    def exposure_calibration(self) -> dict[str, Any]:
        """What this policy assumes about the scope it is applied to.

        A policy is only meaningful relative to a bar interval and an asset
        count. `maximum_position_fraction` of 0.2 across 386 daily assets is a
        fully-invested portfolio; the same number on one hourly asset caps the
        run at 20% of capital and silently divides every published return by
        five. Recording the assumption lets a run flag the mismatch instead of
        producing an uninterpretable number.
        """
        return {
            "assets_for_full_investment": (
                math.ceil(1.0 / self.maximum_position_fraction)
                if self.maximum_position_fraction > 0
                else None
            ),
            "maximum_concurrent_assets": self.maximum_concurrent_assets,
            "sizing_distance": self.sizing_distance,
        }


def policy_keys() -> tuple[str, ...]:
    """Every field a stored policy can carry, derived from the dataclass itself.

    This used to be a hand-maintained tuple in `historical.py` and another in
    `forward.py`, and the duplication cost a real result: `drawdown_deleverage_end`
    was added to `MoneyManagement` and to neither list, so both evaluators
    silently dropped it when rebuilding a stored policy. It fell back to
    `maximum_drawdown`, which had just been raised to 0.30, and the de-leverage
    ramp quietly widened -- average exposure 18.7% instead of 8.1%, and a
    configuration measured legal at 24.72% drawdown aborted at 31.35%.

    Deriving the list makes that class of drift impossible: a new field is
    threaded through both phases the moment it exists.
    """
    return tuple(field.name for field in fields(MoneyManagement))
