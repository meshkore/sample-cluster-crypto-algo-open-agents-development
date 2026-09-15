# MWModel

*A model of the world economy built out of agents that each pursue their own interest.*

```
python server/app.py          ->  http://127.0.0.1:8800
```

## What it is

Not one model that understands everything — many small ones that each simulate a player, put
in the same world, and left to interact. States, central banks, producing sectors, investor
cohorts, market makers. Each has a balance sheet, an interest, its own partial and late view
of the world, a memory, a policy, and **a published number it must reproduce**. That last one
is the gate: an agent with nothing to be scored against does not get built.

The whole plan is in [`docs/MASTER-PLAN.md`](docs/MASTER-PLAN.md). Read that first.

## Why it exists

Because of a question the previous system could not answer: *how will inflation look in sixty
days, given that Hormuz and Bab el-Mandeb are constrained?* Answering it needs a chain — a
strait's capacity, rerouting, freight, delivered crude, refining, the energy weight in each
country's basket, the publication lag, the central bank's reaction — and every link in that
chain is a small model with its own error bar. The system's job is to hold the chain and carry
the uncertainty along it, not to be an oracle.

And the top of the chain is not an assumption either. A chokepoint is the current state of a
negotiation between players who each have something to gain, so it has a hazard of changing
that responds to how much everyone is hurting.

## Three laws

1. **Conservation.** Money and physical units balance, asserted in the hot path. A
   violation stops the tick; it is never logged and continued.
2. **Asymmetric information.** Nobody sees the world state — each agent sees its own late,
   partial observation of it. A model where everyone knows everything has no trade in it.
3. **Nothing is exogenous that could be endogenous.** Every constant here is a placeholder
   for an agent not yet built, and the plan says which.

## Layout

```
mwmodel/
  state.py            the world, and the conservation law
  engine.py           the tick: advance, deliver, perceive, decide, clear, settle, record
  project.py          ensemble projection - scenario hazards, parameter and shock uncertainty
  agents/             base + countries + central banks
  markets/            clearing
  network/            the valves of the world
  seed/               the starting world, every figure marked as a placeholder
  archive/            THE WORLD ARCHIVE: 85 point-in-time streams back to 1947, plus the
                      chronicle of dated events. Moved here from the trading laboratory on
                      2026-09-15; docs/DESIGN.md and docs/FINDINGS.md live inside it.
server/               the viewer
data/                 gitignored: the archive's store, raw ingests
docs/MASTER-PLAN.md   the five-year plan and the phase gates
```

## Status: phase 0

The world turns, conservation holds, and the chain from a strait to a consumer price runs end
to end. Narrow Hormuz and crude goes from $70 to $208, barrels strand in Gulf tanks, and
inflation rises by a *different* amount in every country — Turkey's energy contribution
reaches 14pp where Japan's reaches 4. Nothing wired that; it falls out of agents each doing
the obvious thing.

**Every input is an order-of-magnitude placeholder and every coefficient is a starting value.**
Real energy balances land in phase 1, real CPI baskets in phase 2. This is a mechanism to
argue with, not a forecast.

## What this is not

Not a trading system. It reads the world and acts on nothing; there is no path from this code
to an exchange, a wallet, or a key.
