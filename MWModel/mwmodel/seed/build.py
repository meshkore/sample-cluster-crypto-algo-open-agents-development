"""Assemble a starting world: the players, their balances, the markets and the valves.

Nothing clever happens here. It is the constructor, kept separate from the engine so that the
question "what world are we simulating" has one answer in one file, and so that a different
starting world - a historical replay, a counterfactual, a stress test - is a different builder
rather than a flag buried in a loop.
"""

from __future__ import annotations

from ..agents.country import CentralBank, Country
from ..network import chokepoints as CP
from ..state import Market, WorldState
from . import energy, facts


def build(day: str = "2026-09-15", measured: bool = True) -> tuple[WorldState, list]:
    """`measured=True` uses the EIA's published balances; False keeps the placeholders.

    The switch exists so the difference between an invented world and a measured one can be
    run side by side rather than argued about. If the harvest has not been run the builder
    falls back to the placeholders and SAYS SO, rather than failing or - worse - quietly
    producing a world made of round numbers that looks exactly like a real one.
    """
    countries, residual, prov = facts.COUNTRIES, None, {}
    if measured:
        try:
            m = energy.apply(facts.COUNTRIES, asof=day)
            countries, residual, prov = m["countries"], m["residual"], m["provenance"]
        except FileNotFoundError:
            print("  [!] EIA balances not harvested - falling back to placeholders. "
                  "Run `python -m mwmodel.archive.ingest.eia`.")

    w = WorldState(day=day)
    w.set_var("__world", "measured", 1.0 if residual else 0.0)
    if residual:
        for k in ("world_production", "world_consumption", "capacity", "demand"):
            if residual.get(k) is not None:
                w.set_var("__world", k, residual[k])
    agents: list = []

    for code, f in countries.items():
        ident = f"country.{code}"
        a = Country(ident, f["name"],
                    oil_capacity=f.get("oil_capacity", 0.0),
                    oil_demand=f.get("oil_demand", 0.0),
                    energy_weight=f.get("energy_weight", 0.08),
                    passthrough=f.get("passthrough", 0.5),
                    fuel_subsidy=f.get("fuel_subsidy", 0.0),
                    core_inflation=f.get("core_inflation", 0.02),
                    fiscal_breakeven=f.get("breakeven", 60.0) or 60.0,
                    quota_discipline=f.get("discipline", 0.0),
                    spare_holder=code in energy.SPARE_HOLDERS,
                    cash_cost=f.get("cash_cost", 35.0),
                    ref_price=facts.MARKETS["crude"]["price"],
                    region=f.get("region", ""), gdp=f.get("gdp", 0.0), pop=f.get("pop", 0.0))
        agents.append(a)
        w.set_var(ident, "gdp_index", 1.0)
        w.set_var(ident, "cpi_yoy", f.get("core_inflation", 0.02))
        w.set_var(ident, "cpi_lagged", f.get("core_inflation", 0.02))
        # START THE WORLD WHERE IT ACTUALLY IS. Seeding every producer at the same nominal
        # utilisation invented a supply surplus or deficit on the very first tick that had
        # nothing to do with the world being simulated. The measured ratio of what a country
        # produces to what it could produce is a fact we have; using anything else throws it
        # away.
        cap0 = f.get("oil_capacity", 0.0) or 0.0
        prod0 = f.get("production_now", 0.0) or 0.0
        w.set_var(ident, "utilisation",
                  max(0.55, min(1.0, prod0 / cap0)) if cap0 > 0 else 0.86)
        # Seeded at the market's opening price: what this country is used to paying is,
        # initially, what it is paying.
        w.set_var(ident, "ref_price", facts.MARKETS["crude"]["price"])
        # A year of import spending in cash, so that nobody is liquidity constrained before
        # phase 2 gives them a real external balance.
        spend = f.get("oil_demand", 0.0) * 365.0 * facts.MARKETS["crude"]["price"] * 1e6
        w.balance(ident).cash = spend * facts.CASH_YEARS

        if f.get("cb"):
            cb = CentralBank(f"cb.{code}", f"{f['name']} central bank",
                             country=ident,
                             inflation_target=f.get("inflation_target", 0.02),
                             neutral_rate=f.get("neutral_rate", 0.015))
            agents.append(cb)
            w.set_var(cb.id, "policy_rate",
                      f.get("neutral_rate", 0.015) + f.get("inflation_target", 0.02))

    # The euro area's single policy, reacting to a weighted average of four prints.
    ecb = CentralBank("cb.ECB", "European Central Bank", country="country.DEU",
                      inflation_target=0.02, neutral_rate=0.005,
                      members=facts.EURO_AREA)
    agents.append(ecb)
    w.set_var(ecb.id, "policy_rate", 0.025)

    # The aggregate remainder. With measured balances this is the ACTUAL residual between the
    # world total and the named roster, not a guess: the market then clears against the real
    # hundred million barrels a day.
    row_d = dict(facts.REST_OF_WORLD["demand"])
    row_s = dict(facts.REST_OF_WORLD["supply"])
    if residual:
        row_d["oil_demand"] = max(0.0, residual["demand"])
        row_s["oil_capacity"] = max(0.0, residual["capacity"])
    rest = Country("region.ROW", row_d["name"],
                   oil_demand=row_d["oil_demand"], oil_capacity=0.0,
                   energy_weight=row_d["energy_weight"], passthrough=row_d["passthrough"],
                   fuel_subsidy=row_d["fuel_subsidy"],
                   core_inflation=row_d["core_inflation"],
                   ref_price=facts.MARKETS["crude"]["price"], region="ROW")
    agents.append(rest)
    w.set_var(rest.id, "gdp_index", 1.0)
    w.balance(rest.id).cash = row_d["oil_demand"] * 365.0 * 68.0 * 1e6

    other = Country("sector.other_supply", row_s["name"],
                    oil_capacity=row_s["oil_capacity"], oil_demand=0.0, spare_holder=False,
                    fiscal_breakeven=row_s["breakeven"], quota_discipline=row_s["discipline"],
                    ref_price=facts.MARKETS["crude"]["price"], region="ROW")
    agents.append(other)
    w.set_var(other.id, "utilisation", 0.98)

    # Markets. Inventory is a real balance owned by the market, not a floating number.
    for key, spec in facts.MARKETS.items():
        total_demand = sum(a.params.get("oil_demand", 0.0) for a in agents
                           if isinstance(a, Country))
        stock = total_demand * spec["cover_days"]
        w.markets[key] = Market(key=key, unit=spec["unit"], price=spec["price"],
                                inventory=stock)
        w.balance(f"market.{key}").units[spec["unit"]] = stock
        w.balance(f"market.{key}").cash = 0.0

    CP.seed_edges(w)
    if residual:
        counts = energy.provenance_summary(prov)
        w.log("__world", "seeded", provenance=str(counts),
              world_production=residual["world_production"],
              world_consumption=residual["world_consumption"], asof=residual["asof"])
    return w, agents
