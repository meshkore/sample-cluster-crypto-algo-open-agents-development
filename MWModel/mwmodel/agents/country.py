"""COUNTRIES - the first players, because almost every chain starts or ends at one.

A country here is not a dot on a map. It is a player with a fiscal position, an energy
balance, a consumption basket and an interest, and it makes decisions that change the world:
how much to pump, whose gas to buy, whether to subsidise fuel, whether to escalate.

THREE POLICIES LIVE HERE, and each one is a hypothesis that will be scored:

  PRODUCTION   A producing state pumps against its capacity, but not blindly. It has a fiscal
               breakeven - the oil price at which its budget balances - and a quota it may or
               may not respect. When the price is far above breakeven the temptation is to
               pump; when it is below, the temptation is to cut and hope others do too. That
               tension is the whole of OPEC's history and it is modelled as an incentive
               rather than a schedule.

  CONSUMPTION  Demand responds to income and to price, and the two elasticities are different
               by an order of magnitude. Short-run price elasticity of oil demand is around
               -0.05: a fifty percent price rise removes two or three percent of barrels,
               which is exactly why energy shocks hurt rather than clear. Income elasticity is
               near one. A country that subsidises fuel shields its consumers from the price
               and therefore removes even less demand - which pushes the adjustment onto
               everyone else.

  INFLATION    Crude reaches a consumer price index through the pump, and the pass-through is
               NOT one to one. Taxes are largely fixed per litre, so a high-tax country moves
               less; the energy weight in the basket differs; and the whole thing arrives with
               a lag of weeks. This is the link the operator asked about, and it is the reason
               the same barrel produces a different CPI in Madrid and in Mumbai.

Every coefficient below carries its source in the comment, and every one is a candidate for
calibration in phase 2. They are starting values, not findings.
"""

from __future__ import annotations

import math

from .base import Agent, Intent, Observation
from ..bus import Event
from ..entity import Entity
from ..entities.shipping import CONTRACT_ROLL, EXPOSURE, SPOT_SHARE
from ..state import WorldState


#: Daily pull of the reference price towards the market price. 0.0038 is a half-life of about
#: 180 days - slow enough that a shock is felt, fast enough that a new level becomes normal.
REF_ADAPT = 0.0038

#: How strongly OPEC+ moves its utilisation per day for each unit of margin over its fiscal
#: breakeven, and how hard quota discipline bites when the price is below it. Exposed as
#: module constants so `calibrate` can fit them rather than inherit an assertion.
CARTEL_GAIN = 0.010
CARTEL_DISCIPLINE = 0.016

#: Percentage points added to inflation by a DOUBLING of freight rates, reached after about a
#: year. 0.7 is the IMF's estimate (Carriere-Swallow et al., WEO Jan 2022), measured across 143
#: countries and the only published number of its kind - which is why it is used as written and
#: marked as borrowed rather than fitted here.
FREIGHT_TO_CPI = 0.007
#: Daily approach to that full effect: half of it inside three months, most inside a year.
FREIGHT_LAG = 0.008
#: The average region's summed lane exposure, so a country more open to trade than average gets
#: more than the average effect and one less open gets less.
EXPOSURE_NORM = 0.75

#: Days between monetary policy meetings. Eight a year, which is the published calendar of the
#: Fed, the ECB, the Bank of England and the Bank of Japan alike.
MEETING_EVERY = 45


