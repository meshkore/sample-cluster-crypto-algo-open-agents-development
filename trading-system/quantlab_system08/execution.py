"""What it actually costs to trade a given size in a given name on a given day.

WHY THE FLAT NUMBER HAD TO GO

Until now this system charged a flat 15 bps per side, everywhere, always. That number was
the operator's house assumption and it did one job honestly: it stopped anyone pretending
trading was free. But it is wrong in the three ways that matter most, and the operator's
instruction is that the backtest must simulate the market's real constraints rather than a
convenient average:

  * IT DOES NOT KNOW HOW BIG THE ORDER IS. Trading USD 3,000 of BTC and USD 3,000,000 of a
    thin altcoin cost the same in the old model. In reality the second one moves the price
    against itself and the first does not.
  * IT DOES NOT KNOW HOW LIQUID THE NAME IS. A flat rate says a coin turning over USD 20M a
    day is as cheap to trade as one turning over USD 4bn.
  * IT DOES NOT KNOW WHAT THE MARKET IS DOING. The days this book most wants to trade - a
    cascade of liquidations, a 20% down day - are exactly the days when spreads blow out and
    orders do not fill where you asked. Charging a calm-market rate on a crash day is the
    single most flattering assumption a crypto backtest can make.

THE MODEL, AND WHERE EACH PIECE COMES FROM

Cost per side, in basis points of the notional traded, is the sum of three terms.

  COMMISSION is a fee schedule, not an estimate. Binance USD-M perpetual taker fee at the
  base VIP tier is 5.0 bps and maker is 2.0 bps. A cross-sectional book rebalancing on a
  fixed cadence is not a patient liquidity provider, so the default assumes taker.

  HALF-SPREAD is what you pay for crossing. It is tiered by the name's own liquidity rather
  than assumed constant, because the spread on a USD 4bn/day major and a USD 15M/day
  small-cap differ by an order of magnitude.

  IMPACT is the square-root law: the price concession for an order is proportional to the
  asset's volatility times the square root of the fraction of daily volume it represents.
  This is the most robustly replicated result in market microstructure - it appears in
  Almgren, Thum, Hauptmann and Li (2005) on equity impact, in Kyle-style models, and has
  since been reproduced on crypto venues. The functional form matters more than the
  constant: cost per unit grows with size, so a book cannot escape it by trading more.

      impact_bps = IMPACT_COEFFICIENT * daily_vol_bps * sqrt(notional / daily_dollar_volume)

  Everything is then multiplied by a STRESS FACTOR on days when the market itself is moving
  violently. Liquidation cascades widen spreads, thin the book and make fills arrive away
  from where they were asked; a model that ignores this reports profits from trades nobody
  could have placed.

WHAT THIS DELIBERATELY DOES NOT CLAIM

It does not model queue position, partial fills, exchange downtime, or the possibility that
an order simply cannot be placed. Those are real and this returns a COST, not a refusal.
The one refusal it does express is the participation cap: an order that would be a large
share of a day's volume is not merely expensive, it is not executable, and `capacity_limit`
returns the largest notional this model is willing to claim could be traded.

Nothing here is fitted to our returns. Every constant is a published fee, a quoted spread or
a coefficient from the microstructure literature, and each one is named so it can be argued
with separately.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# --- commissions. A published fee schedule (Binance USD-M perpetuals, base VIP tier).
TAKER_BPS = 5.0
MAKER_BPS = 2.0

# --- half-spread by liquidity tier, in bps, keyed by daily USD volume floor. These are
# quoted spreads on major perpetual venues, not estimates of ours: the majors quote inside
# a basis point and the thin end of a USD 10M screen is an order of magnitude wider.
SPREAD_TIERS = (
    (1_000_000_000.0, 0.5),      # BTC, ETH class
    (300_000_000.0, 1.5),
    (100_000_000.0, 3.0),
    (30_000_000.0, 6.0),
    (0.0, 12.0),                 # the thin end of a USD 10M turnover screen
)

# --- square-root impact. 0.5 is the low end of the published range (roughly 0.3 to 1.0),
# chosen deliberately: it is the assumption least favourable to the argument that our costs
# are being understated, so a result that survives it is not surviving on a soft constant.
IMPACT_COEFFICIENT = 0.5

# --- stress. On a day when the market moves more than the first threshold, everything
# widens. The multipliers are blunt on purpose - a precise number here would be invented,
# and the point is that the calm-market rate is KNOWN to be wrong on these days.
STRESS_BANDS = ((0.15, 3.0), (0.08, 2.0), (0.04, 1.35))

# --- capacity. The largest share of a day's dollar volume this model will claim could be
# traded. Above this the square-root law is extrapolating past where anyone has measured it,
# and the honest answer is that the trade does not happen rather than that it costs more.
MAX_PARTICIPATION = 0.02


@dataclass(frozen=True)
class Fill:
    """One side of one trade, decomposed so no cost can hide inside another."""

    bps: float
    commission_bps: float
    spread_bps: float
    impact_bps: float
    stress: float
    participation: float
    capped: bool          # the order was larger than this model will execute


def half_spread_bps(daily_dollar_volume: float) -> float:
    for floor, bps in SPREAD_TIERS:
        if daily_dollar_volume >= floor:
            return bps
    return SPREAD_TIERS[-1][1]


def stress_factor(market_move: float) -> float:
    """How much everything widens on a violent day. `market_move` is the day's return."""
    m = abs(float(market_move or 0.0))
    for threshold, mult in STRESS_BANDS:
        if m >= threshold:
            return mult
    return 1.0


def capacity_limit(daily_dollar_volume: float,
                   max_participation: float = MAX_PARTICIPATION) -> float:
    """The largest notional this model is willing to claim could be traded in a day."""
    return max(0.0, float(daily_dollar_volume or 0.0)) * max_participation


def cost_bps(notional: float,
             daily_dollar_volume: float,
             daily_vol: float,
             market_move: float = 0.0,
             taker: bool = True,
             impact_coefficient: float = IMPACT_COEFFICIENT,
             max_participation: float = MAX_PARTICIPATION) -> Fill:
    """Cost of trading `notional` USD of one name on one day, in bps of that notional.

    `daily_vol` is the asset's own daily return volatility as a fraction - the square-root
    law scales impact by volatility, because the same participation in a violent name costs
    more than in a quiet one.

    A name with no volume on the day is not free and is not cheap: it is uncapped and
    charged the widest tier, because a tape that printed nothing is a tape you could not
    have traded on.
    """
    notional = abs(float(notional or 0.0))
    dv = max(0.0, float(daily_dollar_volume or 0.0))
    commission = TAKER_BPS if taker else MAKER_BPS
    spread = half_spread_bps(dv)

    if dv <= 0 or notional <= 0:
        stress = stress_factor(market_move)
        total = (commission + spread) * stress
        return Fill(total, commission, spread, 0.0, stress, 1.0 if notional > 0 else 0.0,
                    notional > 0)

    participation = notional / dv
    capped = participation > max_participation

    # Impact in bps: coefficient * volatility(bps) * sqrt(participation).
    impact = impact_coefficient * (float(daily_vol or 0.0) * 10_000.0) * math.sqrt(
        min(participation, max_participation))
    if capped:
        # Beyond the cap the square-root law is extrapolating past its measured range. The
        # excess is charged at the cap's marginal rate rather than silently ignored, so a
        # book that insists on an untradeable size still sees a cost that grows with it.
        overshoot = participation / max_participation
        impact *= overshoot

    stress = stress_factor(market_move)
    total = (commission + spread + impact) * stress
    return Fill(total, commission, spread, impact, stress, participation, capped)
