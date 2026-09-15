"""AN ENTITY - an agent that also listens, speaks, and decides what it is worth listening to.

`Agent` (in agents/base.py) is a player with a balance, an interest and a policy. An `Entity`
is an agent wired into the bus: it declares the channels it hears and the channels it speaks
on, and it can change both while the simulation is running.

    listens     patterns it is subscribed to now - not for ever
    emits       the channels it is the publisher of record for
    on_event    one event in, zero or more events out. The cascade is made of these.
    review      periodically, decide what to keep listening to

WHY DYNAMIC SUBSCRIPTION IS THE INTERESTING PART
The operator: *"each one of these agents has to be alive. If China stops exporting cars it has
to stop subscribing to the channels that affect that industry."* A fixed wiring diagram is a
model of one moment. The world's wiring changes - Germany bought Russian gas until it did not,
and every elasticity estimated across that break is an average of two different worlds. An
entity that can drop a channel can represent the break instead of smearing it.

AND WHY IT IS ALSO THE EASIEST PLACE TO CHEAT
"This entity decides what matters to it" is one short step from "this entity listens to
whatever makes the fit better", which is overfitting with extra steps. So there is a rule, and
it is the same rule the rest of this laboratory runs on:

    A MODEL MAY PROPOSE A SUBSCRIPTION. ONLY THE RECORD MAY ADMIT ONE.

A candidate channel - proposed by the entity's own structure, by an operator, or by a local
language model reasoning about whether cereal prices matter to a coastal restaurant trade - is
granted a TRIAL subscription. It survives the next review only if the measured relevance
between that channel and this entity's own published output clears a floor. Relevance is
measured on CHANGES, over a window, with a minimum number of joint observations, and dropping
takes two consecutive failures rather than one.

That hysteresis is not politeness. System 06 learned it the expensive way: a switch that flips
on a single noisy reading spends its life flipping, and the thing it controls never settles.
"""

from __future__ import annotations

from .agents.base import Agent, Intent, Observation
from .bus import Bus, Event
from .state import WorldState

#: Ticks between reviews of the subscription list. Thirty days: long enough to have something
#: to measure, short enough that a structural break shows up within a quarter.
REVIEW_EVERY = 30

#: |correlation of changes| a channel must reach to be worth hearing. 0.15 is low on purpose -
#: the question a subscription answers is "could this matter at all", not "is this the main
#: driver". The policy inside the entity decides how much it matters.
RELEVANCE_MIN = 0.15

#: Consecutive failed reviews before a channel is dropped.
PATIENCE = 2


