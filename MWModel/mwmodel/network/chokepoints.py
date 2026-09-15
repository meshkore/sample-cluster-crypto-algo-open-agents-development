"""THE VALVES OF THE WORLD - where a fifth of the oil has to pass through a strait.

The operator's question was about two of these: *"el estrecho de Ormuz y el estrecho de Bab
el-Mandeb están ocupados... se está dificultando el paso de petróleo"*. They are modelled the
way every route is modelled - as an edge with a capacity - so a blockade is not a special case
bolted on. It is a capacity that has fallen, and everything downstream follows from ordinary
behaviour: a shipper takes the next cheapest route with room, the voyage gets longer, freight
and war-risk insurance rise, and the delivered price of a barrel goes up even though not one
barrel fewer was lifted out of the ground.

That distinction matters more than it looks. **A chokepoint event is usually not a supply
shock. It is a LOGISTICS shock**, and the two behave differently: the first removes barrels,
the second delays them and makes them dearer. Bab el-Mandeb in 2024 is the clean example -
traffic collapsed, tankers went round the Cape, voyages lengthened by ten to fourteen days,
freight multiplied, and the crude price barely moved because the oil still arrived. Hormuz is
the opposite case, and the reason it is the one that frightens people: there is almost no way
around it.

CAPACITIES ARE IN MILLIONS OF BARRELS PER DAY of crude and products, and the figures are
order-of-magnitude public knowledge pending the phase-1 ingest that replaces them with a real
series. Each is marked with how much of it can be bypassed, because the bypass is the whole
difference between an inconvenience and a crisis.
"""

from __future__ import annotations

from ..state import Edge, WorldState

#: key -> (name, base capacity mb/d, bypass capacity mb/d, extra days by the alternative route,
#:         extra cost USD/bbl on the alternative, note)
CHOKEPOINTS: dict[str, tuple] = {
    "hormuz": (
        "Strait of Hormuz", 21.0, 2.6, 0.0, 3.5,
        "Roughly a fifth of global liquids. The only bypasses are two pipelines - the Saudi "
        "East-West line to the Red Sea and the Emirati line to Fujairah - which together move "
        "a small fraction of the flow. There is no sea route around it. This is why it is the "
        "one chokepoint whose closure is a price event rather than a freight event."),
    "bab_el_mandeb": (
        "Bab el-Mandeb / Suez", 8.8, 8.0, 12.0, 6.0,
        "Almost fully bypassable around the Cape of Good Hope, at the cost of ten to fourteen "
        "days and a large freight and war-risk premium. The 2024 disruption is the reference "
        "case: traffic collapsed, the oil still arrived, and crude barely moved."),
    "malacca": (
        "Strait of Malacca", 23.7, 18.0, 5.0, 2.0,
        "The route from the Gulf to Asia. Lombok and Sunda can take much of it with a few "
        "days added, so it is a cost shock rather than a supply one."),
    "suez_canal": (
        "Suez Canal + SUMED", 9.2, 8.5, 12.0, 5.5,
        "Shares its fate with Bab el-Mandeb; kept separate because the canal can close for "
        "reasons the strait cannot, as 2021 demonstrated."),
    "turkish_straits": (
        "Bosphorus / Dardanelles", 3.2, 1.0, 0.0, 4.0,
        "Russian and Caspian crude to the Mediterranean. Hard to bypass; small enough that "
        "its closure is regional rather than global."),
    "panama": (
        "Panama Canal", 1.0, 0.9, 20.0, 4.5,
        "Small for oil and large for everything else. Included because drought has already "
        "constrained it twice, which makes it the model's example of a capacity that falls "
        "for climatic rather than political reasons."),
}

#: Producer -> how its exports are routed. Fractions need not sum to one: what is not routed
#: through a named chokepoint reaches the market freely.
ROUTES: dict[str, dict[str, float]] = {
    "country.SAU": {"hormuz": 0.75, "bab_el_mandeb": 0.10},
    "country.IRN": {"hormuz": 0.95},
    "country.IRQ": {"hormuz": 0.85, "turkish_straits": 0.05},
    "country.ARE": {"hormuz": 0.70},
    "country.KWT": {"hormuz": 1.00},
    "country.QAT": {"hormuz": 1.00},
    "country.RUS": {"turkish_straits": 0.20},
    "country.KAZ": {"turkish_straits": 0.60},
    "country.NGA": {},
    "country.USA": {},
    "country.CAN": {},
    "country.BRA": {},
    "country.NOR": {},
    "country.VEN": {},
    "country.LBY": {"suez_canal": 0.15},
    "country.DZA": {"suez_canal": 0.10},
}


def seed_edges(w: WorldState) -> None:
    for key, (name, cap, bypass, days, cost, note) in CHOKEPOINTS.items():
        w.edges[key] = Edge(key=key, frm="", to="", capacity=cap, base_capacity=cap,
                            days=days, cost=cost, note=f"{name}. {note}")
        w.set_var(f"edge.{key}", "bypass", bypass)


def constrain(w: WorldState, key: str, open_fraction: float, why: str = "") -> None:
    """Narrow or reopen a valve. The single lever every geopolitical scenario pulls."""
    e = w.edges[key]
    e.capacity = e.base_capacity * max(0.0, min(1.0, open_fraction))
    w.log(f"edge.{key}", "capacity", open_fraction=e.open_fraction, why=why)


def delivered(w: WorldState, producer: str, qty: float) -> tuple[float, float]:
    """How much of `qty` actually reaches the market, and what the detour costs per barrel.

    The bypass is what decides whether a constraint destroys barrels or merely taxes them, so
    it is applied explicitly: whatever cannot pass the narrowed strait tries the alternative
    route, up to that route's own capacity, and pays for the extra distance and the war-risk
    premium. Only what fits through neither is lost.
    """
    routes = ROUTES.get(producer, {})
    if not routes:
        return qty, 0.0

    lost, extra_cost, routed = 0.0, 0.0, 0.0
    for key, share in routes.items():
        e = w.edges.get(key)
        if e is None or share <= 0:
            continue
        through = qty * share
        routed += through
        blocked = through * (1.0 - e.open_fraction)
        if blocked <= 0:
            continue
        bypass_room = max(0.0, w.var(f"edge.{key}", "bypass", 0.0) - w.var(
            f"edge.{key}", "bypass_used", 0.0))
        rerouted = min(blocked, bypass_room)
        w.set_var(f"edge.{key}", "bypass_used",
                  w.var(f"edge.{key}", "bypass_used", 0.0) + rerouted)
        lost += blocked - rerouted
        extra_cost += rerouted * e.cost

    out = max(0.0, qty - lost)
    return out, (extra_cost / out if out > 0 else 0.0)


def reset_bypass(w: WorldState) -> None:
    """Bypass capacity is a per-tick resource, not a bank. Called at the start of each tick."""
    for key in CHOKEPOINTS:
        w.set_var(f"edge.{key}", "bypass_used", 0.0)


def status(w: WorldState) -> list[dict]:
    """What every valve is doing, for the viewer and for the journal."""
    out = []
    for key, (name, cap, bypass, days, cost, note) in CHOKEPOINTS.items():
        e = w.edges.get(key)
        if e is None:
            continue
        out.append({"key": key, "name": name, "open": e.open_fraction,
                    "capacity": e.capacity, "base": e.base_capacity,
                    "bypass": bypass, "detour_days": days, "detour_cost": cost,
                    "flow": e.flow, "note": note})
    return out
