"""CLEARING - how a price is found when almost nobody can change their mind quickly.

The single most important number in this module is the short-run price elasticity of oil
demand, and it is about **-0.05**. A one percent shortfall of barrels does not need a one
percent price rise to clear; it needs roughly twenty. That is not an exotic finding, it is the
standard estimate, and it is the entire reason energy shocks are violent: in the short run
almost nobody can drive less, heat less or fly less, so the adjustment has to come out of
price.

INVENTORIES ARE WHAT STOPS THAT BEING THE WHOLE STORY. Stocks absorb a shortfall for as long
as they last, which is why the same disruption is a non-event with ample cover and a crisis
with thin cover. So the clearing here is a function of BOTH the flow gap and the days of cover
behind it, and the asymmetry is deliberate: a surplus builds stock slowly and prices sag; a
deficit drains stock fast and prices spike. Markets fall down the stairs and up the lift.

WHAT THIS IS NOT. There is no order book, no market maker and no intraday dynamic here yet -
those arrive in phase 3, with the agents that own them. This is a daily clearing, and it is
honest about being one.
"""

from __future__ import annotations

from ..state import Market, WorldState

#: Short-run elasticities, by market. Sources are standard estimates and every one of them is
#: a phase-2 calibration target rather than a finding.
ELASTICITY = {"crude": 0.05, "natgas_eu": 0.08, "natgas_us": 0.12}

#: Days of cover at which a market is comfortable, and at which it panics.
NORMAL_COVER = {"crude": 60.0, "natgas_eu": 45.0, "natgas_us": 40.0}
MIN_COVER = {"crude": 25.0, "natgas_eu": 12.0, "natgas_us": 15.0}

#: How hard the price responds to a CHANGE in days of cover. Calibrated against the record
#: rather than derived: through 2022 OECD commercial stocks lost roughly ten days of cover -
#: a sixth of normal - while crude rose about sixty percent, which puts this near 2.4 once the
#: adjustment speed below is taken into account. It is the single most consequential number in
#: the module and the first thing phase 2 fits properly.
SENSITIVITY = {"crude": 2.4, "natgas_eu": 3.2, "natgas_us": 2.8}

#: How much of the required price move happens in one day. Prices do not jump to the clearing
#: level instantly; they walk towards it while participants argue about whether the shortfall
#: is real.
ADJUST = 0.06

#: How violently the price goes convex once cover falls through the floor. This is the term
#: that produces a spike rather than a slope, and it is the hardest one to justify from first
#: principles - which is exactly why it is exposed for fitting.
FLOOR_CONVEX = 1.8

#: A shortfall moves price harder than a surplus of the same size, because the surplus can be
#: stored and the shortfall cannot be conjured.
DEFICIT_ASYMMETRY = 1.6


def clear(w: WorldState, key: str, supply: float, demand: float,
          cost_push: float = 0.0) -> float:
    """Advance one market by one tick and return the new price.

    `cost_push` is the freight and insurance premium the network reports - the part of a
    chokepoint event that raises the DELIVERED cost of a barrel that was never lost. Keeping
    it separate from the supply gap is what lets the viewer say whether a price move was a
    shortage or a detour, which is the difference between Hormuz and Bab el-Mandeb.
    """
    m: Market = w.markets[key]
    m.supply, m.demand = supply, demand

    # WHAT A MARKET PRICES IS THE STOCK, NOT THE FLOW - and getting that wrong was the third
    # and worst defect the scoreboard found. The flow gap was applied as a percentage move
    # every single day, so a persistent surplus of two tenths of one percent compounded into a
    # forty percent collapse over four months while supply and demand stayed matched to within
    # a fifth of a percent. Nobody reprices oil daily because last Tuesday was slightly long.
    #
    # The flow gap enters ONCE, through inventories, and the price responds to how many days
    # of cover those inventories represent. That makes the system self-correcting rather than
    # explosive: a surplus builds stock, stock lowers price, a lower price lifts demand and
    # trims cartel supply, and cover stabilises. Slowly, because the elasticities are small -
    # which is exactly the behaviour the oil market actually shows.
    # The norm is point-in-time when the world has been seeded with real stocks: a trailing
    # ten-year mean of the reporting group's own cover, computed from what had been published
    # on the run's start date. Falling back to a constant would quietly reintroduce exactly
    # the kind of fixed anchor that this model has now been caught on four times.
    normal = w.var("__world", "normal_cover", 0.0) or NORMAL_COVER.get(key, 60.0)
    floor = normal * (MIN_COVER.get(key, 25.0) / NORMAL_COVER.get(key, 60.0))
    cover_days = (m.inventory / demand) if demand > 0 else normal
    tight = (normal - cover_days) / max(normal, 1.0)      # >0 when the tank is low

    # THE LEVEL OF STOCKS IS ALREADY IN TODAY'S PRICE. What moves a price is the CHANGE in
    # tightness, not its level, and confusing the two is the same compounding error this model
    # has now been caught on twice: with real stocks seeded, a steady nine percent below normal
    # produced a steady one percent a day and crude reached two hundred dollars in four months
    # while nothing whatsoever changed. A market that has known for a year that stocks are
    # thin has finished repricing it.
    prev_tight = w.var("__world", f"tight.{key}", tight)
    w.set_var("__world", f"tight.{key}", tight)
    move = SENSITIVITY.get(key, 2.4) * (tight - prev_tight)

    # Below the floor the market stops being a market: nobody sells the last barrel they are
    # allowed to hold, and the premium goes convex. This is the term that produces a spike
    # rather than a slope.
    if cover_days < floor:
        move += FLOOR_CONVEX * ((floor - cover_days) / max(floor, 1.0)) ** 2

    target = m.price * (1.0 + move) + cost_push
    m.price = max(1.0, m.price + ADJUST * (target - m.price))

    # Inventory is NOT updated here. The stock is a real balance owned by `market.<key>` and
    # it changes only through transfers the engine makes, both sides at once.
    m.history.append((w.day, m.price))
    if len(m.history) > 4000:
        del m.history[:1000]

    w.log(key, "clear", price=m.price, supply=supply, demand=demand,
          gap=demand - supply, cover_days=cover_days, cost_push=cost_push,
          why=(f"cover {cover_days:.1f}d against a normal {normal:.0f}" +
               (f", cost push {cost_push:.2f}/bbl" if cost_push else "")))
    return m.price
