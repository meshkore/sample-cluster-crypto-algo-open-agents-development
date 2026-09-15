"""REAL ENERGY BALANCES, replacing the round numbers - phase 1 begins here.

`facts.py` was written to get the world turning and every figure in it was a placeholder. This
module reads the EIA's published balances instead, and it does three things the placeholders
could not:

  1. PRODUCTION AND CONSUMPTION ARE MEASURED, per country, monthly, in the units the market
     quotes. No conversion, so no conversion error.
  2. THE REMAINDER IS COMPUTED, not guessed. The named roster covers about four fifths of the
     world; the aggregate "rest of the world" player is now the actual residual between the
     global total and the sum of the named, which means the market clears against the real
     hundred million barrels a day rather than against a plausible-looking eighty.
  3. EVERY FIGURE CARRIES ITS PROVENANCE. `measured`, `declared` or `placeholder`, reported by
     `provenance()` and printed by the builder, so a result can never quietly rest on a number
     somebody invented in an afternoon.

CAPACITY REMAINS THE HARD ONE. Nobody publishes productive capacity for free, and the
difference between what a country pumps and what it could pump is the entire behaviour of
OPEC. Where a producer states a figure it is used and marked `declared`; otherwise it is
inferred as the best month of the last five years plus two percent, and marked `inferred`.
That inference is deliberately conservative and it is WRONG IN A KNOWN DIRECTION: it
understates exactly the producers who hold spare on purpose, which is to say the ones who
matter in a crisis. Phase 2 replaces it with a cost-curve model.
"""

from __future__ import annotations

from ..archive.ingest import eia

#: Aggregates the EIA publishes alongside countries. They must never be added to a country
#: total or the world is counted twice.
#: TWO DIFFERENT THINGS ARE BOTH CALLED SPARE CAPACITY, and the roster's total makes no sense
#: until they are separated. "OPEC spare capacity", the 3-4 mb/d usually quoted, means barrels
#: deliverable within ninety days and sustainable for months - effectively Saudi Arabia and the
#: Emirates. What this module computes is larger, around 8 mb/d across OPEC+, because it also
#: contains capacity withheld under quota, capacity constrained by sanctions, and capacity that
#: exists on paper in countries that could not reach it quickly. Both are real; only the first
#: can answer a shock next month. The engine should eventually hold them separately.
#:
#: OPEC+ - the producers who withhold barrels as policy. Everyone else pumps flat out, and
#: the difference is the single most consequential asymmetry in the oil market.
SPARE_HOLDERS = {"SAU", "ARE", "KWT", "IRQ", "IRN", "RUS", "KAZ", "NGA", "LBY", "DZA",
                 "VEN", "AGO", "COG", "GNQ", "GAB", "OMN", "AZE", "BHR", "BRN", "MYS",
                 "MEX", "SDN", "SSD"}

AGGREGATES = {"WLD", "OPEC", "NOPEC", "OECD", "NOECD", "EUR", "ASI", "AFR", "NAM", "SAM",
              "MEA", "EUE", "OAS", "CSA", "CSAM", "NAMR"}


def _upto(rows: list, asof: str | None) -> list:
    """Only what had been PUBLISHED by `asof`, with the EIA's own reporting lag applied.

    Energy statistics arrive about two months after the month they describe, so a replay
    standing on 1 March may use January's figure at the earliest. Without this a historical
    replay quietly reads the future and then congratulates itself on the accuracy.
    """
    if not asof:
        return rows
    from datetime import date, timedelta
    cutoff = (date.fromisoformat(asof[:10]) - timedelta(days=PUBLICATION_LAG_DAYS)).isoformat()
    return [r for r in rows if r[0] <= cutoff]


def _recent(rows: list, months: int) -> list[float]:
    return [v for _, v in rows[-months:]] if rows else []


#: How long after a month closes the EIA has published it. Two months is the observed cadence
#: and it is applied on the conservative side, for the same reason the World Archive applies
#: publication lags at all: a number read before it existed makes a model look brilliant.
PUBLICATION_LAG_DAYS = 70


