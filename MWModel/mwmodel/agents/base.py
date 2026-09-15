"""WHAT AN AGENT IS - the same seven things, whatever kind of player it represents.

The operator's architecture, stated once: *"en realidad yo creo que esto funcionaría mejor si
tuviera un modelo que simula a los market makers, otro modelo que simula a los particulares...
agentes independientes con sus propios intereses, su propia memoria, sus propias herramientas,
su propia forma de pensar. Y los colocáramos todos a jugar a la vez."*

So there is one interface and many implementations, and the interface is what makes the
attribution step possible: every action carries the agent that took it and the reason it gave,
so when the world diverges from reality we can ask WHICH PLAYER was wrong instead of shrugging
at a single number. That question could not be asked of system 09, and not being able to ask
it is why system 09 stopped improving.

    identity     who this is, and what it aggregates
    balance      what it owns, held in WorldState (never a private copy)
    interests    what it is trying to do, as something it can be scored on
    observe()    what it can see - LATE and PARTIAL, never the world state itself
    decide()     observation + memory + interest -> intentions
    memory       what it carries between ticks; a cohort burnt in 2022 is a different cohort
    target       the published number it must reproduce, or it does not get built

THE LAST ONE IS THE GATE. An agent with no observable to be scored against is a story, and
stories are precisely how agent-based macro models earn their bad reputation: with enough free
parameters any history can be reproduced, so nothing is explained. If nothing published can
tell us whether this player behaved correctly, it does not belong in the roster yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..state import WorldState


@dataclass
class Intent:
    """One thing an agent wants to do this tick. Never applied by the agent itself.

    Agents propose; the engine disposes. A market decides whether an order fills and at what
    price; the network decides whether a shipment can move. That separation is what keeps a
    bug distinguishable from a decision.
    """

    who: str
    kind: str                     # "buy" | "sell" | "produce" | "consume" | "set" | "ship"
    what: str                     # a market key, a variable name, an edge key
    qty: float = 0.0
    limit: float | None = None    # the worst price this agent will accept
    why: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class Observation:
    """What one agent can see right now - deliberately not the world.

    LAW 2, ASYMMETRIC INFORMATION. A retail cohort sees a price on a screen. A central bank
    sees a statistical release that is six weeks old. An exporting state sees its own loadings
    today and its rival's next month. A model where everyone sees everything has no trade in
    it at all, because trade requires disagreement about what things are worth.
    """

    day: str
    prices: dict[str, float]
    news: list[dict]
    own: dict[str, float]
    world: dict[str, float]       # the few aggregates this agent is entitled to know


class Agent:
    """The base class. Subclasses override `observe` and `decide` and nothing else."""

    #: What kind of player this is; the viewer groups by it.
    kind: str = "agent"
    #: The published series this agent must reproduce. Empty means NOT READY TO BUILD.
    targets: tuple[str, ...] = ()

    def __init__(self, ident: str, name: str = "", **params) -> None:
        self.id = ident
        self.name = name or ident
        self.params = params
        #: Private, persistent, and part of what makes two agents with the same balance
        #: behave differently. Scored and fine-tuned per agent, never globally.
        self.memory: dict[str, float] = {}

    # ------------------------------------------------------------------ the interface
    def observe(self, w: WorldState, news: list[dict]) -> Observation:
        """Default: prices, this agent's own variables, and whatever news reached it.

        Subclasses narrow this. Nothing here may read another agent's balance - if a player
        needs to know something about another player, that is either public data or an
        explicit intelligence channel, and either way it is modelled rather than assumed.
        """
        return Observation(day=w.day,
                           prices={k: m.price for k, m in w.markets.items()},
                           news=news,
                           own=dict(w.vars.get(self.id, {})),
                           world={})

    def decide(self, obs: Observation, w: WorldState) -> list[Intent]:
        raise NotImplementedError(f"{type(self).__name__} has no policy")

    # ------------------------------------------------------------------ scoring
    def score(self, w: WorldState, actual: dict[str, float]) -> dict[str, float]:
        """How wrong this agent was, per target. Attribution reads this; fine-tuning uses it.

        Returned as a mapping rather than a single number on purpose: an agent can be right
        about how much it produced and wrong about what it charged, and collapsing that into
        one figure is how the information needed to correct it gets thrown away.
        """
        out = {}
        for t in self.targets:
            if t in actual and t in w.vars.get(self.id, {}):
                got, want = w.var(self.id, t), actual[t]
                out[t] = (got - want) / (abs(want) if want else 1.0)
        return out

    def __repr__(self) -> str:
        return f"<{self.kind} {self.id}>"
