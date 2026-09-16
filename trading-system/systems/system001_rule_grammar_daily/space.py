"""What a search is allowed to move, declared by the hypothesis that owns it.

This lives in the TRADING SYSTEM, not the optimiser, for the same reason
`policy.py` does: the legal range of a parameter is a claim about the
hypothesis, not about the machinery that searches it. "Bull breadth may sit
between 0.35 and 0.75" is a statement someone can disagree with; the genetic
algorithm that samples it has no opinion and should not be where the claim is
recorded.

The optimiser in `quantlab_manager.search` imports these and never the other way
round -- a strategy that could reach into the lab that scores it is exactly the
coupling the three-folder split exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import random


@dataclass(frozen=True)
class Dimension:
    """One knob, and the range a search is allowed to move it through.

    `choices` makes it categorical (which branch rule runs in which regime);
    otherwise it is numeric and `integer` decides whether a bar count or a
    fraction comes out.
    """

    name: str
    low: float = 0.0
    high: float = 1.0
    integer: bool = False
    choices: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        if self.choices:
            return
        if self.high < self.low:
            raise ValueError(f"{self.name}: high is below low")

    def sample(self, rng: random.Random) -> Any:
        if self.choices:
            return rng.choice(self.choices)
        value = rng.uniform(self.low, self.high)
        return int(round(value)) if self.integer else value

    def clip(self, value: Any) -> Any:
        if self.choices:
            return value if value in self.choices else self.choices[0]
        try:
            value = float(value)
        except (TypeError, ValueError):
            return self.low
        value = min(self.high, max(self.low, value))
        return int(round(value)) if self.integer else value

    def nudge(self, value: Any, rng: random.Random, scale: float = 0.15) -> Any:
        """A local move, not a re-roll.

        Mutation that re-samples uniformly destroys whatever the parent knew. A
        gaussian step proportional to the dimension's own width keeps the child
        in the parent's neighbourhood, which is the whole reason a population
        converges instead of wandering.
        """
        if self.choices:
            return rng.choice(self.choices)
        span = (self.high - self.low) or 1.0
        return self.clip(self.clip(value) + rng.gauss(0.0, span * scale))


@dataclass(frozen=True)
class SearchSpace:
    dimensions: tuple[Dimension, ...]

    def __post_init__(self) -> None:
        names = [d.name for d in self.dimensions]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            # Two dimensions with one name means one silently wins and the other
            # is searched over a range nobody declared.
            raise ValueError(f"duplicate dimensions: {sorted(duplicates)}")

    def sample(self, rng: random.Random) -> dict[str, Any]:
        return {d.name: d.sample(rng) for d in self.dimensions}

    def clip(self, genome: dict[str, Any]) -> dict[str, Any]:
        return {
            d.name: d.clip(genome[d.name])
            if d.name in genome
            else d.sample(random.Random(0))
            for d in self.dimensions
        }

    def crossover(
        self, a: dict[str, Any], b: dict[str, Any], rng: random.Random
    ) -> dict[str, Any]:
        """Uniform crossover: each gene from either parent, independently.

        Single-point crossover makes neighbouring dimensions inherit together,
        and the order of a declaration is not a statement about which parameters
        interact.
        """
        return {
            d.name: (a if rng.random() < 0.5 else b).get(d.name, a.get(d.name))
            for d in self.dimensions
        }

    def mutate(
        self, genome: dict[str, Any], rng: random.Random, rate: float = 0.25
    ) -> dict[str, Any]:
        return {
            d.name: (
                d.nudge(genome.get(d.name, d.low), rng)
                if rng.random() < rate
                else genome.get(d.name, d.low)
            )
            for d in self.dimensions
        }
