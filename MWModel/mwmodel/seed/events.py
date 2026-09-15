"""THE NEWS, AND WHAT IT DOES TO THE WORLD.

    *"En un ecosistema, día tras día vamos suministrando noticias... y lo vamos corrigiendo con
    lo que va pasando en realidad."*

The scoreboard made the case for this module better than any argument could. Replaying 2022
from the first of January, the model held crude near seventy while the world went to a hundred
and eleven - and it was right to, given what it knew, because nobody had told it that Russia
would invade Ukraine in February. A world with no news cannot beat a flat line and should not
be expected to.

So events carry EFFECTS: the specific, named thing each one does to the world state. Four
channels, and keeping them separate is the point, because they behave differently and decay
differently.

    valve.<key>      a strait's open fraction changes. Physical, persistent until changed.
    capacity.<ISO>   a producer's capacity is multiplied. Sanctions, war damage, a cartel
                     decision. Persistent.
    demand.<ISO>     a consumer's demand index is multiplied. A pandemic, a tariff, a
                     recession. Persistent.
    risk             a premium paid for fear rather than for a missing barrel. It moves the
                     price with no change in any quantity, and it DECAYS - which is the whole
                     difference between a scare and a shortage. The 2024 Red Sea episode is
                     the clean example: freight multiplied, crude barely moved, and within
                     weeks the premium was gone.

EVERY EFFECT SIZE HERE IS A JUDGEMENT, not an estimate, and they are written in one table so
they can be argued with rather than discovered inside a result. Phase 2 fits them: with the
chronicle dated and the price history in the archive, each one is a regression waiting to be
run, and several of them will turn out to be wrong.
"""

from __future__ import annotations

from datetime import date

#: (day, headline, {effect: value}, decay_days). `decay_days` applies only to `risk`; the
#: physical channels persist until another event changes them.
ENERGY_EVENTS: tuple[tuple, ...] = (
    ("2020-03-06", "OPEC+ talks collapse; Saudi Arabia opens the taps",
     {"capacity.SAU": 1.10, "discipline.SAU": 0.0}, 0),
    ("2020-03-11", "The pandemic is declared; demand falls off a cliff",
     {"demand.world": 0.80}, 0),
    ("2020-04-12", "OPEC+ agrees the largest cut ever made, 9.7 mb/d",
     {"capacity.SAU": 0.78, "capacity.RUS": 0.85, "capacity.IRQ": 0.82,
      "capacity.ARE": 0.82, "capacity.KWT": 0.82, "discipline.SAU": 0.95}, 0),
    ("2020-06-01", "Demand begins to recover as lockdowns lift",
     {"demand.world": 1.08}, 0),
    ("2021-01-05", "Saudi Arabia announces a unilateral extra cut of 1 mb/d",
     {"capacity.SAU": 0.93}, 0),
    # CORRECTED 2026-09-15 by the scoreboard. This was written with `demand.world: 1.04`
    # attached, which made the informed replay of July 2021 worse by a factor of five - it
    # sent crude to $102 against an actual $72. Two errors in one line: an agreement to unwind
    # SUPPLY cuts is not a demand event at all, and a four percent step in world demand is not
    # a thing that happens on a Tuesday. Gradual recoveries belong in the GDP path, not in an
    # event. The remaining supply effect is also smaller, because the unwinding was a schedule
    # of monthly increments rather than a single decision taking effect at once.
    ("2021-07-18", "OPEC+ agrees to unwind the cuts month by month",
     {"capacity.SAU": 1.03, "capacity.RUS": 1.02}, 0),

    ("2022-02-24", "Russia invades Ukraine",
     {"risk": 0.22, "capacity.RUS": 0.94}, 90),
    ("2022-03-08", "The United States bans imports of Russian oil",
     {"risk": 0.10, "capacity.RUS": 0.97}, 45),
    ("2022-03-31", "The largest strategic reserve release in history: 1 mb/d for six months",
     {"capacity.USA": 1.04, "risk": -0.06}, 60),
    ("2022-06-01", "China's lockdowns cut consumption",
     {"demand.CHN": 0.93}, 0),
    ("2022-10-05", "OPEC+ cuts two million barrels a day",
     {"capacity.SAU": 0.94, "capacity.ARE": 0.95, "capacity.IRQ": 0.95}, 0),
    ("2022-12-05", "The EU embargo and the G7 price cap on Russian crude take effect",
     {"risk": 0.06, "capacity.RUS": 0.96}, 60),

    ("2023-04-02", "OPEC+ announces a surprise cut of 1.66 mb/d",
     {"capacity.SAU": 0.95, "capacity.ARE": 0.96, "capacity.IRQ": 0.96,
      "capacity.KWT": 0.96}, 0),
    ("2023-06-04", "Saudi Arabia adds a unilateral cut of 1 mb/d",
     {"capacity.SAU": 0.91}, 0),
    ("2023-10-07", "War begins in Gaza; a risk premium appears with no barrel lost",
     {"risk": 0.09}, 40),

    ("2024-01-12", "Attacks in the Red Sea; tankers begin to route around the Cape",
     {"valve.bab_el_mandeb": 0.35, "risk": 0.04}, 30),
    ("2024-06-02", "OPEC+ sets out a schedule to return the voluntary cuts",
     {"capacity.SAU": 1.06, "capacity.ARE": 1.05}, 0),
    ("2024-12-05", "OPEC+ delays the unwinding again",
     {"capacity.SAU": 0.97}, 0),

    ("2025-04-02", "Sweeping US tariffs; the demand outlook is cut",
     {"demand.world": 0.985, "risk": -0.03}, 45),
    ("2025-04-03", "OPEC+ accelerates the return of supply into a falling market",
     {"capacity.SAU": 1.05, "capacity.ARE": 1.04, "discipline.SAU": 0.4}, 0),
    ("2025-06-13", "Strikes between Israel and Iran; Hormuz risk is priced",
     {"risk": 0.17, "valve.hormuz": 0.85}, 25),
    ("2025-06-24", "A ceasefire holds; the Hormuz premium unwinds",
     {"risk": -0.14, "valve.hormuz": 1.0}, 15),
)


def between(start: str, end: str) -> list[dict]:
    """Every energy event knowable in the window, chronological."""
    out = []
    for day, headline, effects, decay in ENERGY_EVENTS:
        if start[:10] <= day <= end[:10]:
            out.append({"day": day, "headline": headline, "effects": effects,
                        "decay_days": decay})
    return sorted(out, key=lambda e: e["day"])


def on(day: str) -> list[dict]:
    return [{"day": d, "headline": h, "effects": e, "decay_days": k}
            for d, h, e, k in ENERGY_EVENTS if d == day[:10]]


def feeder(quiet: bool = True):
    """A `news_for(day)` callable for `engine.run`, delivering each event on its own date."""
    def news_for(day: str) -> list[dict]:
        rows = on(day)
        if rows and not quiet:
            for r in rows:
                print(f"    [{r['day']}] {r['headline']}")
        return rows
    return news_for
