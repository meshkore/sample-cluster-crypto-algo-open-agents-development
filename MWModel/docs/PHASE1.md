# Phase 1 — the energy chain, and the four defects the scoreboard found

*2026-09-15. Everything here was measured, not argued.*

## What changed

**Real balances.** The EIA publishes its whole international database as a single 24 MB file,
free and keyless, updated within the month. Every placeholder in `seed/facts.py` is gone:
production monthly by country in thousand barrels per day, consumption, crude separately,
imports and exports. 60 of 60 country energy figures are now `measured` or `declared`;
none is a placeholder. The world clears against **104.6 mb/d produced and 103.1 consumed**,
which are the real numbers, and the aggregate "rest of the world" player is the computed
residual rather than a guess.

**Point-in-time, as everywhere else in this laboratory.** A replay standing on 1 March 2022
sees only what the EIA had published by then, with its two-month reporting lag applied.
Without that the model reads the future and then congratulates itself.

**The news channel.** Twenty-three dated energy events, each with named effects in four
separate channels — `valve.*` (a strait narrows), `capacity.*` (a cartel cuts, a sanction
bites), `demand.*` (a pandemic, a tariff), and `risk`, a premium paid for fear that
corresponds to no missing barrel and **decays with a three-week half-life**. Separating that
last one matters: Bab el-Mandeb in 2024 multiplied freight and barely moved crude, while
Hormuz would move crude without a single tanker being lost.

## The scoreboard

Ten start dates, 120 days each, seeded only with what was published on day one, scored against
what crude actually did. The null is a **flat line** — for oil, a genuinely hard benchmark.

| | beats the flat line | median error ratio |
|---|---|---|
| blind (told nothing after day one) | 3 / 10 | 1.20 |
| informed (told the dated events) | 4 / 10 | **1.19** |

The median barely moves because most windows contain no events. Where events happen, the
channel earns its place:

| window | blind | informed | what happened |
|---|---|---|---|
| 2022-01 | 1.45 | **0.97** | Russia invades Ukraine in February |
| 2024-01 | 1.60 | **1.32** | Red Sea attacks, tankers round the Cape |
| 2025-01 | 1.02 | **0.90** | tariffs, and OPEC+ accelerating supply |

**It still loses more often than it wins, and that is the honest headline.** A simulated world
is not yet a better guess than "tomorrow is today".

## The four defects, each found by the measurement and each a constant pretending to be a model

1. **A fixed reference price.** Consumers compared today's price to a number in a file, so
   every country's demand pulled the market back to that number. The world was an attractor at
   $68: a replay from $47 rose to $71, one from $110 fell to $68. *Fixed:* the reference drifts
   towards what is actually being paid, half-life six months — which also gives the model base
   effects, the thing that made 2023 inflation fall without any price falling.

2. **One kind of producer.** Every producer chased the margin over its fiscal breakeven, which
   turned the *average breakeven* into a second attractor near $60. *Fixed:* outside OPEC+ a
   producer is a price taker with sunk capital and runs at capacity; only OPEC+ manages output.

3. **Capacity that nobody holds.** Inferring capacity from the best month of five years gave
   price takers ten million barrels a day of phantom spare. Since price takers run flat out,
   the market was permanently oversupplied and collapsed in every replay. *Fixed:* for a
   producer with no spare, capacity *is* current production. Roster spare fell from 13 to
   9.6 mb/d, of which 3.3 is Saudi — in line with the published figure.

4. **The market priced the flow, not the stock.** This was the worst one. The supply-demand gap
   was applied as a percentage price move *every single day*, so a persistent surplus of two
   tenths of one percent compounded into a 40% collapse over four months while supply and
   demand stayed matched to within a fifth of a percent. Nobody reprices oil daily because last
   Tuesday was slightly long. *Fixed:* the flow gap enters once, through inventories, and price
   responds to **days of cover** — which makes the system self-correcting instead of explosive,
   and produces a convex spike only when cover falls through the floor.

And one defect in the *chronicle* rather than the model: the July 2021 OPEC+ unwinding was
written with a 4% step in world demand attached. An agreement to unwind supply cuts is not a
demand event, and world demand does not step 4% on a Tuesday. It made that window five times
worse. Corrected, and the correction is in the file where anyone can see it.

## What the attribution says now

> supply simulated 101.89 vs published 103.43 mb/d (−1.50%)
> demand simulated 102.94 vs published 103.11 mb/d (−0.16%)
> **quantities are right; the error is in the clearing**

That is the value of separate agents: the remaining error has an address. The quantities the
world produces and burns are right to within a percent and a half; what is still wrong is the
price the market puts on them.

## Next

- Fit the clearing sensitivity and the event effect sizes against the record instead of
  asserting them — every one of them is a regression waiting to be run, and several will turn
  out to be wrong.
- Products: diesel, jet, gasoline. That is where the inflation channel actually runs, and the
  model currently jumps straight from crude to the pump.
- Refining and freight as their own agents, so a chokepoint's freight premium is computed
  rather than tabled.
- The phase-1 gate itself: replay 2022 and reproduce the diesel crack and the TTF spike within
  a stated band, out of sample.
