"""THE STARTING WORLD - order-of-magnitude public figures, every one of them a placeholder.

READ THIS BEFORE TRUSTING A NUMBER BELOW. These are approximate 2025 figures written to get
the simulation running end to end. They are not a dataset. Phase 1 replaces the energy block
with real series (EIA, JODI, OPEC monthly), phase 2 replaces the CPI block with real basket
weights, and until then every result carries the caveat that its inputs are round numbers.

Saying that once, loudly, here, is cheaper than discovering it inside a conclusion later. This
laboratory has already published a figure built on a supply series that disagreed with the
published one by 65% and called it calibrated.

WHAT EACH COLUMN MEANS
    oil_capacity        sustainable crude capacity, mb/d - what could be pumped, not what is
    oil_demand          liquids consumption at the reference price, mb/d
    gdp                 nominal GDP, USD trillion
    pop                 population, millions
    energy_weight       energy's share of the consumer price basket
    passthrough         how much of a crude move reaches the pump. Low where fuel taxes are
                        high and fixed per litre - a European pays mostly tax, so the crude
                        component of the pump price is a minority of it
    fuel_subsidy        0 = the consumer pays the market price, 1 = fully shielded
    core_inflation      the non-energy trend the country would print with flat oil
    breakeven           the crude price at which the budget balances - the producer's pain line
    discipline          0 = pumps freely, 1 = respects a quota even when it hurts
"""

from __future__ import annotations

