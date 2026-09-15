# MWModel — the master plan

*A model of the world economy built out of agents that each pursue their own interest, fed
daily with what actually happened, and corrected against it forever.*

---

## 0. The question that defines the system

> *"Si te pregunto cómo estará la inflación dentro de 60 días, ¿sabrías responder? ¿Sabe el
> modelo que hoy el estrecho de Ormuz y el de Bab el-Mandeb están ocupados y que por tanto se
> está dificultando el paso de petróleo?"*

Today the honest answer is no, and the reason is worth stating precisely because it is the
specification for everything below. The archive knows that Brent rose. It does not know
**why**, so it cannot know **what happens next**. To answer the question, a system has to hold
a chain:

```
  a chokepoint's capacity falls
      -> tankers reroute (Cape of Good Hope: +10-14 days, +freight, +insurance)
          -> floating inventory rises, delivered crude costs more
              -> refiners pass through to diesel and jet, with a lag and a margin
                  -> the energy component of each country's CPI basket moves,
                     by a DIFFERENT amount in each country (basket weight, taxes,
                     subsidies, currency)
                      -> headline CPI prints 40-60 days later
                          -> central banks react, and the reaction differs by mandate
                              -> rates, currencies, and every asset priced off them move
```

Eight links. Every one of them is measurable, every one has been studied, and every one can be
a small, replaceable model with its own error bar. **The system's job is not to be an oracle.
It is to hold the chain and propagate uncertainty along it.**

And then the part the operator is most right about:

> *"Nada es eterno, nada se queda en su posición actual. Todo el mundo lucha por sus propios
> intereses, de tal manera que las cosas se mueven. Irán y Estados Unidos pueden llegar a un
> acuerdo... o se puede escalar el conflicto."*

A chokepoint is not a constant. It is the current state of a negotiation between agents who
each have something to gain. So the top of the chain is not an assumption — it is **another
agent interaction**, with its own incentives, its own hazard of changing, and its own
probability distribution over the next sixty days. That is why this is an agent model and not
a set of equations.

---

## 1. The thesis

One model that understands everything is the hard road. It needs a single training signal for
a system with no single objective, it cannot explain itself, and when it is wrong nobody can
say which part was wrong.

**Many models, each simulating one player, interacting in one shared world, is the easier road
and the more truthful one.** Each agent is small enough to be calibrated against something
real; each has its own interest, its own information, its own memory, its own tools; and when
the world does something unexpected, the divergence can be attributed to a *specific* agent
whose behaviour was mis-specified. That is the property that makes improvement possible at
all — and it is exactly what system 09 lacked, where a single number went wrong and nothing
could say which of fourteen assumptions caused it.

Three laws follow, and they are not negotiable:

**Law 1 — Conservation.** Money and physical units balance. Every purchase is someone's sale;
every barrel delivered left somewhere; every dollar of deficit is someone's surplus. System 09
proved this is the one discipline that keeps a simulation honest: its ledger asserted
conservation in the hot path to 1e-14, and that assertion caught more errors than every test
suite around it.

**Law 2 — Asymmetric information.** No agent sees the world state. Each sees its own
observation of it — late, partial, and biased. A model where everyone knows everything has no
trade in it, because trade requires disagreement.

**Law 3 — Nothing is exogenous that could be endogenous.** A chokepoint is a negotiation. An
interest rate is a central bank's decision. An oil price is a clearing. Every constant in this
system is a placeholder for an agent we have not built yet, and the plan says so out loud.

---

## 2. What a player is

Segments, not individuals — the operator's instruction and the only tractable choice:

> *"Lo que queremos es segmentos. Por ejemplo, todas las empresas de inteligencia artificial
> van a tener un modelo y un player que va a agrupar todo el dinero que manejan. Los fondos de
> inversión americanos, igual. Puedes separar BlackRock... pero luego todos los demás los
> puedes meter en un grupo o en varios dependiendo de los tamaños."*

Every agent, whatever its kind, is the same seven things:

| | what it is | example |
|---|---|---|
| **identity** | who it is, and what it is an aggregate of | `country.IRN`, `sector.ai_capex`, `firm.BLACKROCK`, `cohort.crypto.whale.100m` |
| **balance** | what it owns and owes, in money and in units | reserves, debt, barrels, tonnes, chips, coins |
| **interests** | what it is trying to do, as an objective it can be scored against | a state maximising revenue and security; a fund maximising risk-adjusted return; a household smoothing consumption |
| **observation** | what it can see, and how late | a retail cohort sees the price; a central bank sees the CPI release; an exporting state sees its own loadings today and its rival's next month |
| **memory** | what it remembers, and how much it forgets | a cohort burnt in 2022 behaves differently in 2025 — and that is a state variable, not a story |
| **policy** | how it turns observation + memory + interest into an action | a rule, an econometric response function, a learned policy, or a reasoning model — per agent, chosen by what the data supports |
| **calibration target** | the published number it must reproduce | OPEC production, a CPI print, ETF flows, an exchange reserve |

