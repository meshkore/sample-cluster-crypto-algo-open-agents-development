"""THE CARRIERS - the operator's own worked example, built as it was described.

    *"Imagine you are a shipping company with a thousand ships making so many routes. When the
    price of oil rises we publish an event. The ship is subscribed to the fuel channel, so it
    hears it, and its own model says: fuel went up, I raise my freight rates. And because this
    company sails between China, Europe and Oceania and nowhere else, it publishes to the
    freight channel of THOSE lanes. Everyone who consumes those lanes hears it, and inflation
    hears it too."*

Three segments rather than three companies, under the roster rule: container liners, crude and
product tankers, dry bulk. Each is the publisher of record for its own lanes, listens to the
bunker channel and to the valves, and sets a rate.

WHAT MAKES A FREIGHT RATE MOVE, and why only two things are modelled here

    fuel        a cost, passed through almost fully over months and partially over weeks.
                Bunker is roughly a quarter to a half of a voyage's cash cost depending on
                segment and on how high rates are at the time.

    capacity    the one that actually matters, and the reason freight is the most violent
                price in this model. Shipping capacity is ships times speed divided by voyage
                length, so a longer voyage DESTROYS CAPACITY without a single ship being lost.
                When Red Sea transits stopped in December 2023, Asia-Europe voyages went from
                about 26 days via Suez to about 38 around the Cape: a third of the capacity on
                that lane evaporated in a fortnight, and spot rates roughly tripled.

That episode is the anchor for `CAPACITY_ELAS` below, and it is ONE OBSERVATION. It is written
as an assertion with its source, not as a fitted parameter, and the calibrator is not allowed
to pretend otherwise until the freight indices are ingested.

WHAT IS DELIBERATELY MISSING
Freight is a price signal here and not yet a settlement: nobody's cash balance changes when a
rate rises, because the shippers who would pay it are not modelled as counterparties yet. The
conservation law is therefore untouched by this module, which is the honest way to add a layer
before its balance sheet exists - but it means carrier profit is not yet a number to trust.
"""

from __future__ import annotations

from ..bus import Event
from ..entity import Entity
from ..state import WorldState

#: Every lane: the chokepoints it needs, the voyage at each end, and what it costs to go
#: round. `detour_days` is the extra time when the chokepoint is unusable.
LANES: dict[str, dict] = {
    "asia_europe":   dict(frm="AS", to="EU", days=26, chokes=("malacca", "bab_el_mandeb",
                                                              "suez_canal"), detour_days=12),
    "asia_namerica": dict(frm="AS", to="NA", days=18, chokes=(), detour_days=0),
    "intra_asia":    dict(frm="AS", to="AS", days=6, chokes=("malacca",), detour_days=3),
    "atlantic":      dict(frm="EU", to="NA", days=10, chokes=(), detour_days=0),
    "gulf_asia":     dict(frm="ME", to="AS", days=18, chokes=("hormuz", "malacca"),
                          detour_days=0),
    "gulf_europe":   dict(frm="ME", to="EU", days=22, chokes=("hormuz", "bab_el_mandeb",
                                                              "suez_canal"), detour_days=10),
    "brazil_china":  dict(frm="SA", to="AS", days=38, chokes=("malacca",), detour_days=4),
    "australia_asia": dict(frm="AS", to="AS", days=12, chokes=(), detour_days=0),
}

#: Which segment publishes which lanes, what it burns, and how much of its cash cost is fuel.
SEGMENTS: dict[str, dict] = {
    "container": dict(name="container liners", fuel_share=0.30,
                      lanes=("asia_europe", "asia_namerica", "intra_asia", "atlantic")),
    "tanker":    dict(name="crude and product tankers", fuel_share=0.42,
                      lanes=("gulf_asia", "gulf_europe")),
    "bulk":      dict(name="dry bulk", fuel_share=0.35,
                      lanes=("brazil_china", "australia_asia")),
}

#: Rate multiplier per unit of lane capacity absorbed by a detour, as an exponent:
#: multiplier = (1 - absorbed) ** -CAPACITY_ELAS. Anchored on the Red Sea rerouting of
#: December 2023 - 12 extra days on a 26-day voyage absorbs 32% of the lane, and container
#: spot rates went up roughly threefold: ln(3) / -ln(1 - 0.32) = 2.9.
CAPACITY_ELAS = 2.9

#: How fast a rate moves towards where the cost and capacity say it should be. Freight is a
#: spot market of weekly fixtures, so it is far faster than crude's 0.06 - but not instant,
#: because contracted volume moves only when contracts roll.
RATE_ADJUST = 0.18

#: WHAT A SHIPPER ACTUALLY PAYS is not the spot rate. Roughly 60% of container volume moves on
#: annual contracts and only the rest is fixed at spot, so a spot rate that triples raises the
#: average freight bill by far less and raises it over a year rather than in a fortnight. This
#: is not a detail: without it the model put a full point of inflation into the euro area from
#: the 2024 Red Sea rerouting, against a published estimate of about a quarter of a point, and
#: the arithmetic was right - the input was the wrong price.
SPOT_SHARE = 0.40
#: Daily roll of the contracted book towards the prevailing spot rate: one year to turn over.
CONTRACT_ROLL = 1.0 / 365.0

