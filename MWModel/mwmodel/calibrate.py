"""CALIBRATION - stop asserting the coefficients and start measuring them.

Every number in this model is currently a judgement written in a comment. Some of them were
already shown to be wrong by the scoreboard, and the four structural defects it found were all
of the same kind: a constant pretending to be a model. This module does the obvious next
thing - search for the values that actually fit the record - and it does it under the one
discipline that makes such a search worth anything.

    THE SPLIT IS NOT NEGOTIABLE. Coefficients are chosen on one set of windows and scored on
    another that the search never sees. A calibration that improves the windows it was fitted
    on has demonstrated nothing whatsoever; that is what fitting means.

This laboratory has paid for that lesson four separate times in its previous life, always the
same way: a number improved, the improvement was adopted, and it did not survive contact with
a period nobody had selected on. So `main()` prints the fitted windows and the held-out
windows side by side, and **refuses to adopt a change that does not improve the held-out set**,
however good it looks on the other one.

WHAT IS BEING FITTED, and why these seven

    sensitivity     how hard the price responds to a day of missing cover. The single most
                    consequential number in the model.
    adjust          how much of the required move happens in one day - the market's inertia.
    elasticity      the short-run price elasticity of oil demand, "about -0.05".
    ref_adapt       how fast consumers get used to a new price. Sets the base effects.
    risk_half_life  how long a fear premium lasts when nothing further happens.
    cartel_gain     how strongly OPEC+ responds to the margin over its breakeven.
    floor_convex    how violently the price spikes once cover falls through the floor.

Seven parameters against ten windows is already a generous ratio, which is precisely why the
held-out half exists and why the search is deliberately coarse.
"""

from __future__ import annotations

import json
import random
import sys
from contextlib import contextmanager
from dataclasses import dataclass, asdict

from . import score
from .agents import country as CO
from .markets import commodity as CM
from . import engine as EN

#: Windows the search may look at, and windows it may not. Split by month rather than by year
#: so that both halves contain the same regimes - a split that put all of 2022 on one side
#: would be measuring the era, not the model.
FIT = ("2021-01-01", "2022-01-01", "2023-01-01", "2024-01-01", "2025-01-01")
HOLD = ("2021-07-01", "2022-07-01", "2023-07-01", "2024-07-01", "2025-07-01")


@dataclass
class Knobs:
    sensitivity: float = 2.4
    adjust: float = 0.06
    elasticity: float = 0.05
    ref_adapt: float = 0.0038
    risk_half_life: float = 21.0
    cartel_gain: float = 0.010
    floor_convex: float = 1.8

    def clipped(self) -> "Knobs":
        """Keep the search inside what is physically arguable rather than merely optimal.

        Bounds are not tuning. A demand elasticity of -0.3 would fit some windows beautifully
        and would also be a claim that half the world can stop driving in a month, which the
        literature and the last fifty years both reject. A parameter that has to leave its
        plausible range to help is telling you the MECHANISM is wrong, not the number.
        """
        return Knobs(
            sensitivity=min(6.0, max(0.6, self.sensitivity)),
            adjust=min(0.35, max(0.01, self.adjust)),
            elasticity=min(0.12, max(0.02, self.elasticity)),
            ref_adapt=min(0.02, max(0.0005, self.ref_adapt)),
            risk_half_life=min(90.0, max(5.0, self.risk_half_life)),
            cartel_gain=min(0.06, max(0.0, self.cartel_gain)),
            floor_convex=min(6.0, max(0.0, self.floor_convex)),
        )


@contextmanager
def applied(k: Knobs):
    """Install one set of coefficients for the duration of a run, then put everything back."""
    saved = (CM.SENSITIVITY["crude"], CM.ADJUST, CM.ELASTICITY["crude"],
             CO.REF_ADAPT, EN.RISK_HALF_LIFE, CO.CARTEL_GAIN, CM.FLOOR_CONVEX)
    CM.SENSITIVITY["crude"] = k.sensitivity
    CM.ADJUST = k.adjust
    CM.ELASTICITY["crude"] = k.elasticity
    CO.REF_ADAPT = k.ref_adapt
    EN.RISK_HALF_LIFE = k.risk_half_life
    CO.CARTEL_GAIN = k.cartel_gain
    CM.FLOOR_CONVEX = k.floor_convex
    try:
        yield
    finally:
        (CM.SENSITIVITY["crude"], CM.ADJUST, CM.ELASTICITY["crude"],
         CO.REF_ADAPT, EN.RISK_HALF_LIFE, CO.CARTEL_GAIN, CM.FLOOR_CONVEX) = saved


