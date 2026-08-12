---
id: QUANT28
title: "The objective was paying the search to stop trading"
status: done
priority: high
owner: master
category: quantlab
initiative: public-agent-lab
created: 2026-08-12
updated: 2026-08-12
tags: [objective, search, exposure, benchmark, 2026, sizing]
depends_on: []
blocks: []
---

## Scope

Ninety-one iterations, and the best forward result the laboratory holds is
+1.12% over 2026. The operator asked why. The answer was not the strategy.

**The objective was not scale-invariant.** v1 scored
`median(fold returns) * consistency - worst_drawdown`. Halving every position
halves both terms, so any candidate scoring below zero was improved by shrinking
— and the optimum for such a candidate is a position size of zero. 75 of the 90
recorded candidates were in that regime. The search found the door and walked
through it: by iteration 91 the incumbent risked 0.54% per trade at a 34% sizing
distance, deployed 0.18% of the book in 2026, and held anything on 4% of days.
Iteration 89, the only iteration that raised position size, was scored worse
than the incumbent for it.

The trade floor could not catch this. Shrinking positions does not reduce trade
count, which is exactly why it survived ninety iterations undetected.

**Nothing could see it.** `PortfolioEvaluation` has carried `average_exposure`
since the laboratory published eight months of results at 5-9% exposure, but
`Session.summary()` did not — and the summary is what the parameter search
reads. The search scored six hundred configurations a generation with no idea
how much capital any of them deployed.

**2026 was scored against zero.** Over 2026-01-01..07-31 the equal-weight
basket of the laboratory's own universe returned -30.9% after costs, BTC hold
-28.5%, median asset -48.5%, 41 of 436 up. A long-only book has a ceiling near
cash in that year. Against an implicit 0% benchmark, "correctly refused to
participate" and "did nothing" are the same number and opposite findings.

## Done when

- The objective is invariant to position size.
- A run that never commits the book is rejected rather than ranked.
- Scores carry the objective that produced them, and a score from an older one
  is never ranked against a newer.
- Every 2026 result is recorded beside what the market did over the same window.

## Outcome

Done 2026-08-12.

`objective()` v2 returns `(median * consistency) / worst_drawdown`, a ratio.
`Score` carries `exposure` and `version`; `LoopState.load` discards a v1
incumbent score rather than converting it — the two functions are not monotone
in each other, which is the reason the objective was replaced.

**There is no exposure floor.** One was shipped and removed the same day; the
attempt is worth more than the mechanism. It gated on DEPLOYED exposure
(`average_exposure / time_in_market`) at 10%, calibrated on a probe that used
one 2018-2025 window over all 386 symbols with no `tradeable_assets` cap. Under
the real fold windows and the real deployment scope — top 100 by turnover — the
healthy genome deploys 4.23% and the pathological one 4.3%. The metric cannot
separate them. It rejected 149 consecutive candidates in iteration 105, every
event logging `best: -Infinity`, and the loop produced nothing for an afternoon.
Exposure is now recorded on `Score` and never gated on.

The probe's other conclusion was wrong for the same reason. It reported that at
1x sizing the strategy *loses* −2.29%, which read as `notional_for` deleting
positions below `minimum_position_fraction` rather than scaling them. On the
four folds the search actually scores, trade count is **944 at every rung from
0.5x to 3x** — sizing deletes nothing, and every rung is profitable:

| size | implied | fold returns | worst dd | deployed | score |
|---|---|---|---|---|---|
| 0.5x | 1.58% | 0.28 / 4.93 / 5.54 / 4.66 | 2.76% | 2.49% | 1.735 |
| 1.0x | 3.17% | 0.56 / 10.02 / 11.26 / 9.37 | 5.48% | 4.98% | 1.770 |
| 2.0x | 6.34% | 1.12 / 20.67 / 23.23 / 18.84 | 10.77% | 9.93% | 1.834 |
| 3.0x | 9.51% | 1.68 / 31.84 / 35.51 / 29.24 | 15.19% | 14.75% | 2.010 |

A 6x change in position size moves the score 16%. That is the objective working
as designed, and it is also the reason **the search will never choose a size.**
Sizing is a mandate decision, not a score decision: the rung is picked by how
much of the operator's 25% abort it is allowed to consume. `lift_sizing_to_the_floor`
doubles a v1 incumbent once during the migration so a starved genome does not
carry v1's sizing into v2; the incumbent was then set to the 3x rung by hand and
recorded as **H-SIZE-001** with the ladder above as its evidence. Every rung was
measured through a backtester started without `--forward`. 2026 was not
consulted and must not be — scaling the book scales the sealed year in both
directions, so sizing to flatter it is exactly the contamination the lock exists
to prevent.

`benchmarks.py` records equal-weight and BTC-hold beside every 2026 result.
Commentary only: computed after the verdict, never entering selection, and
unable to fail an iteration.

## What this does NOT fix

Fit score anti-predicts 2026 at Pearson −0.293 across 53 paired runs. The
candidates v1 rewarded for growing are the ones 2026 destroyed — iteration 77
scored +0.176, the best ever, and returned −22.20%. Four folds ending 2025-12-31
cannot know that 2026 is unlike all four, and no honest pre-2026 objective can
be made to know it. This work removes a defect in how the search spends its
effort; it does not make the fittable era predictive of the sealed one.
