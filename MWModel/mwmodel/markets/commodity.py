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

#: How much of the required price move happens in one day. Prices do not jump to the clearing
#: level instantly; they walk towards it while participants argue about whether the shortfall
#: is real.
ADJUST = 0.18

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

    gap = demand - supply                       # positive: the world wants more than it has
    cover_days = (m.inventory / demand) if demand > 0 else NORMAL_COVER.get(key, 60.0)
    normal, floor = NORMAL_COVER.get(key, 60.0), MIN_COVER.get(key, 25.0)

    # How much of the gap inventories can absorb. Full cover absorbs most of it; at the floor
    # they absorb nothing, because nobody will sell the last barrel they are allowed to hold.
    room = (cover_days - floor) / max(normal - floor, 1.0)
    buffer = max(0.0, min(1.0, room))
    effective = gap * (1.0 - 0.72 * buffer) if gap > 0 else gap * (1.0 - 0.35 * buffer)

    elas = ELASTICITY.get(key, 0.05)
    frac = effective / demand if demand > 0 else 0.0
    move = (frac / elas) * (DEFICIT_ASYMMETRY if frac > 0 else 1.0)

    # Thin cover is frightening on its own, before any gap: the scarcity premium is what a
    # market pays for optionality when it can see the bottom of the tank.
    scarcity = max(0.0, (floor - cover_days) / max(floor, 1.0)) * 0.9

    target = m.price * (1.0 + move + scarcity) + cost_push
    m.price = max(1.0, m.price + ADJUST * (target - m.price))

    # Inventory is NOT updated here. The stock is a real balance owned by `market.<key>` and
    # it changes only through transfers the engine makes, both sides at once. A clearing
    # function that also moved stock could create a barrel by arithmetic, and the conservation
    # assertion would then be checking the same mistake twice.
    m.history.append((w.day, m.price))
    if len(m.history) > 4000:
        del m.history[:1000]

    w.log(key, "clear", price=m.price, supply=supply, demand=demand,
          gap=gap, cover_days=cover_days, cost_push=cost_push,
          why=("shortfall" if gap > 0 else "surplus") +
              (f", cost push {cost_push:.2f}/bbl" if cost_push else ""))
    return m.price