#: A chokepoint is unusable below this open fraction. Above it, ships queue and pay; below it,
#: they go round. Not a smooth function in reality either: the Cape decision is a decision.
REROUTE_BELOW = 0.70


class Carrier(Entity):
    """One shipping segment. Hears fuel and valves; speaks rates on the lanes it serves."""

    kind = "carrier"
    #: Freightos Baltic and Baltic Exchange publish these weekly. NOT YET INGESTED.
    targets = ("freight.fbx.asia_europe", "freight.bdi", "freight.td3c")

    def __init__(self, segment: str, **params) -> None:
        spec = SEGMENTS[segment]
        super().__init__(f"carrier.{segment}", spec["name"], **params)
        self.segment = segment
        self.lanes: tuple[str, ...] = tuple(spec["lanes"])
        self.fuel_share: float = spec["fuel_share"]
        self.listens = ("price.bunker.tonne",) + tuple(
            f"valve.{c}" for lane in self.lanes for c in LANES[lane]["chokes"])
        self.subscribed = list(self.listens)
        self.emits = tuple(f"price.freight.{lane}" for lane in self.lanes)
        self.own_topic = f"price.freight.{self.lanes[0]}"

    # ------------------------------------------------------------------ the policy
    def on_event(self, ev: Event, w: WorldState) -> list[Event]:
        why = ("bunker " + format(ev.value, ",.0f") + " USD/t"
               if ev.topic.startswith("price.bunker") else
               ev.topic.split(".", 1)[-1] + " at " + format(ev.value, ".0%") + " of capacity")
        return self.reprice(w, why)

    def reprice(self, w: WorldState, why: str = "") -> list[Event]:
        bunker = w.var("refiner.global", "price.bunker_tonne", 0.0)
        ref = w.var(self.id, "ref_bunker", 0.0)
        if bunker <= 0:
            return []
        if ref <= 0:
            w.set_var(self.id, "ref_bunker", bunker)
            ref = bunker
        fuel_push = self.fuel_share * (bunker / ref - 1.0)

        out: list[Event] = []
        for lane in self.lanes:
            spec = LANES[lane]
            extra = 0.0
            blocked = []
            for choke in spec["chokes"]:
                edge = w.edges.get(choke)
                if edge is None:
                    continue
                if edge.open_fraction < REROUTE_BELOW and spec["detour_days"] > 0:
                    extra = max(extra, spec["detour_days"])
                    blocked.append(choke)
                elif edge.open_fraction < 1.0:
                    # Still passable: the cost is queueing and war-risk insurance, not distance.
                    extra = max(extra, spec["days"] * 0.10 * (1.0 - edge.open_fraction))
            absorbed = extra / (spec["days"] + extra) if extra > 0 else 0.0
            capacity_mult = (1.0 - absorbed) ** -CAPACITY_ELAS if absorbed < 0.95 else 20.0

            want = (1.0 + fuel_push) * capacity_mult
            prev = w.var(self.id, f"rate.{lane}", 1.0)
            rate = prev + RATE_ADJUST * (want - prev)
            w.set_var(self.id, f"rate.{lane}", rate)
            w.set_var(self.id, f"detour_days.{lane}", extra)
            reason = why
            if blocked:
                reason = (", ".join(blocked) + " impassable: +"
                          + format(extra, ".0f") + " days, "
                          + format(absorbed, ".0%") + " of the lane's capacity gone")
            out.append(self.say(f"price.freight.{lane}", rate, unit="index",
                                why=reason, absorbed=round(absorbed, 3),
                                fuel_push=round(fuel_push, 4)))
        return out


def carriers(**params) -> list[Carrier]:
    return [Carrier(seg, **params) for seg in SEGMENTS]


#: How much of each region's imported goods travels on each lane. Rough trade geography, and
#: the first thing the trade-network layer of phase 2 replaces with real bilateral flows -
#: at which point a country will subscribe to the lanes it actually uses rather than the ones
#: its neighbours use.
EXPOSURE: dict[str, dict[str, float]] = {
    "EU": {"asia_europe": 0.45, "atlantic": 0.25, "gulf_europe": 0.20},
    "NA": {"asia_namerica": 0.45, "atlantic": 0.25, "gulf_asia": 0.05},
    "AS": {"intra_asia": 0.40, "asia_europe": 0.20, "gulf_asia": 0.25,
           "brazil_china": 0.10, "australia_asia": 0.10},
    "ME": {"gulf_asia": 0.30, "gulf_europe": 0.30, "intra_asia": 0.10},
    "EA": {"asia_europe": 0.25, "atlantic": 0.10, "gulf_europe": 0.15},
    "SA": {"atlantic": 0.25, "brazil_china": 0.30, "asia_namerica": 0.10},
    "AF": {"asia_europe": 0.25, "gulf_europe": 0.20, "atlantic": 0.15},
    "ROW": {"asia_europe": 0.20, "asia_namerica": 0.15, "intra_asia": 0.20},
}