def measure(iso: str, production: dict, consumption: dict,
            crude: dict | None = None, asof: str | None = None) -> dict:
    """One country's energy balance, in mb/d, with the provenance of each figure.

    ONE UNIT THROUGHOUT, and getting there took a correction. `production` is *petroleum and
    other liquids* - crude plus natural gas liquids plus biofuels plus refinery processing
    gain - while the capacities OPEC members declare are *crude* capacities. Saudi Arabia's
    stated twelve million barrels a day is not comparable to the roughly thirteen it supplies
    in total liquids, and using the two interchangeably makes the producers who actually hold
    spare capacity look as though they hold none. So a declared crude capacity is scaled up by
    that country's own ratio of total liquids to crude before it is used.
    """
    prod = _upto(production.get(iso, []), asof)
    cons = _upto(consumption.get(iso, []), asof)

    last12 = _recent(prod, 12)
    output = (sum(last12) / len(last12) / 1000.0) if last12 else None

    # SPARE CAPACITY IS NOT A UNIVERSAL PROPERTY. A producer outside OPEC+ pumps everything it
    # can: its wells are commercial, its shareholders want the barrel sold today, and its
    # "spare" is the maintenance schedule. Inferring capacity from the best month of five
    # years gave the United States nearly a million barrels a day of phantom slack and put the
    # roster's total spare at 13 mb/d against a published 3-4. So the lookback depends on who
    # is being measured: OPEC+ holds spare on purpose and is measured over five years;
    # everyone else is measured over the last twelve months, where capacity and output are
    # the same thing by construction.
    # For a price taker, CAPACITY IS WHAT IT IS ACTUALLY PRODUCING. Using its best month of
    # the last year instead handed the world about ten million barrels a day of capacity that
    # nobody holds, and since price takers run flat out the market was then permanently
    # oversupplied and the price collapsed in every replay. A producer with no spare has, by
    # definition, no spare.
    if iso in SPARE_HOLDERS:
        best = max(_recent(prod, 60), default=None)
        inferred = (best * 1.02 / 1000.0) if best else None
    else:
        inferred = output

    declared = eia.DECLARED_CAPACITY.get(iso)
    if declared is not None and crude is not None:
        c12 = _recent(_upto(crude.get(iso, []), asof), 12)
        crude_now = (sum(c12) / len(c12) / 1000.0) if c12 else None
        if crude_now and output and crude_now > 0:
            declared = declared * (output / crude_now)     # crude capacity -> total liquids
    capacity = declared if declared is not None else inferred
    if declared is not None and inferred is not None:
        # A declared capacity below what the country has actually produced is not a capacity.
        capacity = max(declared, inferred)

    demand = (cons[-1][1] / 1000.0) if cons else None

    return {
        "production": output,
        "oil_capacity": capacity,
        "capacity_source": "declared" if declared is not None else
                           ("inferred" if inferred else "missing"),
        "oil_demand": demand,
        "demand_asof": cons[-1][0] if cons else None,
        "production_asof": prod[-1][0] if prod else None,
    }


def world_totals(production: dict, consumption: dict, asof: str | None = None) -> dict:
    """What the whole planet pumps and burns, from the EIA's own world aggregate."""
    wp = _upto(production.get("WLD", []), asof)
    wc = _upto(consumption.get("WLD", []), asof)
    return {
        "production": (sum(_recent(wp, 12)) / 12.0 / 1000.0) if len(wp) >= 12 else None,
        "consumption": (wc[-1][1] / 1000.0) if wc else None,
        "production_asof": wp[-1][0] if wp else None,
        "consumption_asof": wc[-1][0] if wc else None,
    }