class Country(Entity):
    """A state: it pumps, it burns, it prices, and it has a budget to defend.

    On the bus it is a listener rather than a speaker about prices: it hears what fuel costs
    and what it costs to bring goods in, and it speaks one channel of its own - its inflation
    print, which is what everybody else in the model is trying to anticipate.
    """

    kind = "country"
    targets = ("oil_prod", "cpi_yoy")

    def __init__(self, ident: str, name: str = "", **params) -> None:
        super().__init__(ident, name, **params)
        code = ident.rsplit(".", 1)[-1]
        #: A country listens to the lanes its goods actually travel on, and to nothing else.
        #: That is the whole point of the event architecture: when a lane stops mattering to
        #: this country, the subscription goes and the shock genuinely stops reaching it.
        self.exposure: dict[str, float] = dict(
            EXPOSURE.get(params.get("region", ""), EXPOSURE["ROW"]))
        self.listens = (("price.fuel.gasoline", "price.fuel.diesel")
                        + tuple(f"price.freight.{lane}" for lane in self.exposure))
        self.subscribed = list(self.listens)
        self.emits = (f"macro.cpi.{code}",)
        self.own_topic = f"macro.cpi.{code}"

    # ------------------------------------------------------------------ listening
    def on_event(self, ev: Event, w: WorldState) -> list[Event]:
        """Store what was heard. Nothing is published in reply: a country's answer to a
        freight rate is its next inflation print, and that is emitted once per tick by
        `update_prices` rather than once per event - otherwise the same month's CPI would go
        out four times because four lanes moved."""
        if ev.topic.startswith("price.freight."):
            lane = ev.topic.rsplit(".", 1)[-1]
            w.set_var(self.id, f"freight.{lane}", ev.value)
        elif ev.topic == "price.fuel.gasoline":
            w.set_var(self.id, "heard_gasoline", ev.value)
        elif ev.topic == "price.fuel.diesel":
            w.set_var(self.id, "heard_diesel", ev.value)
        return []

    def freight_index(self, w: WorldState) -> tuple[float, float]:
        """What this country's importers are actually PAYING, and the exposure behind it.

        Two steps, and the second one is the one that matters. First the spot rate across the
        lanes this country uses, weighted by how much of its trade travels on each. Then the
        blend of spot and contract: most volume moves on an annual contract, so a spot rate
        that triples in a fortnight reaches the freight bill slowly and partially. Pricing the
        spot rate directly is the same class of error as pricing the flow gap daily - the
        number is real and it is not the number that gets paid.
        """
        total = weighted = 0.0
        for lane, share in self.exposure.items():
            rate = w.var(self.id, f"freight.{lane}", 0.0)
            if rate > 0:
                weighted += share * rate
                total += share
        spot = (weighted / total) if total > 0 else 1.0
        contract = w.var(self.id, "freight_contract", 0.0) or spot
        contract += (spot - contract) * CONTRACT_ROLL
        w.set_var(self.id, "freight_contract", contract)
        w.set_var(self.id, "freight_spot", spot)
        return SPOT_SHARE * spot + (1.0 - SPOT_SHARE) * contract, total

    def observe(self, w: WorldState, news: list[dict]) -> Observation:
        """A state sees prices immediately and its own statistics late.

        Its CPI print is six weeks behind reality and its GDP a quarter behind, which is not a
        modelling nicety: it is why policy is always late, and a simulation in which ministers
        read today's true inflation would produce a stability no government has ever achieved.
        """
        obs = super().observe(w, news)
        obs.own["cpi_observed"] = w.var(self.id, "cpi_lagged", w.var(self.id, "cpi", 100.0))
        return obs

    # ------------------------------------------------------------------ the policies
    def decide(self, obs: Observation, w: WorldState) -> list[Intent]:
        out: list[Intent] = []
        crude = obs.prices.get("crude", 0.0)

        # --- PRODUCTION ------------------------------------------------------------
        cap = self.params.get("oil_capacity", 0.0)          # mb/d
        if cap > 0:
            # TWO KINDS OF PRODUCER, and collapsing them into one was the second defect the
            # scoreboard found. Giving every producer a fiscal breakeven and letting output
            # chase the margin over it turns the AVERAGE BREAKEVEN into an attractor: every
            # replay converged on about sixty dollars regardless of where it started, because
            # that is where the average producer stops wanting to add barrels. Real markets
            # are not anchored at OPEC's budget arithmetic.
            #
            # Outside OPEC+ a producer is a price taker with sunk capital. Its shareholders
            # want the barrel sold today, its wells do not care what the budget needs, and it
            # runs at capacity in almost every state of the world. Only a collapse far below
            # cash costs shuts anything in, and even then slowly.
            if not self.params.get("spare_holder", False):
                cash_cost = self.params.get("cash_cost", 35.0)
                shut_in = 1.0 if crude > cash_cost else max(0.80, crude / max(cash_cost, 1.0))
                util = 0.975 * shut_in
            else:
                # OPEC+ manages output, and what it defends is revenue rather than a price.
                # The response is bounded and slow: a cartel that could move instantly would
                # pin the price exactly where it wanted it, which is the one thing the record
                # shows it cannot do.
                # A CARTEL DECIDES CHANGES, NOT LEVELS - the third constant-anchor defect,
                # and the same mistake as the fixed reference price. A target utilisation of
                # 0.88 meant that a group deliberately holding output at 0.80, as OPEC+ was
                # through 2021, would surge six million barrels a day back to 0.88 within
                # three weeks for no reason other than that the number was written here. Real
                # decisions persist: the group meets, agrees a change, and lives with the
                # level until it meets again.
                breakeven = self.params.get("fiscal_breakeven", 60.0)
                quota = self.params.get("quota_discipline", 0.5)
                margin = (crude - breakeven) / max(breakeven, 1.0)
                prev_level = w.var(self.id, "utilisation", 0.85)
                drift = CARTEL_GAIN * margin - CARTEL_DISCIPLINE * quota * max(0.0, -margin)
                util = max(0.62, min(1.0, prev_level + drift))

            prev = w.var(self.id, "utilisation", util)
            util = 0.93 * prev + 0.07 * util        # wells are physical; fleets move slowly
            w.set_var(self.id, "utilisation", util)
            qty = cap * util
            w.set_var(self.id, "oil_prod", qty)
            out.append(Intent(self.id, "produce", "crude", qty,
                              why=(f"utilisation {util:.2f}; "
                                   + ("manages output, breakeven "
                                      f"{self.params.get('fiscal_breakeven', 0):.0f}"
                                      if self.params.get("spare_holder") else
                                      "price taker, runs at capacity"))))
            out.append(Intent(self.id, "sell", "crude", qty, limit=None,
                              why="export what was lifted"))

        # --- CONSUMPTION -----------------------------------------------------------
        base = self.params.get("oil_demand", 0.0)           # mb/d at reference price
        if base > 0:
            # THE REFERENCE PRICE ADAPTS, and making it a constant was a real defect found by
            # the scoreboard on 2026-09-15. With a fixed reference every country's demand pulls
            # the market back towards that one number, so the whole world became an attractor
            # at $68: a replay starting at $47 rose to $71 and one starting at $110 fell to
            # $68, and the model lost to a flat line in nine windows out of ten. Consumers do
            # not compare today's price to a number in a file; they compare it to what they
            # have got used to, and what they have got used to drifts.
            ref = w.var(self.id, "ref_price", self.params.get("ref_price", 75.0))
            # Short-run price elasticity of oil demand: about -0.05 in the literature, and
            # smaller still where fuel is subsidised, because the consumer never sees the
            # price at all.
            elas = -0.05 * (1.0 - 0.6 * self.params.get("fuel_subsidy", 0.0))
            gdp = w.var(self.id, "gdp_index", 1.0)
            income = self.params.get("income_elasticity", 0.85)
            qty = base * (gdp ** income) * ((max(crude, 1.0) / ref) ** elas)
            w.set_var(self.id, "oil_demand", qty)
            out.append(Intent(self.id, "buy", "crude", qty, limit=None,
                              why=f"gdp {gdp:.3f}, price {crude:.1f} vs ref {ref:.0f}, "
                                  f"elasticity {elas:.3f}"))

        return out

    # ------------------------------------------------------------------ the CPI chain
    def update_prices(self, w: WorldState) -> None:
        """Crude -> the pump -> the basket -> the print. Called by the engine after clearing.

        Three separate effects, kept separate because they are separately wrong:
          1. pass-through: how much of a crude move reaches the pump, after fixed taxes
          2. basket weight: how much the pump matters in this country's index
          3. the lag: how long before a statistical office publishes it
        """
        crude = w.price("crude")
        ref = w.var(self.id, "ref_price", self.params.get("ref_price", 75.0))
        weight = self.params.get("energy_weight", 0.08)
        subsidy = self.params.get("fuel_subsidy", 0.0)

        # THE PUMP SELLS PRODUCTS, NOT CRUDE. Until the refining sector existed this line read
        # `crude / ref`, which assumed the crack spread never moves - and the crack is exactly
        # what moved in 2022, when European diesel rose by half again as much as Brent did
        # because the barrels that were short were diesel barrels. Where the refiner has
        # spoken, the household basket is priced off petrol and diesel; where it has not, the
        # old crude ratio stands in and says so by its absence.
        gasoline = w.var(self.id, "heard_gasoline", 0.0)
        diesel = w.var(self.id, "heard_diesel", 0.0)
        if gasoline > 0 and diesel > 0:
            fuel = (2.0 * gasoline + diesel) / 3.0
            fref = w.var(self.id, "ref_fuel", 0.0) or fuel
            pump_move = (fuel / max(fref, 1.0) - 1.0) * self.params.get("passthrough", 0.55)
            w.set_var(self.id, "ref_fuel", fref + (fuel - fref) * REF_ADAPT)
        else:
            pump_move = (crude / max(ref, 1.0) - 1.0) * self.params.get("passthrough", 0.55)

        # The contribution to inflation, annualised, from energy alone.
        energy_infl = pump_move * weight * (1.0 - 0.8 * subsidy)

        # AND THE SECOND CHANNEL: what it costs to bring the goods in. This is the one the
        # operator asked for by name - a ship raises its rate, and the countries on that lane
        # find it in their next print. It is slow (a container booked today is on a shelf in
        # three months) and it is small next to energy, which is why it needed its own channel
        # instead of being folded into the energy weight where it would have been invisible.
        index, exposure = self.freight_index(w)
        want_freight = (FREIGHT_TO_CPI * math.log2(max(index, 0.05))
                        * (exposure / EXPOSURE_NORM))
        freight_infl = w.var(self.id, "freight_contrib", 0.0)
        freight_infl += (want_freight - freight_infl) * FREIGHT_LAG
        w.set_var(self.id, "freight_contrib", freight_infl)
        w.set_var(self.id, "freight_index", index)

        core = self.params.get("core_inflation", 0.02)
        target = core + energy_infl + freight_infl

        # Inflation is sticky: today's print carries most of yesterday's. The 0.94 is a
        # monthly persistence of roughly 0.85 expressed daily, and it is the first thing
        # phase 2 will calibrate per country.
        prev = w.var(self.id, "cpi_yoy", core)
        now = 0.94 * prev + 0.06 * target
        w.set_var(self.id, "cpi_yoy", now)
        w.set_var(self.id, "energy_contrib", energy_infl)

        # The reference drifts towards the price actually being paid, with a half-life of
        # about six months. This is what gives the model base effects: a price that has stayed
        # at $110 for a year stops ADDING to inflation, which is exactly what happened in 2023
        # and what a fixed reference could never express.
        w.set_var(self.id, "ref_price", ref + (crude - ref) * REF_ADAPT)

        # What the statistical office has actually published: six weeks behind.
        hist = w.vars.setdefault(f"{self.id}__cpi_hist", {})
        hist[str(w.tick)] = now
        published = hist.get(str(max(0, w.tick - 42)), now)
        w.set_var(self.id, "cpi_lagged", published)

        # Speak on the one channel this entity is the publisher of record for - and publish
        # the LAGGED number, because that is the only inflation figure that exists outside
        # this simulation. A central bank that could hear today's true CPI would stabilise an
        # economy no central bank has ever managed to stabilise.
        w.bus.publish(self.say(f"macro.cpi.{self.id.rsplit('.', 1)[-1]}", published,
                               why=f"energy {energy_infl:+.3%}, freight {freight_infl:+.3%}"),
                      tick=w.tick)


