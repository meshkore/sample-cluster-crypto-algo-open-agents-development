---
id: QUANT9
title: "Evaluate the mechanism behind a third-party TradingView script as a new hypothesis"
status: pending
priority: low
owner: unassigned
category: quantlab
initiative: liquid-ml-research
created: 2026-08-03
updated: 2026-08-03
tags: [hypothesis, external-source, mechanism, evaluation]
depends_on: []
blocks: []
---

## Why this exists

The operator found a TradingView script ("0DTE Scalper v4 — Kalman SuperTrend
and ADX Volatility Waves") that markets itself as working, and asked whether we
could read it, copy it and adopt it. Flagged for a later round rather than
answered inline in chat, because it needs the same skepticism this laboratory
applies to its own results, not a shortcut around them.

## What to actually do

**Do not copy the script or its backtest claims.** Per `ADVERSARIAL_REVIEW.md`,
every profit claim is false until supported by locked out-of-sample data we ran
ourselves — a vendor's marketing page is not evidence, and TradingView
"protected"/invite-only scripts frequently hide the real Pine source behind a
description and cherry-picked screenshots that cannot be reproduced or audited.

Two things are also structurally wrong for this lab regardless of whether the
mechanism has merit:

1. **0DTE is an options concept.** Zero-days-to-expiration scalping is about
   same-day option expiry (theta, gamma near expiry) on instruments this
   laboratory does not and will not trade. Long-only crypto spot has no
   analogue to "days to expiration."
2. **License/reuse.** Most TradingView scripts retain the author's copyright
   even when the description is public; many hide the source entirely behind
   "protected" publication. Read what's public, do not assume redistribution
   rights, and do not paste vendor source into this repository.

What is legitimately worth taking: the **named signal ingredients** —
SuperTrend and an ADX-based volatility/regime filter are ordinary, well-known,
independently implementable indicators with no license attached to the concept
itself. If this is worth a round:

1. Read the script's *public* description only (no login, no purchased/invite
   access) for the stated mechanism, not the performance claims.
2. Restate it as an economic/behavioral hypothesis in this lab's own format
   (mechanism, trigger, entry/exit, expected failure modes, invalidators) —
   the same shape every other hypothesis here uses.
3. Implement our own version of the signal (SuperTrend + ADX volatility gate,
   long-only, on our own daily-bar crypto data) and run it through the normal
   pipeline: Phase-1 sweep, robustness checks, forward evaluation, benchmark
   comparison. It graduates or fails exactly like every other family — no
   special treatment for having a plausible-sounding external source.
4. If it fails, record it in `research/FAILURES.md` like any other rejected
   family, naming the external source so it isn't retried later.

## Acceptance criteria

- No vendor source code or paid/invite-only content is pasted into this repo.
- The mechanism is stated as a first-class hypothesis and tested exactly like
  any other family, with no exemption from the drawdown limit, cost model or
  benchmark comparison.
- Whatever the result, it is reported honestly — including "this does not
  survive contact with real costs and a benchmark," which is what has
  happened to most ideas evaluated here so far.