def cost(k: Knobs, windows, days: int = 120, with_news: bool = True) -> float:
    """The median error ratio against a flat line. Lower is better; 1.00 is the null.

    The MEDIAN rather than the mean, on purpose: one catastrophic window should not be able to
    buy its way out of trouble by dragging an average, and one brilliant window should not be
    able to hide four bad ones.
    """
    with applied(k.clipped()):
        ratios = []
        for w in windows:
            r = score.replay(w, days, with_news=with_news)
            if "ratio" in r:
                ratios.append(r["ratio"])
    if not ratios:
        return float("inf")
    ratios.sort()
    return ratios[len(ratios) // 2]


def search(base: Knobs, windows, iters: int = 40, days: int = 120,
           seed: int = 11, quiet: bool = False) -> tuple[Knobs, float]:
    """A coarse random walk in the neighbourhood of the asserted values.

    Deliberately crude. With seven parameters, ten windows and a simulator in the loop, a
    sophisticated optimiser would only find a more precise overfit; the honest use of a search
    here is to ask "are the asserted numbers roughly right", not to squeeze the last percent.
    """
    rng = random.Random(seed)
    best, best_cost = base, cost(base, windows, days)
    if not quiet:
        print(f"    start {best_cost:.3f}")
    for i in range(iters):
        scale = 0.45 if i < iters // 2 else 0.18     # coarse first, then local
        trial = Knobs(
            sensitivity=best.sensitivity * (1 + rng.gauss(0, scale)),
            adjust=best.adjust * (1 + rng.gauss(0, scale)),
            elasticity=best.elasticity * (1 + rng.gauss(0, scale * 0.7)),
            ref_adapt=best.ref_adapt * (1 + rng.gauss(0, scale)),
            risk_half_life=best.risk_half_life * (1 + rng.gauss(0, scale)),
            cartel_gain=best.cartel_gain * (1 + rng.gauss(0, scale)),
            floor_convex=best.floor_convex * (1 + rng.gauss(0, scale)),
        ).clipped()
        c = cost(trial, windows, days)
        if c < best_cost:
            best, best_cost = trial, c
            if not quiet:
                print(f"    {i:>3d}  {c:.3f}  sens {trial.sensitivity:.2f} "
                      f"adj {trial.adjust:.3f} elas {trial.elasticity:.3f} "
                      f"ref {trial.ref_adapt:.4f} risk {trial.risk_half_life:.0f}d")
    return best, best_cost


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    iters = int(argv[0]) if argv and argv[0].isdigit() else 40

    base = Knobs()
    print("MWModel - CALIBRATION")
    print(f"  fitting on {len(FIT)} windows, scoring on {len(HOLD)} the search never sees")
    print(f"  {iters} trials, seven coefficients, all bounded to what is physically arguable\n")

    base_fit = cost(base, FIT)
    base_hold = cost(base, HOLD)
    print(f"  ASSERTED   fit {base_fit:.3f}   held out {base_hold:.3f}")

    print("\n  searching:")
    best, best_fit = search(base, FIT, iters=iters)
    best_hold = cost(best, HOLD)

    print(f"\n  FITTED     fit {best_fit:.3f}   held out {best_hold:.3f}")
    print(f"  {'':<16}{'asserted':>12}{'fitted':>12}")
    for field, a in asdict(base).items():
        b = getattr(best, field)
        print(f"  {field:<16}{a:>12.4f}{b:>12.4f}")

    adopt = best_hold < base_hold
    print()
    if adopt:
        print(f"  ADOPT. The held-out windows improved {base_hold:.3f} -> {best_hold:.3f}, "
              f"which is\n  the only evidence that counts.")
    else:
        print(f"  DO NOT ADOPT. The fit improved {base_fit:.3f} -> {best_fit:.3f} and the "
              f"held-out\n  windows did not ({base_hold:.3f} -> {best_hold:.3f}). That is "
              f"what overfitting looks\n  like, and the asserted values stand.")

    out = {"iters": iters, "fit_windows": list(FIT), "hold_windows": list(HOLD),
           "asserted": asdict(base), "fitted": asdict(best),
           "cost": {"asserted_fit": base_fit, "asserted_hold": base_hold,
                    "fitted_fit": best_fit, "fitted_hold": best_hold},
           "adopt": adopt}
    p = score.W.WORLD_ROOT.parent / "calibration_report.json"
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\n  written {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
