"""THE SCOREBOARD - replay history and find out whether any of this is worth anything.

    *"Lo compararás, haremos el fine tuning y calcularemos la siguiente hora."*

This is steps 8 to 10 of the tick loop in the master plan, and it is the only thing that
separates a simulation from an animation. Start the world on a past date, seeded with what was
PUBLISHED by then, run it forward with no further information, and compare what it produced
with what actually happened.

THE NULL IS A FLAT LINE, and that is not a soft target. The price of oil is close to a random
walk: "tomorrow is today" beats most forecasts most of the time, at every horizon anyone has
studied, and any model that cannot beat it has learned nothing it did not start with. It is
printed on the same screen as the model's own error, always, because a root-mean-square error
with nothing beside it can be made to look like whatever the author needs.

WHAT A FAILURE HERE MEANS. If the model loses to a flat line, that is a result and it gets
written down. The response is never to tune until the number turns - this laboratory has paid
for that lesson four times - it is to find which link of the chain is wrong and fix the link.
The per-agent attribution in `attribute()` exists for exactly that.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from . import archive as W
from . import engine
from .seed.build import build

#: The archive's own reading of the oil price - the thing the simulation is trying to match.
TRUTH = "global.commodity.oil_wti"
HORIZONS = (7, 30, 60, 90)


def _actual(day: str) -> float | None:
    """What crude actually cost on `day`, as it was knowable then."""
    try:
        return W.asof(TRUTH, day, sealed=True)
    except Exception:
        return None


def replay(start: str, days: int = 120, quiet: bool = True,
           with_news: bool = False) -> dict:
    """Run the world from `start` for `days`.

    `with_news=False` is the blind run: the world is seeded with what was published on the
    start date and then told nothing further. `with_news=True` delivers the dated energy
    events as they occur, which is the phase-1 gate - *"replaying 2022 with only the events
    known at each date"*. The gap between the two is the value of knowing what happened, and
    it is the cleanest single measurement of whether the event channel is worth anything.
    """
    w, agents = build(day=start)
    anchor = _actual(start)
    if anchor:
        # Start from the real price. The model is being asked to predict the PATH, not to
        # rediscover the level, and letting it start somewhere else would confuse the two.
        w.markets["crude"].price = anchor
        # And what every consumer is USED TO paying starts there as well. Seeding the world at
        # $110 while telling every country it normally pays $68 would manufacture a collapse
        # on the first tick that had nothing to do with the world.
        for a in agents:
            if a.id.startswith("country.") or a.id.startswith("region."):
                w.set_var(a.id, "ref_price", anchor)

    from .seed import events as EV
    feed = EV.feeder() if with_news else None

    sim, truth, ds = [], [], []
    for _ in range(days):
        engine.step(w, agents, feed(w.day) if feed else [])
        a = _actual(w.day)
        sim.append(w.price("crude"))
        truth.append(a)
        ds.append(w.day)
        if not quiet:
            print(f"  {w.day}  sim ${w.price('crude'):7.2f}  actual "
                  f"{('$%7.2f' % a) if a else '      —'}")

    pairs = [(s, t) for s, t in zip(sim, truth) if t]
    if not pairs:
        return {"start": start, "error": "no actual prices in this window"}

    def rmse(pred_of) -> float:
        errs = [(pred_of(i, s, t) - t) ** 2 for i, (s, t) in enumerate(pairs)]
        return (sum(errs) / len(errs)) ** 0.5

    model = rmse(lambda i, s, t: s)
    null = rmse(lambda i, s, t: anchor or pairs[0][1])

    per_h = {}
    for h in HORIZONS:
        if h <= len(pairs):
            s, t = pairs[h - 1]
            per_h[h] = {"sim": s, "actual": t, "null": anchor,
                        "model_err": abs(s - t),
                        "null_err": abs((anchor or t) - t)}

    return {"start": start, "days": days, "anchor": anchor,
            "rmse_model": model, "rmse_null": null,
            "beats_null": model < null,
            "ratio": model / null if null else float("nan"),
            "per_horizon": per_h,
            "path": {"days": ds, "sim": sim, "actual": truth}}


def attribute(start: str, days: int = 120) -> dict:
    """WHICH PART is wrong: the quantity the model produced, or the price it charged for it.

    The two failures look identical in a price error and need opposite fixes. If simulated
    supply matches the world's and the price does not, the clearing is wrong. If supply itself
    drifts, the producers' policies are wrong and no amount of clearing will rescue it.
    """
    w, agents = build(day=start)
    anchor = _actual(start)
    if anchor:
        w.markets["crude"].price = anchor
        for a in agents:
            w.set_var(a.id, "ref_price", anchor)

    sup, dem = [], []
    for _ in range(days):
        r = engine.step(w, agents, [])
        sup.append(r.supply)
        dem.append(r.demand)

    published = w.var("__world", "world_production", 0.0)
    consumed = w.var("__world", "world_consumption", 0.0)
    mean_sup = sum(sup) / len(sup) if sup else 0.0
    mean_dem = sum(dem) / len(dem) if dem else 0.0
    return {
        "supply_sim": mean_sup, "supply_published": published,
        "supply_error_pct": (mean_sup / published - 1.0) if published else None,
        "demand_sim": mean_dem, "demand_published": consumed,
        "demand_error_pct": (mean_dem / consumed - 1.0) if consumed else None,
        "verdict": ("quantities are right; the error is in the clearing"
                    if published and abs(mean_sup / published - 1.0) < 0.02
                    else "the quantities themselves are off; fix the producers before the price"),
    }


def sweep(starts: list[str], days: int = 120, with_news: bool = False) -> dict:
    """The same test on several start dates, because one window is an anecdote."""
    rows = [replay(s, days, with_news=with_news) for s in starts]
    good = [r for r in rows if "rmse_model" in r]
    return {
        "days": days,
        "runs": [{k: v for k, v in r.items() if k != "path"} for r in good],
        "won": sum(1 for r in good if r["beats_null"]),
        "n": len(good),
        "median_ratio": sorted(r["ratio"] for r in good)[len(good) // 2] if good else None,
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    days = int(argv[0]) if argv and argv[0].isdigit() else 120
    starts = [f"{y}-{m}-01" for y in (2021, 2022, 2023, 2024, 2025) for m in ("01", "07")]

    print("MWModel - SCOREBOARD: can the simulated world beat a flat line?")
    print(f"  {len(starts)} start dates, {days} days each, seeded only with what was")
    print("  published on the day the run begins. No events are injected.\n")
    print(f"  {'start':<12}{'anchor':>9}{'blind d90':>10}{'news d90':>11}"
          f"{'actual d90':>12}{'ratio bl':>9}{'ratio nw':>10}")

    blind = sweep(starts, days, with_news=False)
    told = sweep(starts, days, with_news=True)
    by_start = {r["start"]: r for r in told["runs"]}
    for r in blind["runs"]:
        h = r["per_horizon"].get(90) or {}
        t = by_start.get(r["start"], {})
        th = (t.get("per_horizon") or {}).get(90) or {}
        print(f"  {r['start']:<12}{r['anchor'] or 0:>9.1f}{h.get('sim', 0):>10.1f}"
              f"{th.get('sim', 0):>11.1f}{h.get('actual', 0):>12.1f}"
              f"{r['ratio']:>9.2f}{t.get('ratio', float('nan')):>10.2f}")

    print(f"\n  BLIND      beats a flat line in {blind['won']}/{blind['n']} windows, "
          f"median error ratio {blind['median_ratio']:.2f}")
    print(f"  WITH NEWS  beats a flat line in {told['won']}/{told['n']} windows, "
          f"median error ratio {told['median_ratio']:.2f}")
    print("  (below 1.00 beats a flat line. The gap between those two rows is what knowing")
    print("   what happened is worth, and it is the phase-1 gate.)")
    out = {"blind": blind, "with_news": told}

    att = attribute(starts[-1], days)
    print(f"\n  ATTRIBUTION on {starts[-1]}:")
    print(f"    supply  simulated {att['supply_sim']:.2f} vs published "
          f"{att['supply_published']:.2f} mb/d  ({att['supply_error_pct']:+.2%})")
    print(f"    demand  simulated {att['demand_sim']:.2f} vs published "
          f"{att['demand_published']:.2f} mb/d  ({att['demand_error_pct']:+.2%})")
    print(f"    {att['verdict']}")

    path = W.WORLD_ROOT.parent / "score_report.json"
    path.write_text(json.dumps({**out, "attribution": att}, indent=1), encoding="utf-8")
    print(f"\n  written {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
