"""Money management for a system that trades hours, not months.

This does NOT define a new policy type. It supplies intraday *defaults* for
`quantlab_trading.policy.MoneyManagement` -- the dataclass the whole laboratory
already stores, fingerprints and reconstructs -- because inventing a parallel
policy object would make this system's runs unreadable by every tool that knows
the existing one. The fields are the same fields; only the numbers differ, and
each difference below is justified rather than tuned.

What is genuinely new lives here as functions rather than fields:

- **the round-trip cost**, as a number the entry rule can compare against. At
  daily resolution 30 bps is a rounding error against a 6% swing; at 15 minutes
  it is most of the move, so it has to be visible to the signal, not only to
  the ledger;
- **volatility-scaled sizing**, because the distance to the stop is a different
  number on every bar and every symbol. `MoneyManagement.notional_for` divides
  the risk budget by the scalar `sizing_distance`, which cannot express "two
  ATR below this particular close". The policy's fields are still what decide
  the size -- this is the structural-protocol arrangement working as intended,
  a caller reading the members it needs;
- **the turnover floor in the right unit.** The charter's capacity invariant is
  $10M of *daily* quote turnover. The served `dollar_volume_20` column at 15m
  is an average over twenty 15-minute bars, so comparing it to the daily figure
  would silently make the gate 96 times stricter and leave the universe empty.
"""

from __future__ import annotations

from quantlab_trading.policy import MoneyManagement

# 10 bps commission plus 5 bps slippage, each way. `CostModel` applies exactly
# these, so this constant is the entry rule's view of the same arithmetic the
# ledger performs -- if one moves, both move.
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0

# The charter's capacity floor, per DAY. Never relax it: an edge that only
# exists below $1,000 of order size is not an edge.
DAILY_TURNOVER_FLOOR = 10_000_000.0
# 5-minute bars. Every caller passes its own, so this is the default rather
# than an assumption baked into the arithmetic.
BARS_PER_DAY = 288


def round_trip_cost(
    commission_bps: float = COMMISSION_BPS, slippage_bps: float = SLIPPAGE_BPS
) -> float:
    """What a complete trade costs, as a fraction of notional.

    Both legs, both components: 0.30% by default. Every entry threshold in this
    system is expressed as a multiple of this number, so changing the cost model
    moves the thresholds with it instead of quietly making the system trade a
    loss it can no longer see.
    """
    return 2 * (commission_bps + slippage_bps) / 10_000


def bar_turnover_floor(
    daily_floor: float = DAILY_TURNOVER_FLOOR, bars_per_day: int = BARS_PER_DAY
) -> float:
    """The per-bar turnover that corresponds to a daily capacity floor.

    $10M a day is ~$35k per 5-minute bar. The number looks small and is the
    same constraint: it is the same dollars, counted over the interval the
    indicator actually averages.
    """
    if bars_per_day <= 0:
        raise ValueError("bars_per_day must be positive")
    return daily_floor / bars_per_day


