---
id: QUANT24
title: "A cohort-aware detector, if and only if a lead is measured"
status: pending
priority: medium
owner: unassigned
category: quantlab
initiative: global-market-trend
created: 2026-08-11
updated: 2026-08-11
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