#: The producing and consuming states. `cb` marks the ones that run their own monetary policy
#: in this model; the euro-area members share one.
COUNTRIES: dict[str, dict] = {
    # --- the Gulf, which is the entire reason the chokepoints matter -----------------
    "SAU": dict(name="Saudi Arabia", region="ME", oil_capacity=12.0, oil_demand=3.8,
                gdp=1.1, pop=37, energy_weight=0.06, passthrough=0.30, fuel_subsidy=0.6,
                core_inflation=0.019, breakeven=85.0, discipline=0.85),
    "IRN": dict(name="Iran", region="ME", oil_capacity=3.8, oil_demand=1.9,
                gdp=0.4, pop=90, energy_weight=0.10, passthrough=0.25, fuel_subsidy=0.85,
                core_inflation=0.33, breakeven=120.0, discipline=0.10),
    "IRQ": dict(name="Iraq", region="ME", oil_capacity=4.8, oil_demand=0.9,
                gdp=0.26, pop=45, energy_weight=0.08, passthrough=0.30, fuel_subsidy=0.5,
                core_inflation=0.04, breakeven=95.0, discipline=0.35),
    "ARE": dict(name="United Arab Emirates", region="ME", oil_capacity=4.2, oil_demand=1.0,
                gdp=0.55, pop=10, energy_weight=0.05, passthrough=0.35, fuel_subsidy=0.2,
                core_inflation=0.02, breakeven=70.0, discipline=0.55),
    "KWT": dict(name="Kuwait", region="ME", oil_capacity=2.8, oil_demand=0.5,
                gdp=0.16, pop=4.9, energy_weight=0.05, passthrough=0.25, fuel_subsidy=0.7,
                core_inflation=0.025, breakeven=80.0, discipline=0.8),
    "QAT": dict(name="Qatar", region="ME", oil_capacity=1.8, oil_demand=0.4,
                gdp=0.24, pop=3.0, energy_weight=0.04, passthrough=0.30, fuel_subsidy=0.6,
                core_inflation=0.02, breakeven=55.0, discipline=0.7),
    # --- the other large producers ---------------------------------------------------
    "USA": dict(name="United States", region="NA", oil_capacity=13.7, oil_demand=20.3,
                gdp=29.0, pop=342, energy_weight=0.065, passthrough=0.65, fuel_subsidy=0.0,
                core_inflation=0.028, breakeven=48.0, discipline=0.0, cb=True,
                inflation_target=0.02, neutral_rate=0.012),
    "RUS": dict(name="Russia", region="EA", oil_capacity=11.0, oil_demand=3.7,
                gdp=2.2, pop=144, energy_weight=0.09, passthrough=0.35, fuel_subsidy=0.5,
                core_inflation=0.075, breakeven=70.0, discipline=0.4, cb=True,
                inflation_target=0.04, neutral_rate=0.03),
    "CAN": dict(name="Canada", region="NA", oil_capacity=5.7, oil_demand=2.4,
                gdp=2.2, pop=41, energy_weight=0.075, passthrough=0.55, fuel_subsidy=0.0,
                core_inflation=0.024, breakeven=45.0, discipline=0.0, cb=True,
                inflation_target=0.02, neutral_rate=0.012),
    "BRA": dict(name="Brazil", region="SA", oil_capacity=3.7, oil_demand=2.4,
                gdp=2.3, pop=213, energy_weight=0.105, passthrough=0.50, fuel_subsidy=0.15,
                core_inflation=0.042, breakeven=45.0, discipline=0.0, cb=True,
                inflation_target=0.03, neutral_rate=0.05),
    "NOR": dict(name="Norway", region="EU", oil_capacity=2.0, oil_demand=0.2,
                gdp=0.5, pop=5.5, energy_weight=0.08, passthrough=0.40, fuel_subsidy=0.0,
                core_inflation=0.026, breakeven=40.0, discipline=0.0),
    "KAZ": dict(name="Kazakhstan", region="EA", oil_capacity=1.9, oil_demand=0.35,
                gdp=0.29, pop=20, energy_weight=0.09, passthrough=0.35, fuel_subsidy=0.5,
                core_inflation=0.08, breakeven=60.0, discipline=0.3),
    "NGA": dict(name="Nigeria", region="AF", oil_capacity=1.5, oil_demand=0.5,
                gdp=0.36, pop=228, energy_weight=0.12, passthrough=0.45, fuel_subsidy=0.3,
                core_inflation=0.22, breakeven=110.0, discipline=0.2),
    "LBY": dict(name="Libya", region="AF", oil_capacity=1.2, oil_demand=0.25,
                gdp=0.05, pop=7, energy_weight=0.10, passthrough=0.20, fuel_subsidy=0.8,
                core_inflation=0.05, breakeven=100.0, discipline=0.1),
    "DZA": dict(name="Algeria", region="AF", oil_capacity=1.0, oil_demand=0.45,
                gdp=0.27, pop=46, energy_weight=0.10, passthrough=0.25, fuel_subsidy=0.7,
                core_inflation=0.05, breakeven=95.0, discipline=0.5),
    "VEN": dict(name="Venezuela", region="SA", oil_capacity=0.9, oil_demand=0.5,
                gdp=0.1, pop=28, energy_weight=0.12, passthrough=0.15, fuel_subsidy=0.9,
                core_inflation=0.6, breakeven=130.0, discipline=0.1),
    "MEX": dict(name="Mexico", region="NA", oil_capacity=1.9, oil_demand=1.9,
                gdp=1.8, pop=130, energy_weight=0.10, passthrough=0.50, fuel_subsidy=0.2,
                core_inflation=0.038, breakeven=65.0, discipline=0.0, cb=True,
                inflation_target=0.03, neutral_rate=0.045),
    # --- the large consumers ---------------------------------------------------------
    "CHN": dict(name="China", region="AS", oil_capacity=4.3, oil_demand=16.5,
                gdp=18.5, pop=1411, energy_weight=0.07, passthrough=0.40, fuel_subsidy=0.25,
                core_inflation=0.005, breakeven=55.0, discipline=0.0, cb=True,
                inflation_target=0.03, neutral_rate=0.01),
    "IND": dict(name="India", region="AS", oil_capacity=0.7, oil_demand=5.5,
                gdp=3.9, pop=1440, energy_weight=0.13, passthrough=0.45, fuel_subsidy=0.35,
                core_inflation=0.045, breakeven=0.0, discipline=0.0, cb=True,
                inflation_target=0.04, neutral_rate=0.015),
    "JPN": dict(name="Japan", region="AS", oil_capacity=0.0, oil_demand=3.3,
                gdp=4.1, pop=123, energy_weight=0.075, passthrough=0.45, fuel_subsidy=0.2,
                core_inflation=0.019, breakeven=0.0, discipline=0.0, cb=True,
                inflation_target=0.02, neutral_rate=0.0),
    "KOR": dict(name="South Korea", region="AS", oil_capacity=0.0, oil_demand=2.8,
                gdp=1.8, pop=52, energy_weight=0.085, passthrough=0.45, fuel_subsidy=0.15,
                core_inflation=0.021, breakeven=0.0, discipline=0.0, cb=True,
                inflation_target=0.02, neutral_rate=0.012),
    "DEU": dict(name="Germany", region="EU", oil_capacity=0.0, oil_demand=2.3,
                gdp=4.6, pop=84, energy_weight=0.095, passthrough=0.35, fuel_subsidy=0.05,
                core_inflation=0.024, breakeven=0.0, discipline=0.0),
    "FRA": dict(name="France", region="EU", oil_capacity=0.0, oil_demand=1.6,
                gdp=3.2, pop=68, energy_weight=0.090, passthrough=0.32, fuel_subsidy=0.1,
                core_inflation=0.021, breakeven=0.0, discipline=0.0),
    "ITA": dict(name="Italy", region="EU", oil_capacity=0.0, oil_demand=1.2,
                gdp=2.3, pop=59, energy_weight=0.100, passthrough=0.30, fuel_subsidy=0.05,
                core_inflation=0.020, breakeven=0.0, discipline=0.0),
    "ESP": dict(name="Spain", region="EU", oil_capacity=0.0, oil_demand=1.3,
                gdp=1.7, pop=48, energy_weight=0.105, passthrough=0.38, fuel_subsidy=0.05,
                core_inflation=0.022, breakeven=0.0, discipline=0.0),
    "GBR": dict(name="United Kingdom", region="EU", oil_capacity=0.7, oil_demand=1.6,
                gdp=3.6, pop=69, energy_weight=0.085, passthrough=0.35, fuel_subsidy=0.0,
                core_inflation=0.030, breakeven=50.0, discipline=0.0, cb=True,
                inflation_target=0.02, neutral_rate=0.012),
    "TUR": dict(name="Turkey", region="EA", oil_capacity=0.1, oil_demand=1.1,
                gdp=1.3, pop=86, energy_weight=0.135, passthrough=0.55, fuel_subsidy=0.1,
                core_inflation=0.30, breakeven=0.0, discipline=0.0, cb=True,
                inflation_target=0.05, neutral_rate=0.04),
    "IDN": dict(name="Indonesia", region="AS", oil_capacity=0.6, oil_demand=1.8,
                gdp=1.4, pop=283, energy_weight=0.11, passthrough=0.40, fuel_subsidy=0.45,
                core_inflation=0.028, breakeven=0.0, discipline=0.0, cb=True,
                inflation_target=0.03, neutral_rate=0.02),
    "EGY": dict(name="Egypt", region="AF", oil_capacity=0.6, oil_demand=0.9,
                gdp=0.38, pop=115, energy_weight=0.125, passthrough=0.35, fuel_subsidy=0.5,
                core_inflation=0.16, breakeven=0.0, discipline=0.0),
    "ZAF": dict(name="South Africa", region="AF", oil_capacity=0.0, oil_demand=0.6,
                gdp=0.4, pop=63, energy_weight=0.11, passthrough=0.50, fuel_subsidy=0.0,
                core_inflation=0.043, breakeven=0.0, discipline=0.0, cb=True,
                inflation_target=0.045, neutral_rate=0.025),
}

