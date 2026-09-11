---
id: QUANT26
title: "Show the market composite in the monitor, beside the equity"
status: archived
priority: medium
owner: unassigned
category: design
initiative: global-market-trend
created: 2026-08-11
updated: 2026-09-10
tags: [monitor, design, transparency]
depends_on: [QUANT20]
blocks: []
---

# Show the market composite

## Why

The equity curve is now coloured by the detected regime, so a reader can see
*what the detector decided*. They cannot see *what it decided from*. When the
line turns red the obvious next question is "was the market actually falling
there?" and the monitor has no answer.

## What to build

- The market composite drawn behind the equity curve on the same time axis, at
  low contrast, so the regime bands can be read against the thing that produced
  them.
- Breadth as a second, thin series — it is the statistic that actually moved
  the label after QUANT20 and it is currently invisible.
- Both served from the run itself, not recomputed in the browser: the composite
  is a property of the run's own tape and a second implementation in JavaScript
  would be a second place to be wrong.

## Acceptance

A reader can answer "why is this stretch red?" without opening a terminal.

---

## Closed out — 2026-09-10

Archived with the generation it belonged to. System 08 is in a **design-only** phase: no
code, no backtests, no measurements, until the operator authorises it in words.

Nothing here is lost. Every option and experiment worth revisiting is catalogued in
[`.meshkore/context/experiment-catalogue.md`](../../../context/experiment-catalogue.md),
which is the one place to look before proposing work — so that we do not re-open a question
this laboratory has already answered.
