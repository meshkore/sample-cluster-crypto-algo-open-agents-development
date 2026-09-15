# The event architecture, and the first thing it was measured against

*2026-09-15. Written the same day as the phase-1 calibration was refused, because the refusal
named the next mechanism and this is it.*

## What changed

The model stopped being a system of equations and became **a network of publishers and
listeners**. Nothing is wired country by country any more. A price changes, it is published to
a named channel, and whoever is subscribed hears it and republishes what they decided.

```
price.crude  →  refiner.global  →  price.fuel.{diesel,gasoline,jet,bunker}
                                   price.bunker.tonne
                                        ↓
                              carrier.{container,tanker,bulk}
                                        ↓
                              price.freight.<lane>
                                        ↓
                    the countries whose goods travel on that lane — and nobody else
                                        ↓
                              macro.cpi.<ISO>  →  that country's central bank
```

Five new modules: [`bus.py`](../mwmodel/bus.py) (channels, materiality, the cascade),
[`entity.py`](../mwmodel/entity.py) (an agent that listens, speaks and reviews its own
subscriptions), [`entities/refining.py`](../mwmodel/entities/refining.py),
[`entities/shipping.py`](../mwmodel/entities/shipping.py), and
[`mind/`](../mwmodel/mind/__init__.py) (a local language model that may propose a subscription
and may never decide anything). The rules are written down once, in
[`RULES-OF-THE-GAME.md`](RULES-OF-THE-GAME.md).

**The products layer arrived with it**, which is what phase 1 said was next. The inflation chain
no longer jumps from crude to the pump: it runs through diesel, petrol and their crack spreads,
and it has a second channel — what it costs to bring the goods in.

## The four laws of the bus, and why each one exists

1. **A cascade may not revisit a topic within one tick.** Oil → freight → inflation → rates →
   demand → oil is real, and it closes through *time*: the return leg lands on the next tick.
   Without this the first genuine cycle explodes and somebody reaches for a damping constant,
   which is an invented number hiding a design error.
2. **A channel carries changes that matter, not a heartbeat.** Below a materiality threshold a
   value is recorded but not delivered, or every entity wakes for every tick and the
   subscription graph means nothing.
3. **Delivery is deterministic** — wave, topic, source — or nothing downstream can be
   attributed or replayed.
4. **Every event carries its causal chain**, which is what turns the viewer's "why" from a
   shrug into a path.

And one law for the entities: **a model may propose a subscription; only the record may admit
one.** A candidate channel gets a one-month trial and survives only if the correlation of
*changes* between it and that entity's own published output clears a floor. That applies to the
language model too, which is the only reason it is allowed anywhere near the mechanism.

## The measurement: December 2023, the Red Sea

The point of the architecture is asymmetry — a shock should reach the countries actually
exposed to it and not the others. So: close Bab el-Mandeb on 15 December 2023, change nothing
else, and let it run for a year.

| | model | published |
|---|---|---|
| Asia–Europe container spot, peak | **3.04×** | roughly 3× (FBX, Jan 2024) |
| extra transit, Asia–Europe | **+12 days** on 26 | 10–14 days round the Cape |
| euro-area inflation from freight, ~3.5 months | **+0.29 pp** | ~0.25 pp (ECB, 2024) |
| US inflation from freight, 12 months | **+0.007 pp** | not measurable |
| crude, 12 months | **+5.4%** | crude barely moved |

**The 3× is not a validation — it is the anchor.** `CAPACITY_ELAS` was set from that episode, so
reproducing it proves the arithmetic and nothing else. The freight indices are not ingested yet;
until they are, this entity is a mechanism to argue with.

**The +0.29 pp against the ECB's ~0.25 pp is a real check**, because nothing in the freight-to-CPI
path was fitted: the 0.7 pp per doubling is the IMF's published cross-country estimate, the lane
exposures are trade geography, and the contract/spot blend is how shipping is bought. And the
US at +0.007 pp is the whole argument for the architecture: American goods do not travel on that
lane, so the shock never reaches them. Nothing in the code says "the Red Sea affects Europe".

### What the first version got wrong, and the correction

The first run put **+1.02 pp** into euro-area inflation over the year — four times the published
estimate. The arithmetic was right; the *price* was wrong. It was pricing the **spot rate**, and
roughly 60% of container volume moves on annual contracts. A spot rate that triples in a
fortnight reaches the freight bill slowly and partially.

That is the same class of error as pricing the flow gap daily instead of the stock, which was
the worst of the four defects phase 1 found. Both are: *a real number that is not the number
that gets paid.* Fixed by blending spot with a contract book that rolls over a year.

### What is still wrong, named

The contribution keeps climbing past twelve months (+0.77 pp) because the model holds the lane
capacity destroyed for ever. In 2024 transits stayed down all year but **spot rates came back
down anyway**, because the fleet grew about 10% and absorbed the detour. Shipping capacity
responding to margin is a missing mechanism, not a missing coefficient — the same verdict, in
the same form, as the calibration refusal.

## Effect on the scoreboard

None, and that is expected: products and freight are downstream of crude, and the scoreboard
scores crude. Blind 5/10 at 1.00, informed 9/10 at 0.99, unchanged. **The value of this phase
is not a better oil price — it is a second inflation channel that can be wrong in a way somebody
can check.**

## Also changed

- **Central banks meet, they do not drift.** The policy rate was moving a fraction of a basis
  point every day, which no central bank does and which flooded the bus with an event a day per
  bank. Eight meetings a year now, holding between them — a source of macro dynamics rather
  than an approximation of one.
- **The forecast table**, at the horizons the operator named: 7 / 30 / 90 / 365 days, with no
  intraday column, ever. `python -m mwmodel.project 365`, and the first three are live in the
  viewer.
- **The viewer** gained the horizon table at the top and "the chain of consequence" — the actual
  cascade of the last tick, grouped by what it descended from.

## Next

1. **Gas.** TTF, Henry Hub, JKM. The largest hole in a European inflation forecast.
2. **Fleet capacity that responds to margin**, which is what the twelve-month drift above is
   asking for.
3. **Ingest the freight and crack indices** so both new entities can be scored rather than
   argued about.
4. **The financial layer** — a forward curve, positioning, market makers. Still the binding
   constraint on the price itself, as the calibration said.
