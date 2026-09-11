---
id: QUANT24
title: "A cohort-aware detector, if and only if a lead is measured"
status: archived
priority: medium
owner: unassigned
category: quantlab
initiative: global-market-trend
created: 2026-08-11
updated: 2026-09-10
tags: [detector, cohorts, conditional]
depends_on: [QUANT22, QUANT23]
blocks: []
---

# A cohort-aware detector

## Conditional by design

**Do not start this until QUANT22 finds a lead.** The first lead-lag
measurement found none, and building a cohort-aware detector on a lag that does
not exist would add four moving parts to the piece the whole system routes on,
in exchange for nothing.

## What it would be, if the lead is real

The detector currently averages every cohort into one number, which can only
ever be a lagging compromise of segments that turn at different times. If a
cohort genuinely turns first, the detector should read **that cohort** for the
turn and the broad index for the level:

- A `leader_scope` parameter naming which cohort supplies the trend test.
- Breadth still from the whole universe — breadth is the statistic that needed
  the wide market most, and narrowing it would undo QUANT20.
- The lead expressed as a parameter, searchable, so the loop can refuse it.

## Acceptance

Beats the QUANT20 detector on the same scorecard — separation ordering, arrival
inside the fall, and bear-branch training signal — on the fittable era, and then
survives a forward run. Anything less and the simpler detector wins.

---

## Closed out — 2026-09-10

Archived with the generation it belonged to. System 08 is in a **design-only** phase: no
code, no backtests, no measurements, until the operator authorises it in words.

Nothing here is lost. Every option and experiment worth revisiting is catalogued in
[`.meshkore/context/experiment-catalogue.md`](../../../context/experiment-catalogue.md),
which is the one place to look before proposing work — so that we do not re-open a question
this laboratory has already answered.
