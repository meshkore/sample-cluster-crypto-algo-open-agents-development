"""PROJECTION - the part the operator cares about, and the only honest form it can take.

    *"El estado actual, al final, ya lo sabemos. Lo que queremos saber es qué pasará en una
    semana, en un mes."*

A projection here is the same tick loop run forward with no new data, many times, with the
uncertain things sampled rather than assumed. Three sources of uncertainty, and they are
genuinely different:

  SCENARIO   A chokepoint is not a constant, it is the current state of a negotiation. Hormuz
             can be open, harassed or closed, and it MOVES - because, as the operator put it,
             *"nada es eterno... todo el mundo lucha por sus propios intereses, de tal manera
             que las cosas se mueven"*. So the valve has a transition matrix, and the
             probabilities in it respond to who is hurting: a producer far below its fiscal
             breakeven wants a deal, and a consumer paying two hundred dollars a barrel wants
             one badly enough to offer something.
  PARAMETER  Every calibrated coefficient is uncertain. Elasticity is "about -0.05", not
             -0.05, and the difference between those two is most of the price range.
  SHOCK      The residual the model cannot explain, resampled rather than set to zero.

THE OUTPUT IS NEVER A NUMBER. It is a distribution with a causal chain attached, because a
point forecast cannot be argued with and therefore cannot be improved. "Brent in sixty days:
median 94, eighty percent interval [71, 168], and the upper tail is Hormuz" is a statement a
person can act on and a statement that can later be scored.

WHAT THIS IS NOT, YET. The transition probabilities below are judgement, not estimates. They
are written here rather than hidden so they can be argued with and, in phase 5, replaced by a
reasoning agent that reads the news and the incentives and sets them itself.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field

from . import engine
from .network import chokepoints as CP
from .state import WorldState

#: Valve states and how open they are.
VALVE_STATES = {"open": 1.0, "harassed": 0.55, "closed": 0.12}

#: Daily transition probabilities, before incentives adjust them. Deliberately sticky: a
#: strait that is open today is overwhelmingly likely to be open tomorrow, which is why the
#: interesting risk lives in the tail rather than the mean.
BASE_TRANSITIONS = {
    "open":     {"open": 0.995, "harassed": 0.0045, "closed": 0.0005},
    "harassed": {"open": 0.020, "harassed": 0.972, "closed": 0.008},
    "closed":   {"open": 0.010, "harassed": 0.045, "closed": 0.945},
}

#: How strongly pain pushes towards a settlement. At two hundred dollars a barrel the pressure
#: to reopen is large; at sixty it is nearly absent. This single coefficient is the model's
#: entire theory of "everyone fights for their own interests, so things move", and it is
#: exposed rather than buried so it can be attacked.
PRESSURE = 3.5
PRESSURE_REF = 80.0


@dataclass
class Fan:
    """One variable's projected distribution: the median and the interval, day by day."""

    key: str
    days: list[str]
    p10: list[float] = field(default_factory=list)
    p50: list[float] = field(default_factory=list)
    p90: list[float] = field(default_factory=list)


def _next_state(state: str, price: float, rng: random.Random) -> str:
    """Where the valve goes tomorrow, given where it is and how much the world is hurting."""
    row = dict(BASE_TRANSITIONS[state])
    if state != "open":
        # The more expensive oil is, the harder everyone works to reopen the strait: the
        # exporter is losing its own revenue and the importers are paying for it.
        pain = max(0.0, price / PRESSURE_REF - 1.0)
        lift = min(0.35, row["open"] * PRESSURE * pain)
        row["open"] += lift
        drain = lift / max(1e-9, (1.0 - row["open"] + lift))
        for k in row:
            if k != "open":
                row[k] *= (1.0 - drain)
    total = sum(row.values())
    r = rng.random() * total
    acc = 0.0
    for k, p in row.items():
        acc += p
        if r <= acc:
            return k
    return state