class Entity(Agent):
    """An agent on the bus. Subclasses override `on_event` and usually `decide`."""

    kind: str = "entity"
    #: Patterns this entity starts life subscribed to.
    listens: tuple[str, ...] = ()
    #: Channels it is the publisher of record for. One publisher per channel, always: two
    #: sources for the same topic and nobody can be held responsible for what it says.
    emits: tuple[str, ...] = ()
    #: The channel whose movement a candidate subscription must explain to earn its place.
    #: Empty means this entity cannot review its own subscriptions and keeps what it was given.
    own_topic: str = ""

    def __init__(self, ident: str, name: str = "", **params) -> None:
        super().__init__(ident, name, **params)
        self.subscribed: list[str] = list(self.listens)
        #: pattern -> consecutive reviews it has failed
        self.failing: dict[str, int] = {}
        #: patterns on trial, and the review tick at which they must have proved themselves
        self.trials: dict[str, int] = {}
        self.outbox: list[Event] = []

    # ------------------------------------------------------------------ wiring
    def wire(self, bus: Bus) -> None:
        bus.subscribe(self.id, *self.subscribed)

    def say(self, topic: str, value: float, why: str = "", **detail) -> Event:
        """Build one outgoing event. The bus decides whether it is material enough to travel."""
        return Event(topic=topic, value=float(value), source=self.id, why=why, detail=detail)

    def on_event(self, ev: Event, w: WorldState) -> list[Event]:
        """One event in, zero or more out. Default: hear nothing, say nothing."""
        return []

    def decide(self, obs: Observation, w: WorldState) -> list[Intent]:
        return []

    # ------------------------------------------------------------------ staying alive
    def describe(self) -> str:
        """One line about what this entity is, for a reader that is not this code."""
        return f"{self.kind}: {self.name}"

    def propose(self, bus: Bus, w: WorldState) -> list[str]:
        """Channels this entity would like to try. Structural by default; see `mind/`.

        Overridden by entities that know something about themselves - a country that has just
        started importing from somewhere proposes that lane. The base version proposes nothing
        unless a local language model is switched on for this entity with `mind=True`, because
        guessing is what the review exists to punish, and a guess with a trial subscription
        attached is the only kind this system accepts.
        """
        if not self.params.get("mind"):
            return []
        from .bus import matches
        from .mind import propose_channels
        candidates = [t for t in bus.topics()
                      if t != self.own_topic
                      and not any(matches(p, t) for p in self.subscribed)]
        out = propose_channels(self.id, self.describe(), candidates)
        if out:
            w.log(self.id, "proposed", channels=", ".join(out),
                  why="a language model suggested these; each gets one month to prove itself")
        return out

    def review(self, bus: Bus, w: WorldState, verbose: bool = False) -> dict:
        """Keep, drop, promote, expire. Called every REVIEW_EVERY ticks by the engine."""
        report = {"who": self.id, "kept": [], "dropped": [], "promoted": [], "expired": []}
        if not self.own_topic:
            return report

        # candidates arrive on trial; a trial that has run its window must now measure up
        for pattern in self.propose(bus, w):
            if pattern not in self.subscribed and pattern not in self.trials:
                self.trials[pattern] = w.tick + REVIEW_EVERY
                self.subscribed.append(pattern)
                bus.subscribe(self.id, pattern)

        for pattern in list(self.subscribed):
            score = self._relevance(bus, pattern)
            on_trial = pattern in self.trials
            if score >= RELEVANCE_MIN:
                self.failing.pop(pattern, None)
                if on_trial and w.tick >= self.trials[pattern]:
                    del self.trials[pattern]
                    report["promoted"].append((pattern, round(score, 3)))
                else:
                    report["kept"].append((pattern, round(score, 3)))
                continue
            # not measurable yet is not the same as measured and useless
            if score == 0.0 and not self._measurable(bus, pattern):
                report["kept"].append((pattern, 0.0))
                continue
            misses = self.failing.get(pattern, 0) + 1
            self.failing[pattern] = misses
            expiring = on_trial and w.tick >= self.trials[pattern]
            if misses >= PATIENCE or expiring:
                self.subscribed.remove(pattern)
                bus.unsubscribe(self.id, pattern)
                self.failing.pop(pattern, None)
                self.trials.pop(pattern, None)
                report["expired" if expiring else "dropped"].append((pattern, round(score, 3)))
        if verbose:
            w.log(self.id, "review", **{k: str(v) for k, v in report.items() if v})
        return report

    # ------------------------------------------------------------------ internals
    def _concrete(self, bus: Bus, pattern: str) -> list[str]:
        from .bus import matches
        return [t for t in bus.series if matches(pattern, t)]

    def _relevance(self, bus: Bus, pattern: str) -> float:
        """The best a pattern's channels can do. A wildcard is kept for its best member."""
        best = 0.0
        for topic in self._concrete(bus, pattern):
            if topic == self.own_topic:
                continue
            best = max(best, abs(bus.relevance(topic, self.own_topic)))
        return best

    def _measurable(self, bus: Bus, pattern: str) -> bool:
        own = bus.diff_series(self.own_topic)
        for topic in self._concrete(bus, pattern):
            if topic != self.own_topic and len(set(bus.diff_series(topic)) & set(own)) >= 20:
                return True
        return False
