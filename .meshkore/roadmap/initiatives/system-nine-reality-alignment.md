---
id: system-nine-reality-alignment
title: "System 09 v2: a model that equals reality, and a 2026 measured as divergence"
status: active
priority: high
oneliner: "v2 must reconcile to the real market: the modelled capitalisation at 2025-12-31 equals the published one, prices and volumes are the real ones for every asset, and 2026 is scored by how far the model's day-by-day prediction drifts from what actually happened."
modules: [trading-system]
target: "V5 calibration PASS at every checkpoint, and a daily divergence series for 2026"
created: 2026-09-14
updated: 2026-09-14
owner: win-opus-5
related: [system-eight-from-zero]
---

## Why this initiative exists

The operator set the condition on 2026-09-14: *"si a 31 del 12 de 2025 la capitalización de
cripto es de 4 billones, nuestro sistema tiene una capitalización de 4 billones... estamos
respetando los precios de Bitcoin y de todos los assets del mundo... los mismos volúmenes de
trading registrados y publicados... y en 2026 lo que tendríamos que valorar es cuánto nos
alejamos de la realidad."*

v1 never tested this. It conserves units and cash internally - V0 passes to 1e-14 - but
nothing ever compared its **levels** to the published world. The one test that looked outward,
V2 anchor recovery, won all six flow statistics and **lost both level statistics**, which is
the same finding stated in the model's own language.

Measured today, before any v2 work: the model's capitalisation at 2025-12-31 is **$2.525T**
over 14 assets. The real total is around $4T. Most of that gap is scope - the world has
thousands of assets and we carry fourteen - but *how much* is scope and how much is wrong
float has never been separated, and that separation is the first task.

## What "aligned with reality" means, concretely

Three reconciliations, each with a number that either passes or fails:

1. **Price.** Every asset's price in the ledger is the published close. Not a modelled price,
   not an average - the observed one. (v1 already does this; v2 asserts it.)
2. **Capitalisation.** For every asset, `modelled float x published price` must equal the
   published market capitalisation at a set of checkpoints, within a stated tolerance. The
   universe total must then reconcile against the published global total, with the residual
   named and carried as an explicit "rest of market" aggregate rather than silently missing.
3. **Volume.** The dollar volume the ledger settles per asset per day must equal the published
   volume for that asset and day, per venue. Where our venue is a share of global volume, that
   share is measured and reported, never assumed.

## What 2026 becomes

Not a P&L reading. A **divergence measurement**: the model predicts the state of the market
day by day - capitalisation, per-asset price paths, flows, the balance of each segment - and
we score the distance between that prediction and what actually happened, each day, as a
series that can be plotted and decomposed by asset and by segment.

This is a calibration instrument, not a selection instrument, and the distinction is what
makes it safe to look at: it measures *whether the simulation is a model of the world*, and it
cannot be used to choose a trading configuration. **The trading reading stays sealed** - any
strategy evaluation still needs a window this system has never touched.

## Scope

- **In:** per-asset supply histories, published market-cap and volume series, a global-total
  reconciliation, the rest-of-market aggregate, the V5 calibration ladder, the divergence
  scorer and its dashboard section.
- **Also in, because the divergence score is meaningless without them:** the generalisation
  work (purged walk-forward, ensembles, fold spread) and the external-economy layer - a model
  whose boundary is inferred as a residual cannot predict the boundary.
- **Out:** live trading, wallets, exchange secrets. Unchanged and absolute.

## Done looks like

- `V5 CALIBRATION` prints per-asset and total rows at 2018-12-31, 2021-12-31 and 2025-12-31,
  each with a tolerance and a verdict.
- The dashboard shows modelled capitalisation against published capitalisation on one axis,
  and the 2026 divergence series below it.
- `docs/RESULTS.md` carries the calibration table and states what the residual is made of.
