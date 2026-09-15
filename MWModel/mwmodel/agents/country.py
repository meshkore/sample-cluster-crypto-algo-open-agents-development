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

from .base import Agent, Intent, Observation
from ..state import WorldState


#: Daily pull of the reference price towards the market price. 0.0038 is a half-life of about
#: 180 days - slow enough that a shock is felt, fast enough that a new level becomes normal.
REF_ADAPT = 0.0038


class Country(Agent):
    """A state: it pumps, it burns, it prices, and it has a budget to defend."""

    kind = "country"
    targets = ("oil_prod", "cpi_yoy")

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
                drift = 0.010 * margin - 0.016 * quota * max(0.0, -margin)
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
        pump_move = (crude / max(ref, 1.0) - 1.0) * self.params.get("passthrough", 0.55)
        weight = self.params.get("energy_weight", 0.08)
        subsidy = self.params.get("fuel_subsidy", 0.0)

        # The contribution to inflation, annualised, from energy alone.
        energy_infl = pump_move * weight * (1.0 - 0.8 * subsidy)
        core = self.params.get("core_inflation", 0.02)
        target = core + energy_infl

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
        w.set_var(self.id, "cpi_lagged", hist.get(str(max(0, w.tick - 42)), now))


class CentralBank(Agent):
    """A mandate, a reaction function, and a number it can only see six weeks late.

    The rule is a Taylor rule, which is crude and also the most robust description of what
    central banks actually do that anyone has found. What matters here is not its elegance but
    that it reacts to the OBSERVED inflation rather than the true one - so the model produces
    the overshoot and the late tightening that real economies suffer, rather than the smooth
    stabilisation that a perfectly informed bank would achieve.
    """

    kind = "central_bank"
    targets = ("policy_rate",)

    def decide(self, obs: Observation, w: WorldState) -> list[Intent]:
        country = self.params.get("country", "")
        seen = w.var(country, "cpi_lagged", 0.02)
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
        rate = prev + max(-0.0015, min(0.0015, wanted - prev))
        return [Intent(self.id, "set", f"{self.id}.policy_rate", rate,
                       why=f"observed inflation {seen:.3%} vs target {target:.1%}")]
