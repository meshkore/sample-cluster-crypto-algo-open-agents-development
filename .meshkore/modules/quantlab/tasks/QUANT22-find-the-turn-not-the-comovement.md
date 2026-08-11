---
id: QUANT22
title: "Test cohort lead-lag on turning points, not on daily returns"
status: pending
priority: high
owner: unassigned
category: quantlab
initiative: global-market-trend
created: 2026-08-11
updated: 2026-08-11
tags: [cohorts, lead-lag, refutation, measurement]
depends_on: [QUANT20]
blocks: [QUANT24]
---

# Test lead-lag on turning points

## What the first measurement said

`cohort_lag.py` cross-correlated five cohorts against the whole market at every
lag from −90 to +90 days. **The correlation peaks at lag 0 for every cohort.**
BTC 0.779, majors 0.940, established alts 0.953, retail-era alts 0.694, recent
listings 0.457 — all at zero lag.

On daily co-movement, the "BTC leads, alts follow, memecoins last" hypothesis
is not supported.

## Why that is not the end of it

The test measured **co-movement of returns**, and the hypothesis is about
**turning points**. Those are different questions and the first does not
answer the second: two series can move together every day and still top two
months apart, because a top is a change in the drift and not in the correlation.

The peak table hints at exactly that — the cohorts topped in different cycles
entirely (2018-02, 2021-04, 2021-11, 2024-04, 2025-08).

## What to measure

- Timing of major peaks and troughs per cohort, on a swing definition (e.g. a
  20%+ retracement confirms a peak), against the market's own.
- Lead-lag of the **drawdown state**, not the return: is cohort A in drawdown
  before cohort B is?
- Conditional: given the market has just topped, how many days until each
  cohort tops? Distribution, not an average — the operator's "un mes, dos
  meses" is a claim about a distribution.

## Acceptance

Either a measured lead with a stated distribution and a sample size worth
acting on, or a second recorded refutation. Both are results. A refutation here
is worth more than the first one, because it closes the direction properly.