The last row is what stops this becoming a fantasy. **An agent with no observable to be scored
against does not get built.** If nothing published can tell us whether it behaved correctly,
it is a story, and stories are exactly how agent-based macro models have historically failed:
they can be made to fit anything, so they explain nothing.

### The roster, by kind

- **States** (~40 individually, rest by bloc). GDP, population, CPI basket, energy balance,
  fiscal position, reserves, trade. They *decide*: buy gas from the US or Russia or Algeria,
  subsidise fuel or not, raise tariffs, release strategic reserves, escalate or negotiate.
- **Central banks** (~12). A mandate, a reaction function, a balance sheet.
- **Producing sectors** (energy, refining, shipping, mining, agriculture, semiconductors,
  aerospace, AI capex). Capacity, utilisation, lead times, inventories.
- **Firms**, only where one firm is large enough that averaging it away loses information:
  Saudi Aramco, BlackRock, TSMC, the largest miners. A handful, by design.
- **Investor cohorts**, banded by size — the operator's point that a $100M whale and a $2M
  whale are different animals. Pension funds, sovereign funds, hedge funds, retail by wealth
  band, and crypto's own cohorts inherited from system 09, which is where they always belonged.
- **Market makers**, who hold inventory, quote both sides, and withdraw when risk rises. They
  are why prices gap rather than glide, and no model without them can produce a crash.
- **Households**, by country × income band. Consumption, energy share of spending, savings.

### The interaction graph is the point

If eight agents buy oil, they will compete for it. If a country's growth outlook falls, it
buys less, and its supplier's revenue falls, and that supplier's fiscal position tightens, and
its willingness to escalate a conflict changes. **Those consequences are not scripted — they
fall out of agents each doing the obvious thing.** That is the whole reason to build it this
way.

---

## 3. How a step works

The world advances in **ticks**. One hour is the target cadence; the engine is
cadence-agnostic and will run daily first because most data arrives daily.

```
  1  ADVANCE THE CLOCK        t -> t+1
  2  DELIVER THE NEWS         every event whose known_at <= t, to the agents who can see it
  3  PERCEIVE                 each agent updates its own view of the world (late, partial)
  4  DECIDE                   each agent's policy emits intentions: orders, shipments,
                              policy changes, negotiations
  5  CLEAR                    markets match supply and demand and produce prices;
                              the network moves physical units under capacity constraints
  6  SETTLE                   balances update; CONSERVATION IS ASSERTED, and a violation
                              stops the tick rather than being logged
  7  RECORD                   the full state is written, with the reason for every decision
```

Then, once per real day:

```
  8  COMPARE                  simulated observables vs what the archive actually recorded
  9  ATTRIBUTE                which agent's behaviour caused the divergence
 10  CORRECT                  adjust that agent's parameters - the fine-tuning, per agent,
                              never as one global fudge factor
```

Step 9 is the one that makes the system improve rather than merely run, and it is only
possible because the agents are separate. A monolith that is wrong is just wrong.

---

## 4. Projection: the part that matters

> *"El estado actual, al final, ya lo sabemos. Lo que queremos saber es qué pasará en una
> semana, en un mes."*

A projection is the same tick loop run forward with **no new data**, many times, with the
uncertain things sampled:

- **Scenario hazards.** Hormuz has states — open, harassed, closed — and a per-tick
  probability of moving between them that is itself a function of the agents' incentives.
  Sanctions relief raises the probability of de-escalation; a strike on a refinery lowers it.
- **Parameter uncertainty.** Every calibrated coefficient carries its posterior, not its
  point estimate.
- **Shock draws.** The residuals the model cannot explain are resampled from their own history
  rather than assumed away.

The output is never a number. It is a **distribution with a causal chain attached**: *"CPI in
the euro area, 60 days out: median +0.31pp above the current path, 80% interval [+0.05,
+0.94]; 62% of that comes from the diesel channel; the interval is wide because Hormuz has a
23% chance of closing further and a 31% chance of reopening."* That is an answer a person can
act on and argue with — which a point forecast never is.

---

## 5. Where this goes wrong, and the defences

Agent-based macro models have a bad reputation, and it is earned. Three failures, and what
this design does about each:

**They can fit anything.** With hundreds of free parameters, any history can be reproduced.
→ *Defence:* every agent has a published calibration target and is scored **out of sample**,
on periods it was not fitted on. An agent that cannot beat a naive rule on held-out data gets
its policy simplified until it can. The bar this laboratory already learned the hard way: a
result is a measurement procedure, and selection optimism is the default outcome.

