# The rules of the game

*What this system is for, what it is allowed to say, what it is made of, and where every
number comes from. One page, kept current. If the code and this document disagree, the code is
wrong — this is the specification.*

---

## 1. The objective

**Forecasts of the world economy at the horizons where inertia is the dominant force.**

| horizon | why this one | what it is judged against |
|---|---|---|
| **7 days** | inventory cover, freight fixtures, the fuel already in the tank | the published outcome |
| **30 days** | pass-through to the pump, contract rolls, one statistical release | the published outcome |
| **90 days** | refinery turnarounds, a central bank meeting, a quarter of trade | the published outcome |
| **365 days** | capital decisions, base effects, a policy cycle | the published outcome |

And, stated with equal force, **what this system will never publish: an intraday forecast.**
The operator set that boundary and it is the right one — *"I don't think we can make intraday
forecasts. They make no sense. We have neither real-time data nor the computing power."* Every
mechanism in here is an inertia measured in weeks: days of cover, a six-week publication lag, a
six-month reference-price half-life, a committee that meets eight times a year. Nothing in it
knows what oil does this afternoon, and a number printed against that horizon would be a lie
told in a confident font.

**The output is never a point.** It is a distribution with a causal chain attached: *"Brent in
sixty days: median 94, 80% interval [71, 168], and the upper tail is Hormuz."* A point forecast
cannot be argued with, and a forecast nobody can argue with cannot be improved.

**The null is a flat line.** A forecast is worth something only when it beats "tomorrow is
today", measured as `rmse_model / rmse_flat`. That ratio squared is `1 − R²`, so 1.00 means
zero variance explained. The scoreboard is in `mwmodel/score.py` and it is run against windows
nobody selected on.

---

## 2. The laws

Three about the world, four about the bus, and three about method. They are not style; each one
exists because its absence broke something that is written down in `docs/PHASE1.md`.

### The world
1. **Conservation.** Money and physical units balance, asserted in the hot path, never logged
   and continued. Creation and destruction are declared explicitly or the tick raises.
2. **Asymmetric information.** Nobody sees the world state. Each player sees its own late,
   partial observation. A central bank reads a six-week-old CPI, and that is why policy is
   always late in this model, as it is in life.
3. **Nothing exogenous that could be endogenous.** Every constant is a placeholder for an agent
   not yet built, and the master plan says which one.

### The bus (`mwmodel/bus.py`)
4. **A cascade may not revisit a topic within one tick.** Oil → freight → inflation → rates →
   demand → oil is a real loop, and it closes through *time*: the return leg lands on the next
   tick. Without this rule the first real cycle explodes and somebody reaches for a damping
   constant, which is an invented number hiding a design error.
5. **A channel carries changes that matter, not a heartbeat.** Below a per-family materiality
   threshold a value is recorded but not delivered.
6. **Delivery is deterministic.** Wave, then topic, then source. Two runs of the same world
   produce the same cascade in the same order, or nothing downstream can be attributed.
7. **Every event carries its causal chain**, which is what lets the viewer answer *why* with a
   path instead of a shrug.

### Method
8. **An entity with no published number to be scored against does not get built.** With enough
   free parameters any history can be reproduced and nothing is explained. This is the rule
   that keeps an agent model from becoming a story.
9. **Point-in-time, always.** A replay standing on 1 March 2022 sees only what had been
   published by then, with each series' own lag applied. Every observation carries `ref_date`
   (what it describes) and `known_at` (when it became knowable).
10. **A model may propose; only the record may admit.** A candidate subscription — from a
    language model, from an operator, from an entity's own structure — gets a *trial*
    subscription and survives only if a relationship is then measured. This applies equally to
    coefficients: a fit that needs a parameter to sit on its bound is refused, because that is
    the search telling you the mechanism is wrong.

---

## 3. The data sources

Everything below is free and keyless unless marked. Observations are **never** committed to the
repository; the registry that describes them is code, and `data/` is gitignored.

### Ingested and in use

| source | what it gives | cadence / lag | used by |
|---|---|---|---|
| **EIA INTL bulk** (`archive/ingest/eia.py`) | production, consumption, crude, imports, exports, stocks — every country, monthly, back to 1980 | monthly, ~70d lag | the entire energy balance; `seed/energy.py` |
| **EIA weekly stocks** (same file) | OECD commercial stocks for 11 reporters | monthly | days-of-cover seeding, the normal-cover baseline |
| **DBnomics / IMF CPI** (`archive/ingest/dbnomics.py`) | monthly CPI, 13 countries | monthly, ~60d lag | CPI targets, calibration |
| **FRED** (37 streams, `archive/streams.py`) | rates, money, credit spreads, FX, equity | daily–monthly | the World Archive; scoring |
| **The chronicle** (`seed/events.py`) | 23 dated energy events with named effects | event | the informed replays |

### Declared, not yet ingested — and the entity that is waiting for them

