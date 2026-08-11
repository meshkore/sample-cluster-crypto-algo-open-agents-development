"""The knobs the loop is allowed to turn on itself, and their limits.

This is the whole safety story for self-improvement, so it is worth being blunt
about what it is and is not.

**What the loop may change about itself: these numbers, and nothing else.** Not
a line of Python, not the contract, not the lock, not the drawdown mandate, not
which folds exist. A self-improving process whose blast radius is "the search
runs five generations instead of four" is a different and much smaller thing
than one that can rewrite the code that decides what a result means, and this
project takes the first and refuses the second. That is the same line
`team.py` draws for the advisors, applied to the loop itself: the current
literature on self-evolving agents calls it bounding evolution to text-mutable
artifacts, and reaches the same conclusion from the other direction.

**Every knob has a hard range, checked here.** A proposal outside it is
discarded, not clamped -- clamping would let a model that asked for a
population of ten thousand quietly get the maximum and think it got what it
asked for, which makes the record of what was tried a lie.

**Every change is recorded.** `apply` returns what actually moved, and the
caller writes it to the append-only ledger. An unattended process that retunes
itself and leaves no trace is one nobody can audit afterwards, and afterwards
is the only time anyone looks.

The file itself is small JSON on disk so a human can read it, edit it, or throw
it away, and the loop picks the change up at the next iteration without a
restart.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json


class Knob:
    """One tunable number: what it means, what it may be, and why it is capped.

    `why` is not decoration. It is sent to the evolve session as the reason the
    bound exists, because a model told only "population must be <= 24" will
    propose 24 and a model told why will sometimes propose 8.
    """

    def __init__(
        self,
        name: str,
        default: float | int,
        low: float | int,
        high: float | int,
        integer: bool,
        what: str,
        why: str,
    ):
        self.name = name
        self.default = default
        self.low = low
        self.high = high
        self.integer = integer
        self.what = what
        self.why = why

    def clean(self, value: Any) -> float | int | None:
        """The value if it is admissible, else None. Never a clamp."""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number != number or number in (float("inf"), float("-inf")):
            return None
        if self.integer:
            if number != int(number):
                return None
            number = int(number)
        return number if self.low <= number <= self.high else None

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "what": self.what,
            "range": [self.low, self.high],
            "default": self.default,
            "why_bounded": self.why,
        }


KNOBS: tuple[Knob, ...] = (
    Knob(
        "explore_every",
        default=5,
        low=3,
        high=12,
        integer=True,
        what=(
            "One turn in N ignores the diagnosis and works the module with the "
            "least evidence behind it."
        ),
        why=(
            "Below 3 the loop barely follows its own diagnosis and stops "
            "converging on anything; above 12 it reverts to the greedy "
            "behaviour that spent 35 of 102 iterations on one module."
        ),
    ),
    Knob(
        "generations",
        default=4,
        low=2,
        high=8,
        integer=True,
        what="Generations of the genetic search per iteration.",
        why=(
            "Each generation is a full pass over the population across four "
            "folds, so this multiplies wall-clock directly. Past 8 an iteration "
            "takes longer than the operator's attention span and the loop "
            "produces fewer, later results rather than better ones."
        ),
    ),
    Knob(
        "population",
        default=10,
        low=6,
        high=24,
        integer=True,
        what="Individuals per generation.",
        why=(
            "Below 6 the search has no diversity to recombine and collapses "
            "onto the incumbent. The upper bound is wall-clock again: "
            "population times generations times folds is the backtest count."
        ),
    ),
    Knob(
        "gate",
        default=0.02,
        low=0.0,
        high=0.15,
        integer=False,
        what=(
            "How much better than the best known score for this module a fit "
            "must be before the sealed 2026 window is opened on it."
        ),
        why=(
            "This is the rate at which the one irreplaceable resource is spent. "
            "Zero opens 2026 on every fit that is not worse, which burns the "
            "forward window on noise; high values mean the loop fits for days "
            "and never measures anything."
        ),
    ),
)

BY_NAME: dict[str, Knob] = {knob.name: knob for knob in KNOBS}


def defaults() -> dict[str, Any]:
    return {knob.name: knob.default for knob in KNOBS}


def catalogue() -> list[dict[str, Any]]:
    """What the evolve session is told it may touch."""
    return [knob.describe() for knob in KNOBS]


def load(path: Path | str) -> dict[str, Any]:
    """Current settings, with anything missing or inadmissible falling back.

    A corrupt or hand-edited file degrades to defaults rather than raising: the
    research loop must not be stoppable by a bad number in a tuning file, and a
    knob that silently reverts to its default is visible in the next evolve
    briefing.
    """
    values = defaults()
    try:
        stored = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return values
    if not isinstance(stored, dict):
        return values
    for name, raw in stored.items():
        knob = BY_NAME.get(name)
        if knob is None:
            continue
        cleaned = knob.clean(raw)
        if cleaned is not None:
            values[name] = cleaned
    return values


def apply(path: Path | str, proposed: Any) -> list[dict[str, Any]]:
    """Write admissible changes and return exactly what moved.

    Returns a list of `{knob, from, to, }` rather than a bare success flag,
    because the caller's job is to write that into the ledger. A change nobody
    can point at afterwards is indistinguishable from a change that never
    happened.
    """
    if not isinstance(proposed, dict):
        return []
    current = load(path)
    changes: list[dict[str, Any]] = []
    for name, raw in proposed.items():
        knob = BY_NAME.get(name)
        if knob is None:
            continue
        cleaned = knob.clean(raw)
        if cleaned is None or cleaned == current[name]:
            continue
        changes.append({"knob": name, "from": current[name], "to": cleaned})
        current[name] = cleaned
    if not changes:
        return []
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
    return changes