class CentralBank(Entity):
    """A mandate, a reaction function, and a number it can only see six weeks late.

    The rule is a Taylor rule, which is crude and also the most robust description of what
    central banks actually do that anyone has found. What matters here is not its elegance but
    that it reacts to the OBSERVED inflation rather than the true one - so the model produces
    the overshoot and the late tightening that real economies suffer, rather than the smooth
    stabilisation that a perfectly informed bank would achieve.
    """

    kind = "central_bank"
    targets = ("policy_rate",)

    def __init__(self, ident: str, name: str = "", **params) -> None:
        super().__init__(ident, name, **params)
        code = params.get("country", "").rsplit(".", 1)[-1]
        #: It hears exactly one thing: the inflation figure that has been PUBLISHED. That is
        #: the whole of law 2 in one subscription - the bank has no window into the true state
        #: of the economy, only into the statistical office's six-week-old account of it.
        self.listens = (f"macro.cpi.{code}",) + tuple(
            f"macro.cpi.{m}" for m in params.get("members", ()) if m != code)
        self.subscribed = list(self.listens)
        self.emits = (f"policy.rate.{ident.rsplit('.', 1)[-1]}",)
        self.own_topic = self.emits[0]

    def on_event(self, ev: Event, w: WorldState) -> list[Event]:
        """Remember the print. A committee does not move between meetings on one number."""
        w.set_var(self.id, f"heard.{ev.topic.rsplit('.', 1)[-1]}", ev.value)
        return []

    def heard(self, w: WorldState, fallback: float) -> float:
        """The average of the prints this bank is mandated over - one for most, four for the
        euro area, which is why a single monetary policy fits nobody in particular."""
        vals = [v for k, v in w.vars.get(self.id, {}).items() if k.startswith("heard.")]
        return sum(vals) / len(vals) if vals else fallback

    def decide(self, obs: Observation, w: WorldState) -> list[Intent]:
        # A COMMITTEE MEETS; IT DOES NOT DRIFT. Until this line existed the policy rate moved a
        # fraction of a basis point every single day, which is not what any central bank does
        # and which flooded the bus with an event a day per bank. Eight meetings a year is the
        # cadence of the Fed, the ECB and most of the rest, and between them the rate is held
        # even when the data says it should not be - which is itself a source of macro
        # dynamics, not an approximation of one.
        if w.tick % MEETING_EVERY != 0:
            return []
        country = self.params.get("country", "")
        seen = self.heard(w, w.var(country, "cpi_lagged", 0.02))
        target = self.params.get("inflation_target", 0.02)
        neutral = self.params.get("neutral_rate", 0.02)
        gap = seen - target
        # 1.5 on the inflation gap is the Taylor principle: to raise the REAL rate, the
        # nominal rate has to move more than one for one with inflation. Below that, a bank
        # accommodates a shock instead of leaning against it.
        wanted = neutral + target + 1.5 * gap
        wanted = max(0.0, min(0.25, wanted))
        prev = w.var(self.id, "policy_rate", neutral + target)
        # Banks move in steps and rarely reverse; the smoothing is the committee, not physics.
        # A meeting can move 25 or 50 basis points, and rarely more. The cap is per MEETING
        # now, not per day, which is why it is twenty-five times larger than it was.
        rate = prev + max(-0.005, min(0.005, wanted - prev))
        why = f"observed inflation {seen:.3%} vs target {target:.1%}"
        # Speak the rate on its own channel. NOBODY LISTENS YET - the investor cohorts and
        # market makers that would react to it arrive in phase 3. The channel exists now
        # because publishing is the entity's job and subscribing is everyone else's, and a
        # model where the publisher waits for an audience never gets built in the right order.
        w.bus.publish(self.say(f"policy.rate.{self.id.rsplit('.', 1)[-1]}", rate, why=why),
                      tick=w.tick)
        return [Intent(self.id, "set", f"{self.id}.policy_rate", rate, why=why)]