def apply(countries: dict, asof: str | None = None) -> dict:
    """Overwrite the placeholder energy figures in a copy of the country table.

    Returns `{"countries": ..., "residual": ..., "provenance": ...}`. Nothing is mutated in
    place: the placeholders stay readable in `facts.py` so that the difference between what
    was invented and what was measured is visible in one diff.
    """
    production = eia.load("production")
    consumption = eia.load("consumption")
    try:
        crude = eia.load("crude")
    except FileNotFoundError:
        crude = None

    out, prov = {}, {}
    named_prod = named_cons = 0.0
    for iso, f in countries.items():
        m = measure(iso, production, consumption, crude, asof=asof)
        row = dict(f)
        for key in ("oil_capacity", "oil_demand"):
            if m[key] is not None:
                row[key] = round(m[key], 3)
                prov[f"{iso}.{key}"] = ("declared" if key == "oil_capacity"
                                        and m["capacity_source"] == "declared"
                                        else "measured")
            else:
                prov[f"{iso}.{key}"] = "placeholder"
        row["production_now"] = round(m["production"], 3) if m["production"] else 0.0
        row["capacity_source"] = m["capacity_source"]
        out[iso] = row
        named_prod += row.get("oil_capacity", 0.0) or 0.0
        named_cons += row.get("oil_demand", 0.0) or 0.0

    totals = world_totals(production, consumption, asof=asof)
    # The residual is what the named roster does not cover. It is computed rather than
    # assumed, and if it ever comes out negative that is a double-count to be fixed rather
    # than clipped - so it is reported, not silently floored.
    residual = {
        "capacity": (totals["production"] - sum(
            r.get("production_now", 0.0) for r in out.values())) if totals["production"] else 0.0,
        "demand": (totals["consumption"] - named_cons) if totals["consumption"] else 0.0,
        "world_production": totals["production"], "world_consumption": totals["consumption"],
        "asof": totals["production_asof"],
        "named_capacity": named_prod, "named_demand": named_cons,
    }
    return {"countries": out, "residual": residual, "provenance": prov}


#: The countries that report petroleum stocks to the EIA. Eleven of them, essentially the
#: OECD, and between them they hold most of the world's visible inventory. Days of cover for
#: this group is the best free proxy for how tight the world actually is.
REPORTERS = ("USA", "JPN", "DEU", "FRA", "ITA", "GBR", "KOR", "CAN", "MEX", "ISR", "ISL")
MIN_REPORTERS = 8


def cover_series(asof: str | None = None) -> list[tuple[str, float]]:
    """Days of cover for the reporting group, month by month, point-in-time.

    THIS IS THE INFORMATION THE MODEL WAS MISSING. The clearing prices days of cover, and
    every replay used to begin at exactly sixty of them - so the simulation was never told
    whether the world it was starting in was tight or comfortable. Calibrating coefficients
    against that could only ever push the model towards standing still, which is precisely
    what the search found: the fitted world moved 1.2% while the real one moved 11%.

    Rows stamped at a year end are annual aggregates with a different reporter set and are
    dropped; a month with fewer than eight reporters is dropped too, because a sum over a
    changing membership is not a series.
    """
    from ..archive.ingest import eia
    st = eia.load("stocks")
    cons = eia.load("consumption")

    by_day: dict[str, dict[str, float]] = {}
    for iso in REPORTERS:
        for d, v in _upto(st.get(iso, []), asof):
            if not d.endswith("-01"):
                continue                      # annual stamps: a different reporter set
            by_day.setdefault(d, {})[iso] = v

    out = []
    for d in sorted(by_day):
        present = by_day[d]
        if len(present) < MIN_REPORTERS:
            continue
        total = sum(present.values())
        burn = 0.0
        for iso in present:
            vals = [v for dd, v in _upto(cons.get(iso, []), asof) if dd <= d]
            if vals:
                burn += vals[-1] / 1000.0
        if burn > 0:
            out.append((d, total / burn))
    return out


def cover_now(asof: str | None = None, window_years: int = 10) -> dict:
    """The latest knowable cover, and what NORMAL means as of that date.

    Normal is a trailing ten-year mean rather than a constant, and it is computed only from
    what had been published - so a replay in 2021 uses the norm a person standing in 2021
    would have had, not one computed with the benefit of 2026.
    """
    rows = cover_series(asof)
    if not rows:
        return {"cover": None, "normal": None, "asof": None, "n": 0}
    recent = rows[-window_years * 12:]
    normal = sum(c for _, c in recent) / len(recent)
    return {"cover": rows[-1][1], "normal": normal, "asof": rows[-1][0], "n": len(recent)}


def provenance_summary(prov: dict) -> dict:
    out: dict[str, int] = {}
    for v in prov.values():
        out[v] = out.get(v, 0) + 1
    return out
