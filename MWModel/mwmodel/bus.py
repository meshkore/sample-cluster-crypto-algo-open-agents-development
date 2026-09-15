"""THE BUS - how one number changing reaches everything that cares, and nothing else.

The operator's architecture, stated once: *"an event-driven system. Imagine you are a shipping
company with a thousand ships. When the price of oil rises we publish an event: fuel is a
dollar dearer. The ship is subscribed to the fuel channel, so it hears it, and its own model
says: fuel went up, I raise my freight rates. And it publishes to the freight channel of the
lanes it serves. Everyone who consumes those lanes hears that, and inflation hears it too."*

That is the whole mechanism. It replaces the thing every macro model does badly - a single
simultaneous system of equations solved all at once - with something closer to how the world
actually transmits information: **late, partially, along named channels, to whoever happens to
be listening.** A country that stops importing cars stops listening to the car channel, and
from that moment the shock genuinely does not reach it. In a matrix of elasticities it always
would.

FOUR LAWS OF THE BUS, and each one exists because the naive version breaks

1.  A CASCADE MAY NOT REVISIT A TOPIC WITHIN ONE TICK.
    Oil raises freight, freight raises inflation, inflation raises rates, rates cut demand,
    and demand moves oil. That loop is real and it is most of what the model is for - but it
    does not happen at one instant. Feedback closes through TIME: the return leg lands on the
    next tick. Without this rule the first real cycle either explodes or hangs, and the
    modeller reaches for a damping constant, which is an invented number hiding a design
    error.

2.  A CHANNEL CARRIES CHANGES THAT MATTER, NOT A HEARTBEAT.
    Everything moves a little every tick. If every movement is an event, every entity wakes
    for every tick and the subscription graph means nothing. Each topic family has a
    materiality threshold and a value that fails it is recorded but not delivered.

3.  DELIVERY IS DETERMINISTIC.
    Waves, then topic, then source. Two runs of the same world produce the same cascade in the
    same order, or nothing downstream can be attributed or replayed.

4.  EVERY EVENT CARRIES ITS CAUSAL CHAIN.
    An event knows which topics it descends from. That is what lets the viewer answer "why did
    Turkish inflation move" with a path rather than a shrug, and it is what makes the loop
    guard in law 1 a one-line check instead of a graph search.

WHAT A TOPIC LOOKS LIKE
Dotted, hierarchical, and specific enough to unsubscribe from: `price.crude`,
`price.freight.asia_europe`, `macro.cpi.TUR`, `valve.hormuz`, `capacity.SAU`,
`trade.exports.CHN.vehicles`. Patterns use `*` for one segment and `**` for the rest, so a
carrier can listen to `price.fuel.*` and a central bank to `macro.cpi.**`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

#: How many times an event may cascade within one tick before the bus stops it. Six is not a
#: tuning parameter - it is a statement that a chain longer than six links inside a single day
#: is almost certainly a loop the guard in law 1 failed to catch, and the model should say so
#: loudly rather than keep going.
MAX_WAVES = 6

#: Ticks of each channel's history kept for the relevance measurement in `entity.review`.
HISTORY = 500

#: Law 2. Relative change below which a publication is recorded but not delivered. Macro
#: series get a finer threshold than prices because a tenth of a point of CPI is news and a
#: tenth of a percent on crude is not.
MATERIALITY: tuple[tuple[str, float], ...] = (
    ("macro.", 0.0005),
    ("policy.", 0.0002),
    ("price.", 0.0020),
    ("capacity.", 0.0050),
    ("flow.", 0.0100),
    ("valve.", 0.0100),
    ("", 0.0010),
)


def threshold(topic: str) -> float:
    for prefix, value in MATERIALITY:
        if topic.startswith(prefix):
            return value
    return 0.001


def matches(pattern: str, topic: str) -> bool:
    """`price.*` matches `price.crude`; `macro.cpi.**` matches `macro.cpi.TUR.energy`."""
    p, t = pattern.split("."), topic.split(".")
    for i, seg in enumerate(p):
        if seg == "**":
            return True
        if i >= len(t):
            return False
        if seg != "*" and seg != t[i]:
            return False
    return len(p) == len(t)


@dataclass(frozen=True)
class Event:
    """One thing that changed, addressed to a channel rather than to a recipient.

    Frozen on purpose. An event a listener can edit is a shared mutable variable wearing a
    costume, and the first time two listeners disagree about it the model stops being
    replayable.
    """

    topic: str
    value: float
    day: str = ""
    unit: str = ""
    source: str = ""
    why: str = ""
    detail: dict = field(default_factory=dict)
    #: The topics this event descends from, oldest first. Law 4.
    chain: tuple[str, ...] = ()
    wave: int = 0

    @property
    def root(self) -> str:
        return self.chain[0] if self.chain else self.topic


class Bus:
    """Subscriptions, publication, and one tick's cascade."""

    def __init__(self) -> None:
        #: entity id -> the patterns it currently listens to. Mutable at runtime BY DESIGN:
        #: an entity that stops trading a thing stops hearing about it.
        self.subs: dict[str, list[str]] = {}
        #: last delivered value per topic, which is what materiality is measured against
        self.last: dict[str, float] = {}
        #: (tick, value) per topic, for measuring whether a subscription earns its place
        self.series: dict[str, list[tuple[int, float]]] = {}
        self.pending: list[Event] = []
        #: this tick only - the viewer's cascade tree and the attribution step read these
        self.trace: list[dict] = []
        self.dropped: list[dict] = []
        self.suppressed: int = 0

        # ---------------------------------------------------------------- the meters
        # CUMULATIVE, never reset. A per-tick view tells you what just happened; a counter
        # tells you whether a channel is alive at all, and the difference between a channel
        # that fires twice a year and one that has never fired once is the single most
        # useful thing to know about a network this size. Kept here rather than computed in
        # the viewer, so the numbers on the screen and the numbers in a test are the same.
        self.chan: dict[str, dict] = {}              # topic -> counters
        self.who: dict[str, dict] = {}               # entity -> said / heard / replied
        self.flow: dict[tuple[str, str], int] = {}   # (publisher, listener) -> messages
        self.per_tick: list[tuple[int, int]] = []    # (tick, delivered), for the sparkline
        self.total_published = 0
        self.total_delivered = 0
        self.total_suppressed = 0

    # ------------------------------------------------------------------ subscription
    def subscribe(self, who: str, *patterns: str) -> None:
        cur = self.subs.setdefault(who, [])
        for p in patterns:
            if p and p not in cur:
                cur.append(p)

    def unsubscribe(self, who: str, *patterns: str) -> None:
        cur = self.subs.get(who, [])
        for p in patterns:
            if p in cur:
                cur.remove(p)

    def listeners(self, topic: str) -> list[str]:
        return sorted(who for who, pats in self.subs.items()
                      if any(matches(p, topic) for p in pats))

    def topics(self) -> list[str]:
        return sorted(self.series)

    def read(self, topic: str, default: float = 0.0) -> float:
        return self.last.get(topic, default)

    # ------------------------------------------------------------------ publication
    def record(self, topic: str, value: float, tick: int) -> None:
        """Keep the number whether or not anyone hears it. Law 2 hides events, not history."""
        s = self.series.setdefault(topic, [])
        s.append((tick, float(value)))
        if len(s) > HISTORY:
            del s[: len(s) - HISTORY]

    def meter(self, topic: str) -> dict:
        return self.chan.setdefault(topic, {
            "topic": topic, "published": 0, "delivered": 0, "suppressed": 0,
            "source": "", "value": 0.0, "unit": "", "last_tick": 0, "first_tick": None,
            "why": ""})

    def meter_who(self, who: str) -> dict:
        return self.who.setdefault(who, {"who": who, "said": 0, "heard": 0, "replied": 0,
                                         "last_tick": 0})

    def publish(self, ev: Event, tick: int = 0) -> bool:
        """Offer an event to the bus. Returns whether it was material enough to travel."""
        self.record(ev.topic, ev.value, tick)
        m = self.meter(ev.topic)
        m["value"] = ev.value
        m["source"] = ev.source or m["source"]
        m["unit"] = ev.unit or m["unit"]
        m["why"] = ev.why or m["why"]
        m["last_tick"] = tick
        prev = self.last.get(ev.topic)
        if prev is not None:
            scale = max(abs(prev), 1e-9)
            if abs(ev.value - prev) / scale < threshold(ev.topic):
                self.suppressed += 1
                self.total_suppressed += 1
                m["suppressed"] += 1
                return False
        if m["first_tick"] is None:
            m["first_tick"] = tick
        m["published"] += 1
        self.total_published += 1
        if ev.source:
            spoke = self.meter_who(ev.source)
            spoke["said"] += 1
            spoke["last_tick"] = tick
        self.last[ev.topic] = ev.value
        self.pending.append(ev)
        return True

    def say(self, topic: str, value: float, source: str, **kw) -> Event:
        return Event(topic=topic, value=float(value), source=source, **kw)

    # ------------------------------------------------------------------ the cascade
    def begin(self) -> None:
        self.trace.clear()
        self.dropped.clear()
        self.suppressed = 0

    def drain(self, w, entities: list) -> int:
        """Run the cascade to exhaustion, under laws 1 and 3. Returns events delivered."""
        by_id = {getattr(e, "id", ""): e for e in entities}
        delivered = 0
        for _ in range(MAX_WAVES):
            batch, self.pending = self.pending, []
            if not batch:
                break
            batch.sort(key=lambda e: (e.topic, e.source))
            for ev in batch:
                heard = self.listeners(ev.topic)
                self.trace.append({"topic": ev.topic, "value": ev.value, "source": ev.source,
                                   "wave": ev.wave, "chain": list(ev.chain),
                                   "why": ev.why, "heard_by": len(heard)})
                self.meter(ev.topic)["delivered"] += len(
                    [h for h in heard if h != ev.source])
                for who in heard:
                    ent = by_id.get(who)
                    if ent is None or who == ev.source:
                        continue
                    listener = self.meter_who(who)
                    listener["heard"] += 1
                    listener["last_tick"] = w.tick
                    self.total_delivered += 1
                    key = (ev.source or "__world", who)
                    self.flow[key] = self.flow.get(key, 0) + 1
                    said_before = listener["said"]
                    for out in ent.on_event(ev, w) or []:
                        # LAW 1. The return leg of a loop lands on the next tick, not this one.
                        if out.topic == ev.topic or out.topic in ev.chain:
                            self.dropped.append({"topic": out.topic, "by": who,
                                                 "reason": "a cascade may not revisit a topic "
                                                           "within one tick",
                                                 "chain": list(ev.chain) + [ev.topic]})
                            continue
                        self.publish(replace(out, chain=ev.chain + (ev.topic,),
                                             wave=ev.wave + 1, day=w.day), tick=w.tick)
                    if listener["said"] > said_before:
                        listener["replied"] += 1
                    delivered += 1
        self.per_tick.append((w.tick, delivered))
        del self.per_tick[:-180]
        if self.pending:
            for ev in self.pending:
                self.dropped.append({"topic": ev.topic, "by": ev.source,
                                     "reason": f"cascade still running after {MAX_WAVES} waves",
                                     "chain": list(ev.chain)})
            self.pending.clear()
        return delivered

    # ------------------------------------------------------------------ measurement
    def diff_series(self, topic: str) -> dict[int, float]:
        """Tick -> change since the previous recorded value.

        CHANGES, not levels. Two series that both drift upward correlate at 0.9 and share no
        mechanism whatsoever; that is the oldest way to talk yourself into a relationship that
        is not there, and this laboratory has paid for it before.
        """
        s = self.series.get(topic, [])
        out: dict[int, float] = {}
        for (t0, v0), (t1, v1) in zip(s, s[1:]):
            out[t1] = (v1 - v0) / max(abs(v0), 1e-9)
        return out

    def relevance(self, topic_a: str, topic_b: str, min_points: int = 20) -> float:
        """Correlation of changes on the ticks both channels moved. 0.0 when not measurable."""
        a, b = self.diff_series(topic_a), self.diff_series(topic_b)
        ticks = sorted(set(a) & set(b))
        if len(ticks) < min_points:
            return 0.0
        xs = [a[t] for t in ticks]
        ys = [b[t] for t in ticks]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        sxx = sum((x - mx) ** 2 for x in xs)
        syy = sum((y - my) ** 2 for y in ys)
        if sxx <= 0 or syy <= 0:
            return 0.0
        return sxy / (sxx ** 0.5 * syy ** 0.5)

    def summary(self) -> dict:
        return {"topics": len(self.series), "subscribers": len(self.subs),
                "edges": sum(len(p) for p in self.subs.values()),
                "delivered": len(self.trace), "suppressed": self.suppressed,
                "dropped": len(self.dropped),
                "total_published": self.total_published,
                "total_delivered": self.total_delivered,
                "total_suppressed": self.total_suppressed,
                "silent": sum(1 for m in self.chan.values() if m["published"] <= 1)}

    def channels(self) -> list[dict]:
        """Every channel with its meters and its current audience. The traffic column."""
        out = []
        for topic, m in self.chan.items():
            row = dict(m)
            row["listeners"] = len([x for x in self.listeners(topic) if x != m["source"]])
            row["family"] = topic.split(".", 1)[0]
            out.append(row)
        # Sorted by what actually TRAVELLED, not by what was said. A channel published a
        # hundred times with nobody subscribed is not busy, it is shouting into a room.
        out.sort(key=lambda r: (-r["delivered"], -r["published"], r["topic"]))
        return out

    def talkers(self) -> list[dict]:
        """Every entity with what it said, what it heard, and how often it answered back."""
        out = []
        for who, m in self.who.items():
            row = dict(m)
            row["subscriptions"] = len(self.subs.get(who, []))
            row["patterns"] = list(self.subs.get(who, []))
            out.append(row)
        out.sort(key=lambda r: (-(r["said"] + r["heard"]), r["who"]))
        return out

    def links(self, top: int = 40) -> list[dict]:
        """Who has actually spoken to whom, and how often. The wiring, measured."""
        rows = [{"frm": a, "to": b, "n": n} for (a, b), n in self.flow.items()]
        rows.sort(key=lambda r: -r["n"])
        return rows[:top]