# Why each of these differs from the daily system's defaults.
#
# `risk_per_trade` 0.0015 -- and this number is not a preference, it is forced.
#   Sizing divides the risk budget by the distance to the stop, and at 15m that
#   distance is ~0.6% rather than the daily system's ~5%. Carrying the daily
#   0.01 across therefore asks for a position of 167% of equity on every trade,
#   which `maximum_position_fraction` silently truncates to the cap -- so every
#   position would be exactly 30% of equity, the ATR scaling would never
#   operate at all, and nothing in any result would say so. Found by the test
#   that asserts a tight stop takes a bigger position than a wide one; it did
#   not, because both were clamped. At 0.0015 a 0.6% stop takes 25% of equity
#   and the scaling is live across the whole realistic range.
# `maximum_position_fraction` 0.30 with `maximum_concurrent_assets` 3 -- the
#   charter's arithmetic, applied honestly: on a five-symbol universe, 2% per
#   position is an index fund with commission. Three positions at up to 30% is
#   a portfolio that can move the account, and 90% is the most that can ever be
#   deployed, which is the number a reader should be able to derive.
# `minimum_position_fraction` 0.02 -- a hard floor with a recorded reason. One
#   of this laboratory's ledgers closed a quarter of its trades for under fifty
#   cents once the de-leverage ramp throttled sizing; at 15m that failure mode
#   is not a tail risk, it is the default outcome of an unbounded floor.
# `drawdown_basis` "initial" -- QUANT17. Peak-basis sizing is a one-way ratchet:
#   the ramp collapses the risk budget, nothing opens, equity cannot grow, the
#   peak never updates and the account is bricked while reporting itself legal.
#   The ABORT is still measured against the peak, in the brain, because that is
#   what the summary reports and what the operator's 25% rule means.
# `maximum_holding_days` None -- deliberately. The time stop this system needs
#   is four hours; the field counts days and cannot say that, so the brain
#   counts bars itself. Leaving the field None means no stored policy changes
#   meaning and no existing evaluator sees a field it does not expect.
# `risk_distance_pct` 0.02 -- recorded for the fingerprint and for any tool
#   that sizes through `notional_for`. This system sizes through
#   `position_notional` below, which uses the live ATR distance instead.
INTRADAY_DEFAULTS = {
    "risk_per_trade": 0.0015,
    "maximum_position_fraction": 0.30,
    "minimum_position_fraction": 0.02,
    "maximum_concurrent_assets": 3,
    "minimum_order_notional": 100.0,
    "maximum_drawdown": 0.25,
    "drawdown_basis": "initial",
    "drawdown_deleverage_start": 0.10,
    "drawdown_deleverage_end": 0.25,
    "stop_loss_pct": 0.02,
    "take_profit_pct": 0.01,
    "risk_distance_pct": 0.02,
    "minimum_confidence": 0.0,
    "maximum_holding_days": None,
    "minimum_daily_quote_volume": DAILY_TURNOVER_FLOOR,
    "volume_lookback": 20,
}


def intraday_money_management(**overrides: object) -> MoneyManagement:
    """The intraday policy: the laboratory's dataclass, this system's numbers."""
    settings = dict(INTRADAY_DEFAULTS)
    settings.update(overrides)
    return MoneyManagement(**settings)  # type: ignore[arg-type]


def position_notional(
    policy: MoneyManagement,
    equity: float,
    stop_distance_pct: float,
    drawdown: float = 0.0,
    scale: float = 1.0,
) -> float:
    """What to buy, sized by the distance to *this* bar's stop. 0 means skip.

    Risk-budget sizing, identical in spirit to `MoneyManagement.notional_for`
    and different in one respect: the denominator is the live volatility-scaled
    stop distance rather than a constant. A quiet bar therefore takes a larger
    position for the same risk and a violent one takes a smaller one, which is
    the entire reason to size off ATR at all.

    Returning 0.0 rather than a tiny number is the point of the floor: once the
    de-leverage ramp throttles the budget, a system trading four times a day
    would otherwise grind out thousands of positions too small to matter and
    pay full costs on every one of them.

    `scale` multiplies the risk budget by how strong THIS signal is, and it is
    applied here rather than to the result so that the position cap and the
    minimum-size floor still bound the answer. A caller that scaled the returned
    notional instead would silently exceed `maximum_position_fraction`, which is
    the one number a reader uses to derive how much of the book can ever be at
    risk. Default 1.0: sizing is flat unless a hypothesis argues otherwise.
    """
    if equity <= 0 or stop_distance_pct <= 0:
        return 0.0
    multiplier = policy.risk_multiplier(drawdown)
    if multiplier <= 0:
        return 0.0
    budget = equity * policy.risk_per_trade * multiplier * max(0.0, scale)
    notional = budget / stop_distance_pct
    notional = min(notional, equity * policy.maximum_position_fraction)
    floor = max(
        equity * policy.minimum_position_fraction, policy.minimum_order_notional
    )
    return 0.0 if notional < floor else notional