def project(w: WorldState, agents: list, horizon: int = 60, runs: int = 48,
            valve: str = "hormuz", start_state: str = "open",
            seed: int = 7) -> dict:
    """Run the world forward `runs` times and report the distribution.

    Each run is a full copy of the world, so nothing a projection does can touch the state
    the system actually believes in. That isolation is not a nicety: a projection that mutated
    the present would make every subsequent measurement meaningless and would be very hard to
    notice.
    """
    base_rng = random.Random(seed)
    tracked = ["crude"]
    cpi_of = [a.id for a in agents if a.id.startswith("country.")][:40]

    paths: list[dict] = []
    valve_paths: list[list[float]] = []
    for r in range(runs):
        rng = random.Random(base_rng.randrange(1 << 30))
        sw = copy.deepcopy(w)
        sa = copy.deepcopy(agents)
        state = start_state

        # Parameter uncertainty: this run's world is slightly different from the last one's.
        from .markets import commodity
        elas = commodity.ELASTICITY["crude"] * rng.uniform(0.7, 1.45)

        run = {"crude": [], "cpi": {c: [] for c in cpi_of}}
        valve_path = []
        for _ in range(horizon):
            state = _next_state(state, sw.price("crude"), rng)
            CP.constrain(sw, valve, VALVE_STATES[state], why=f"scenario: {state}")
            valve_path.append(VALVE_STATES[state])

            saved = commodity.ELASTICITY["crude"]
            commodity.ELASTICITY["crude"] = elas
            try:
                engine.step(sw, sa, [])
            finally:
                commodity.ELASTICITY["crude"] = saved

            # The shock: what the model cannot explain, rather than nothing.
            m = sw.markets["crude"]
            m.price = max(1.0, m.price * (1.0 + rng.gauss(0.0, 0.012)))

            run["crude"].append(m.price)
            for c in cpi_of:
                run["cpi"][c].append(sw.var(c, "cpi_yoy"))
        paths.append(run)
        valve_paths.append(valve_path)

    days = [_shift(w.day, i + 1) for i in range(horizon)]

    def fan(series: list[list[float]], key: str) -> Fan:
        f = Fan(key=key, days=days)
        for t in range(horizon):
            col = sorted(s[t] for s in series)
            f.p10.append(col[int(0.10 * (len(col) - 1))])
            f.p50.append(col[int(0.50 * (len(col) - 1))])
            f.p90.append(col[int(0.90 * (len(col) - 1))])
        return f

    crude = fan([p["crude"] for p in paths], "crude")
    cpi = {c: fan([p["cpi"][c] for p in paths], c) for c in cpi_of}

    closed_ever = sum(1 for vp in valve_paths if min(vp) <= VALVE_STATES["closed"] + 1e-9)
    harassed_end = sum(1 for vp in valve_paths if vp[-1] < 1.0)

    return {
        "horizon": horizon, "runs": runs, "valve": valve, "start_state": start_state,
        "days": days,
        "crude": {"p10": crude.p10, "p50": crude.p50, "p90": crude.p90},
        "cpi": {c: {"p10": f.p10, "p50": f.p50, "p90": f.p90} for c, f in cpi.items()},
        "valve_open_mean": [sum(vp[t] for vp in valve_paths) / len(valve_paths)
                            for t in range(horizon)],
        "scenarios": {
            "closed_at_some_point": closed_ever / max(1, runs),
            "still_constrained_at_horizon": harassed_end / max(1, runs),
        },
        "why": _explain(w, crude, cpi),
    }


def _explain(w: WorldState, crude: Fan, cpi: dict[str, Fan]) -> list[str]:
    """The causal chain behind the fan, in words. The viewer's 'why' panel reads this.

    A projection nobody can interrogate is a number on a screen. This is the minimum an
    operator needs in order to disagree with it.
    """
    now = w.price("crude")
    end = crude.p50[-1]
    hi, lo = crude.p90[-1], crude.p10[-1]
    out = [
        f"Crude starts at ${now:,.1f}. The median path ends at ${end:,.1f} "
        f"({(end / now - 1):+.1%}), with an 80% interval of ${lo:,.1f} to ${hi:,.1f}.",
        f"The width of that interval is almost entirely the valve: the upper tail is the "
        f"runs in which the strait stays shut, the lower tail the runs in which it reopens "
        f"and stranded barrels return to the market.",
    ]
    # Rank by the size of the MOVE, and refuse to narrate noise. A tenth of a basis point is
    # not a finding, and dressing it up as one is how a viewer stops being believed.
    moves = sorted(((f.p50[-1] - f.p50[0], c) for c, f in cpi.items()),
                   key=lambda kv: abs(kv[0]), reverse=True)[:3]
    if not moves or abs(moves[0][0]) < 0.0015:
        out.append("No country's inflation moves more than fifteen basis points on the median "
                   "path: with the straits open, this is a quiet world and the energy channel "
                   "is carrying almost nothing.")
        return out
    for move, c in moves:
        if abs(move) < 0.0005:
            continue
        out.append(f"{c.split('.')[-1]}: inflation moves {move:+.2%} on the median path over "
                   f"the horizon, through the energy component of its basket.")
    return out


def _shift(day: str, n: int) -> str:
    from datetime import date, timedelta
    return (date.fromisoformat(day[:10]) + timedelta(days=n)).isoformat()
