"""THE REFINER - where a barrel becomes the thing people actually buy.

Nobody burns crude. They burn diesel, petrol, jet and bunker fuel, and the gap between crude
and those products - the CRACK SPREAD - is a market of its own that does not move with crude
and sometimes moves against it. Leaving it out was the single largest mis-specification the
phase-1 calibration found:

    *"the model's price is too smooth. It has one market, one grade, no forward curve, no
    positioning and no market makers - so the only thing that can produce a sharp move is a
    sharp change in physical cover, and the search is straining that one lever to its limit
    trying to imitate everything else."*

This entity is the first half of the answer. It listens to one channel and speaks on four, so
the inflation chain stops jumping from crude straight to the pump and runs through the thing
that is actually at the pump.

WHY A CRACK IS NOT A CONSTANT MARGIN
In 2022 Brent roughly doubled and European diesel went up by rather more than double, because
diesel was short of Russian barrels while crude was not. In a mild autumn the reverse happens
and refiners lose money on every tonne. A crack that was a fixed dollar figure would be the
fifth constant pretending to be a model, so it is a state variable with its own dynamics:
it widens when crude is scarce (refiners bid for a shrinking pool), it widens further when the
world is frightened (product buyers hedge first, crude buyers second), and it decays back to a
seasonal norm because refining capacity responds to margin within months.

Every coefficient here is an asserted starting value with its anchor in the comment, and every
one is a candidate for the calibrator. `targets` names the published series that will judge
them: ICE gasoil versus Brent, RBOB versus WTI, Singapore 10ppm and VLSFO. NONE OF THOSE ARE
INGESTED YET. Until they are, this entity is a mechanism to argue with, and that is said here
rather than discovered later.
"""

from __future__ import annotations

from ..bus import Event
from ..entity import Entity
from ..state import WorldState

#: Normal crack spreads, USD per barrel over crude, at a normal refining balance. Ten-year
#: rough medians: diesel/gasoil around 15, petrol around 12, jet a little over diesel, and
#: high-sulphur bunker BELOW crude - residual fuel is what is left when everything valuable
#: has been taken out, which is why the number is negative and why that is not a typo.
BASE_CRACK = {"diesel": 16.0, "gasoline": 12.0, "jet": 18.0, "bunker": -6.0}

#: How much each product's crack widens per unit of crude tightness (the same `tight.crude`
#: the clearing uses). Diesel is the most exposed because it is the industrial fuel and the
#: hardest to substitute; bunker the least, because a ship that cannot afford fuel sails anyway.
TIGHT_GAIN = {"diesel": 22.0, "gasoline": 12.0, "jet": 20.0, "bunker": 6.0}

#: And per unit of risk premium. Product buyers hedge before crude buyers do, which is why a
#: scare shows up in the crack before it shows up in the flat price.
RISK_GAIN = {"diesel": 40.0, "gasoline": 20.0, "jet": 35.0, "bunker": 10.0}

#: Daily pull back to the base crack. Half-life about six weeks: refining margin is competed
#: away by runs being raised, and raising runs takes a turnaround cycle, not a day.
CRACK_DECAY = 0.016

#: Barrels of product per barrel of crude, for converting a per-barrel crack into a per-tonne
#: bunker price the shipping entity can use. 6.35 barrels to the tonne for residual fuel.
BBL_PER_TONNE = 6.35


class Refiner(Entity):
    """One global refining sector. Segments, not plants - the operator's rule."""

    kind = "refiner"
    listens = ("price.crude", "valve.*")
    emits = ("price.fuel.diesel", "price.fuel.gasoline", "price.fuel.jet",
             "price.fuel.bunker", "price.bunker.tonne")
    own_topic = "price.fuel.diesel"
    #: Published series this entity must reproduce. NOT YET INGESTED - see the module note.
    targets = ("crack.diesel.nwe", "crack.gasoline.usgc", "price.bunker.vlsfo.sing")

    def __init__(self, ident: str = "refiner.global", name: str = "world refining", **params):
        super().__init__(ident, name, **params)

    def on_event(self, ev: Event, w: WorldState) -> list[Event]:
        if not ev.topic.startswith("price.crude"):
            return []
        return self.reprice(w, why=f"crude {ev.value:,.2f}")

    def reprice(self, w: WorldState, why: str = "") -> list[Event]:
        """Move every crack one step and publish the four product prices."""
        crude = w.price("crude")
        if crude <= 0:
            return []
        tight = w.var("__world", "tight.crude", 0.0)
        risk = w.var("__world", "risk_premium", 0.0)
        out: list[Event] = []
        for product, base in BASE_CRACK.items():
            want = (base
                    + TIGHT_GAIN.get(product, 0.0) * max(0.0, tight)
                    + RISK_GAIN.get(product, 0.0) * max(0.0, risk))
            prev = w.var(self.id, f"crack.{product}", base)
            crack = prev + CRACK_DECAY * (want - prev)
            w.set_var(self.id, f"crack.{product}", crack)
            price = max(1.0, crude + crack)
            w.set_var(self.id, f"price.{product}", price)
            out.append(self.say(f"price.fuel.{product}", price, unit="USD/bbl",
                                why=why or f"crack {crack:+.1f} over crude",
                                crack=round(crack, 2)))
        # The shipping sector buys fuel by the tonne, so publish it in the unit it trades in
        # rather than making every listener remember a conversion factor.
        bunker_t = max(1.0, (crude + w.var(self.id, "crack.bunker", BASE_CRACK["bunker"]))
                       * BBL_PER_TONNE)
        w.set_var(self.id, "price.bunker_tonne", bunker_t)
        out.append(self.say("price.bunker.tonne", bunker_t, unit="USD/t",
                            why="residual fuel, 6.35 bbl to the tonne"))
        return out

    def fuel_index(self, w: WorldState) -> float:
        """What a consumer pays at the pump, relative to the reference. Read by countries.

        Weighted two to one towards petrol because household baskets are: a car burns petrol
        and only the freight it consumes indirectly burns diesel, and the freight side reaches
        inflation through its own channel rather than through this one.
        """
        ref = w.var(self.id, "ref_fuel", 0.0)
        now = (2.0 * w.var(self.id, "price.gasoline", 0.0)
               + 1.0 * w.var(self.id, "price.diesel", 0.0)) / 3.0
        if now <= 0:
            return 1.0
        if ref <= 0:
            w.set_var(self.id, "ref_fuel", now)
            return 1.0
        return now / ref