#: The euro area's single monetary policy, which is why DEU/FRA/ITA/ESP carry no `cb` of their
#: own. It reacts to a weighted average of their prints, which is exactly the tension that
#: makes a single currency hard and is therefore worth modelling rather than assuming away.
EURO_AREA = ("DEU", "FRA", "ITA", "ESP")

#: What the named countries do not account for. The world consumes about 103 mb/d and produces
#: about the same; the roster above covers roughly four fifths of each. The remainder is
#: carried as two aggregate players so the market clears against the real total rather than
#: against a fifth of it - and it is labelled as an aggregate so nobody mistakes it for
#: knowledge.
REST_OF_WORLD = dict(
    demand=dict(name="Rest of the world", oil_demand=19.0, energy_weight=0.10,
                passthrough=0.45, fuel_subsidy=0.25, core_inflation=0.04, region="ROW"),
    supply=dict(name="Other supply: NGLs, biofuels, small producers", oil_capacity=31.0,
                breakeven=50.0, discipline=0.0, region="ROW"),
)

#: Starting market state. Crude cover of sixty days is the customary comfortable level for
#: OECD commercial stocks plus strategic reserves.
MARKETS = {
    "crude": dict(unit="bbl", price=68.0, cover_days=60.0),
}

#: Every country starts with a year of import cover in cash. This is a simplification and a
#: visible one: fiscal and external balances arrive in phase 2, and until then no conclusion
#: that depends on a country running out of money means anything.
CASH_YEARS = 1.0


#: Approximate centroids, for the map. Longitude, latitude. The viewer draws an equirectangular
#: projection, which distorts the poles badly and is exactly right for a picture whose subject
#: is shipping lanes and consumption.
COORDS: dict[str, tuple[float, float]] = {
    "SAU": (45.0, 24.0), "IRN": (53.0, 32.0), "IRQ": (44.0, 33.0), "ARE": (54.0, 24.0),
    "KWT": (47.5, 29.3), "QAT": (51.2, 25.3), "USA": (-98.0, 39.0), "RUS": (90.0, 61.0),
    "CAN": (-106.0, 56.0), "BRA": (-51.0, -10.0), "NOR": (9.0, 61.0), "KAZ": (67.0, 48.0),
    "NGA": (8.0, 9.5), "LBY": (17.0, 27.0), "DZA": (2.0, 28.0), "VEN": (-66.0, 7.0),
    "MEX": (-102.0, 23.0), "CHN": (104.0, 35.0), "IND": (79.0, 22.0), "JPN": (138.0, 36.0),
    "KOR": (127.8, 36.5), "DEU": (10.4, 51.2), "FRA": (2.2, 46.6), "ITA": (12.6, 42.8),
    "ESP": (-3.7, 40.4), "GBR": (-1.5, 53.0), "TUR": (35.0, 39.0), "IDN": (113.0, -1.0),
    "EGY": (30.0, 26.8), "ZAF": (24.0, -29.0),
}

#: Where each valve sits, so the map can draw it where it actually is.
CHOKE_COORDS: dict[str, tuple[float, float]] = {
    "hormuz": (56.4, 26.6), "bab_el_mandeb": (43.3, 12.6), "malacca": (100.4, 2.5),
    "suez_canal": (32.5, 30.5), "turkish_straits": (29.1, 41.1), "panama": (-79.6, 9.1),
}
