---
id: S9V2-3
title: "Score 2026 as divergence from reality, day by day"
status: active
priority: high
owner: win-opus-5
category: trading-system
initiative: system-nine-reality-alignment
created: 2026-09-14
updated: 2026-09-14
tags: [system09, v2, forward, divergence, calibration]
depends_on: [S9V2-1, S9V2-2]
blocks: []
---

## The ask

*"En 2026 lo que tendríamos que valorar es cuánto nos alejamos de la realidad respecto a lo
que nuestro modelo prevé que va a pasar día a día."*

## What to build

A forward simulation that, from the 2025-12-31 state, predicts each day of 2026 - per-asset
prices and capitalisation, flows, segment balances - and a scorer that reports the distance to
what actually happened, as a daily series decomposable by asset and by segment.

Report at minimum: mean absolute relative error on capitalisation, the horizon at which the
prediction stops beating a random walk, and which segment's balance drifts first. That horizon
is the honest statement of how far ahead this simulator can see.

## The discipline that makes this legal

Divergence is a **calibration** instrument and cannot select a trading configuration, so it may
be looked at openly. **Any trading evaluation stays sealed** and needs a window this system has
never touched - 2026 is spent for that purpose, three readings deep. Keep the two scoreboards
in different files so they can never be confused.

## Done when

The divergence series is on the dashboard beneath the capitalisation chart, and RESULTS.md
states the prediction horizon in days.