**They explain the past and predict nothing.** → *Defence:* the daily comparison in step 8 is
a live, permanent forward test. Every projection is recorded with a timestamp and scored when
its horizon arrives. The scoreboard is public inside the system and cannot be edited.

**They become impossible to reason about.** → *Defence:* every decision is recorded with its
reason. The viewer can answer "why did this agent do that" for any agent at any tick, and
"what would have happened if it had not" by rerunning from that tick.

And one more, specific to this laboratory: **the temptation to tune against the answer we
want.** The rule that has cost us four sealed windows stands here too — the evaluation period
is never a selection input.

---

## 6. Phases

Ambition is five years. The first useful thing runs this week. Each phase ends with something
that can be shown on a screen and scored.

### Phase 0 — the world turns (days)
The skeleton, end to end and deliberately crude: world state, tick engine, conservation
assertion, three markets (crude, natural gas, a dollar index), ~25 agents, a physical network
with the six chokepoints that matter, the archive wired in as the source of truth, and a
viewer showing the current state and a 30-day projection fan.
*Done when:* the world runs a hundred ticks without violating conservation, and the viewer
shows a projection that moves when a chokepoint is closed by hand.

### Phase 1 — the energy chain, properly (weeks)
Real production, consumption, refining, shipping and inventories by country. Freight and
insurance as functions of route and risk. Products — diesel, jet, gasoline — because that is
where the inflation channel actually runs.
*Done when:* replaying 2022 with only the events known at each date reproduces the diesel
crack and the TTF spike within a stated error band, out of sample.

### Phase 2 — the inflation chain (months)
CPI baskets by country with real weights, energy pass-through with measured lags, food, rent
and services inertia, wage-setting, and central bank reaction functions with real mandates.
*Done when:* the system answers **"inflation in 60 days"** for the ten largest economies with
a calibrated interval, and beats a random-walk-with-drift benchmark out of sample.

### Phase 3 — the financial layer (months)
Rates, curves, FX, credit, equities. Investor cohorts by size band, market makers with
inventory and withdrawal behaviour. Crypto returns here as one more asset class with its own
cohorts — inherited from system 09, where they were built, and now sitting in a world that can
explain the flows into them.
*Done when:* an energy shock propagates to rates to currencies to risk assets without any
hand-wired link, and the sign and rough size match history.

### Phase 4 — the full trade network (year 1-2)
Who supplies whom, across goods: chips, grain, metals, fertiliser, manufactured goods,
aircraft. Lead times, order books, substitution.
*Done when:* the model answers "who is exposed to whom" for any pair of countries and any
good, and a sanction produces plausible re-routing rather than a hole.

### Phase 5 — agents that reason (year 2-3)
Where data supports it, rule-based policies are replaced by learned ones. The strategic layer
— states negotiating, escalating, conceding — becomes reasoning agents with memory and tools,
because that layer has too few observations to fit statistically and too much structure to
ignore. Per-agent fine-tuning from the daily comparison becomes continuous.

### Phase 6 — the counterfactual engine (year 3+)
Any question of the form *"what if X"* answered as a distribution with attribution: what
changes, through which channel, by how much, and how sure are we.

---

## 7. What is already here on day one

The archive built over the previous days moves in as MWModel's data layer, unchanged in
behaviour:

- **85 streams, 345,261 observations, back to 1947**, each carrying the date it describes
  *and* the date it became knowable.
- The clock — no value can be read before it was publishable, enforced rather than
  conventional.
- A chronicle of dated events with jurisdiction, entities and weight.
- The measured record of what is and is not available for free, including the five defects
  building it exposed (`mwmodel/archive/docs/FINDINGS.md`).

What is missing and is the first ingest queue: energy physical data (production, consumption,
stocks, refinery runs, tanker routes), trade matrices, CPI basket weights, fiscal accounts,
and a live news feed. Every one of those has a free source; the plan names them as they land.

---

## 8. The viewer

> *"El visor es muy importante, porque es la parte bonita de esta historia."*

Three screens, and the third is the reason the other two exist.

1. **The world as it is.** A map carrying flows as weighted edges — crude, gas, LNG, grain,
   capital — with the chokepoints drawn as valves that are open, narrowed or shut. Prices,
   inventories and policy rates in the margins. Click any agent to open its balance sheet,
   its interests, and what it can currently see.
2. **The world as it moves.** The event feed on a timeline, each event marked with which
   agents received it and what they did about it. Scrub backwards; the state follows.
3. **The world as it will be.** Fan charts for every headline variable — CPI by country,
   Brent, TTF, policy rates, the dollar — with the scenario probabilities that generate them
   shown alongside, and a **why** panel that traces the dominant channel of any projection
   back through the chain to the event that started it. Beside every projection, its own
   scorecard: what this system predicted last month, and what actually happened.

---

*Plan written 2026-09-15. Revised whenever a phase closes; the phase gates are the contract.*
