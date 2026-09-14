---
id: S9V2-1
title: "V5: reconcile the modelled capitalisation to the published one, asset by asset"
status: active
priority: high
owner: win-opus-5
category: trading-system
initiative: system-nine-reality-alignment
created: 2026-09-14
updated: 2026-09-14
tags: [system09, v2, calibration, market-cap, supply]
depends_on: []
blocks: [S9V2-2, S9V2-3]
---

## The ask

The operator's condition: if crypto is worth $4T on 2025-12-31, the model is worth $4T.
Measured before starting, the model is worth **$2.525T over 14 assets**.

## What to build

`validate.calibration()` - a V5 rung that, at 2018-12-31, 2021-12-31 and 2025-12-31, prints
per asset: modelled float, published circulating supply, published price, modelled cap,
published cap, relative error, verdict. Then a universe row and a global row.

## The three sources of error, which must be separated and not averaged

1. **Scope** - assets the universe does not carry. Quantifiable exactly: published global cap
   minus published cap of our fourteen. Reported as a named "rest of market" line, never
   silently missing.
2. **Float** - alt supply is a held-constant snapshot in v1, so every emitting asset holds too
   much float in the early years. Fixed by real supply histories (S9V2-2).
3. **Ledger** - units the reconstruction created or destroyed. V0 says this is ~1e-14, so it
   should be zero; if V5 says otherwise, V0 is testing the wrong thing.

## Done when

The three errors are separately quantified at all three checkpoints and the table is in
`docs/RESULTS.md`. A single blended "we are 37% off" number is a failure of this task.