| needed for | series | where it lives |
|---|---|---|
| refining margins | ICE gasoil vs Brent, RBOB vs WTI, Singapore 10ppm, VLSFO | `entities/refining.py` `targets` |
| freight | Freightos Baltic FBX, Baltic Dry, TD3C tanker | `entities/shipping.py` `targets` |
| gas | TTF, Henry Hub, JKM; pipeline and LNG flows | not yet built |
| trade network | UN Comtrade / IMF DOTS bilateral flows | replaces `shipping.EXPOSURE` |
| CPI baskets | national statistical office weights | replaces `facts.energy_weight` |

**Rule for this table: an entity may be built against a declared target before the series is
ingested, but it must say so in its own module docstring, in capital letters, and the fact that
it is unverified must reach anything that reports its output.**

---

## 4. The mechanism

### What an entity is

Seven things, and the seventh is the gate.

```
identity     who this is, and what it aggregates — segments, never individuals
balance      what it owns, held in WorldState, never a private copy
interests    what it is trying to do, expressed as something scorable
listens      the channels it hears — now, not for ever
emits        the channels it is the publisher of record for (one publisher per channel)
memory       what it carries between ticks
target       the published number it must reproduce, or it does not get built
```

### The tick

```
1 ADVANCE    the clock moves
2 DELIVER    every event whose known_at has arrived reaches the players who can see it
3 PERCEIVE   each player forms its own late, partial view
4 DECIDE     policies emit intentions; nothing is applied yet
5 CLEAR      markets find prices; the network decides what physically moves
6 SETTLE     balances change, both sides at once, CONSERVATION IS ASSERTED
7 CASCADE    what changed is published and travels to whoever is listening
8 RECORD     the state and the reason for every decision are written down
```

Steps 3–4 are separate from 5–6 so that agents propose and the world disposes: a player that
could write to the world directly would make a bug indistinguishable from a decision, and the
whole value of this architecture is being able to ask **which player was wrong**.

Step 7 is where the model gets wide. Adding an industry means adding an entity and its
channels — never editing the loop.

### The channels, today

| topic | publisher | who listens | unit |
|---|---|---|---|
| `price.crude` | the crude market | the refiner | USD/bbl |
| `price.fuel.{diesel,gasoline,jet,bunker}` | `refiner.global` | every country | USD/bbl |
| `price.bunker.tonne` | `refiner.global` | all three carrier segments | USD/t |
| `price.freight.<lane>` | the carrier that serves the lane | the countries exposed to it | index |
| `valve.<chokepoint>` | the world | carriers on lanes through it | open fraction |
| `macro.cpi.<ISO>` | that country | its central bank (four of them, for the ECB) | yoy |
| `policy.rate.<bank>` | that central bank | **nobody yet** — phase 3's investors | rate |

The worked example the operator asked for, running today: **Bab el-Mandeb closes → the tanker
and container segments lose 12 days on the Asia–Europe lane → a third of that lane's capacity
disappears → rates triple → Germany's inflation gains 0.38pp over three months and the United
States gains 0.003pp, because American goods do not travel on that lane.** Nothing in the code
says "Red Sea affects Europe". It falls out of who was subscribed to what.

### Staying alive

Every 30 ticks each entity reviews its own subscriptions. A channel is kept if the correlation
of *changes* between it and that entity's own published output clears 0.15 over the window; it
is dropped after two consecutive failures (hysteresis, because a switch that flips on one noisy
reading spends its life flipping). Candidates proposed by the local language model — `mind/`,
Qwen over Ollama, entirely optional and off by default — enter on a one-month trial and are
expired automatically if nothing is measured.

### The correction loop

Simulate → capture the real data → compare → **attribute** → correct. Attribution is the reason
for the whole agent architecture: the residual has an address. Today it says *"quantities are
right to within 1.6%; the error is in the clearing"*, which is a different instruction from
"the model is 12% off".

---

## 5. What is not built yet

In order, and each one is a phase gate rather than a wish:

1. **Gas.** TTF, Henry Hub, JKM, and the pipeline-versus-LNG decision that decides European
   industrial costs. The single largest hole for a European inflation forecast.
2. **The trade network.** Who actually ships what to whom, replacing the regional exposure
   table — the operator's *"we could know who supplies gas to whom, how many aircraft are being
   built, the price of petrol in each country"*.
3. **The financial layer.** A forward curve, positioning, market makers, investor cohorts by
   size band. The phase-1 calibration identified this as the binding constraint: the model's
   price is too smooth because physical cover is the only thing that can move it.
4. **Real CPI baskets** per country, replacing a single energy weight.
5. **Freight and refining settlement**, so those sectors have balance sheets rather than only
   prices.
6. **The hourly cadence**, running unattended, with the compare-and-correct loop closing every
   day without a human in it.

---

*Companion documents: [`MASTER-PLAN.md`](MASTER-PLAN.md) for the five-year shape and the phase
gates; [`PHASE1.md`](PHASE1.md) for what has actually been measured and what was refused.*
