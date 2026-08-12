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

The exposure floor gates on DEPLOYED exposure
(`average_exposure / time_in_market`), not average. Measured, not reasoned:
this incumbent stands aside 75% of days by design, so its average exposure
cannot exceed 4.3% at any legal position size and an average floor of any useful
height would reject everything. Sizing sweep on the incumbent, 2018-2025:

| size | return | worst dd | avg exposure | deployed |
|---|---|---|---|---|
| 1x | −2.29% | 10.33% | 1.09% | 4.5% |
| 2x | +26.16% | 15.46% | 3.02% | 11.9% |
| 3x | +43.79% | 20.55% | 3.77% | 14.8% |
| 4x | +68.20% | 23.01% | 4.32% | 17.0% |

Row one is the finding behind the finding: at v1's sizing the strategy does not
earn less, it *loses*. `notional_for` returns zero below
`minimum_position_fraction`, so shrinking deletes positions rather than scaling
them. The floor is 10% deployed, and the incumbent's `risk_per_trade` is lifted
2x once in the migration — not 4x, which scores best and sits 2% from the 25%
abort.

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
