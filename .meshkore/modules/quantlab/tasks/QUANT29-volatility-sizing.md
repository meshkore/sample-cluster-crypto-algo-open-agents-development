---
id: QUANT29
title: "Every asset was bought the same size, however violent it was"
status: done
priority: high
owner: master
category: quantlab
initiative: public-agent-lab
created: 2026-08-12
updated: 2026-08-12
tags: [sizing, risk-parity, volatility, literature, 2026]
depends_on: [QUANT28]
blocks: []
---

## Scope

The operator asked why 2026 holds nothing above +1.89% and asked for the
literature to be consulted. Both halves of that produced the same answer from
opposite directions.

**What 2026 actually is.** The session record for the best forward run shows the
detector labelling **205 of 212 days BEAR**. The bear branch buys strength
cautiously, so the year produced 51 order days, five concurrent positions and
1.7% time in market. +1.89% is a cash return; it is not a deployed book earning
1.89%. Against an equal-weight basket that lost 30.9% over the same window that
is a good outcome, and it is also the reason absolute return cannot be improved
by trading the same signal harder.

**What the literature says.** Kim, Tse & Wald (2016) report that time-series
momentum's performance is driven by the volatility-SCALED returns -- the risk
parity weighting -- rather than by the momentum signal itself. The crypto
momentum-crash literature arrives at the same control from the other side:
momentum suffers severe crashes and volatility management is what mitigates
them. Both describe scaling toward a target in BOTH directions.

**What this laboratory does instead.** Nothing. `notional_for` computed
`equity * risk_per_trade * confidence * deleverage / sizing_distance` and never
looked at the asset. A 5%-a-day asset and a 15%-a-day asset were bought in
identical size, so the book's risk collected in whichever names happened to be
wildest. Measured on the served panels, `natr_14` runs 5.07% at p10 and 14.86%
at p90 -- a 2.9x spread that sizing ignored completely.

There IS a volatility term in `LongOnlyPortfolioBacktester`, and it was written
one-sided: `min(1.0, volatility_target / observed_vol)`. Median 20-day
volatility is 4.82% over 2018-2025 against a 2.5% target, so that clamp binds on
91.3% of observations and acts as a near-permanent half-size haircut rather than
as risk parity. But that engine is NOT the path the loop runs, which is the
finding that matters: a fold sweep at cap 1.0 and cap 2.0 returned
1.68/31.84/35.51/29.24 in both arms, identical to four decimals, because the
four-module brain never calls it. `volatility_target` and `volatility_lookback`
have been dead configuration for every result this laboratory has published.

## Done when

- Position size responds to the asset's own volatility in the path the loop
  actually runs.
- Switching it on is exposure-neutral at the median asset, so risk parity and
  leverage can be attributed separately rather than confounded.
- Every stored policy and every published result is unchanged until the tilt is
  deliberately switched on.
- The tilt is measured on the four pre-2026 folds at matched exposure against
  the H-SIZE-001 sizing ladder before any 2026 run is paired with it.

## Progress

Shipped, unproven. `MoneyManagement.volatility_sizing` (default `False`),
`volatility_sizing_target` (default 0.085, the measured universe median of
`natr_14`) and `volatility_sizing_column` (default `natr_14`); the brain feeds
`notional_for` the served column out of the row it already holds.

The target defaults to the measured median deliberately: switching the tilt on
leaves the MEDIAN position size untouched and only redistributes size between
quiet and violent assets. A target set anywhere else mixes risk parity with a
size increase, and neither effect could then be attributed -- the same mistake
`stop_loss_pct` made by serving as both the exit and the sizing denominator.

`volatility_scale_cap` bounds how far a quiet asset is leaned into, and also
un-clamps the engine's one-sided term for the callers that do use it. It
defaults to 1.0, which reproduces the old expression exactly; the fold control
cell confirmed that on real data at four decimals.

Sabotage-verified on both seams: reverting `volatility_scale` to `return 1.0`
fails three tests, and dropping `row` from the `_maybe_buy` call collapses the
sized ratio from 3.0 to 1.0. The second sabotage initially PASSED, because the
first version of that test called `_maybe_buy` directly and never crossed the
seam it claimed to cover; it now drives the real tick path.

## Outcome

Done 2026-08-12. **H-VOL-001 REFUTED.** Five tilted arms against the one-sided
sizing ladder, at matched deployed exposure:

| arm | deployed | worst dd | score | untilted at same exposure | gap |
|---|---|---|---|---|---|
| control, no tilt | 14.75% | 15.19% | 2.0099 | -- | -- |
| cut only | 11.97% | 13.30% | 1.7013 | 1.895 | -10.2% |
| two-sided 1.7 | 13.57% | 15.50% | 1.5742 | 1.959 | -19.6% |
| two-sided 3.0 | 13.65% | 15.58% | 1.5772 | 1.962 | -19.6% |
| two-sided 1.7, 0.7x | 9.69% | 11.53% | 1.4885 | 1.831 | -18.7% |
| two-sided 3.0, 0.5x | 7.13% | 8.04% | 1.5350 | 1.801 | -14.8% |

Every arm sits below the untilted curve at its own exposure. Trade count is 944
in all six including the control, so this is sizing alone and not a different
set of positions.

The score is not the damning number. The drawdown is: two-sided tilt carries
15.50% drawdown on 13.57% deployed against the control's 15.19% on 14.75% --
**more drawdown on less capital.** Inverse-volatility weighting did not merely
fail to add return here, it made risk worse per unit committed, which is the one
thing a risk control may not do. Raising the cap from 1.7 to 3.0 moved the score
by 0.003, so the mechanism had saturated and there is no headroom left to find.

The reading: in this universe volatility appears to be compensated, so
equalising risk across assets systematically underweights the names that produce
the return.

Kept, defaulting to off. The control arm reproduced 1.68/31.84/35.51/29.24 and
2.0099 exactly, so it costs nothing while unused, and a refuted mechanism that
can be switched back on with one parameter is worth more than one that must be
rebuilt before it can be re-argued.

## The mistake in how this was proposed

Kim, Tse & Wald's result is TIME-SERIES volatility scaling -- scaling the whole
book by its own trailing volatility through time. What was built and refuted
here is CROSS-SECTIONAL inverse-volatility weighting, sizing assets against each
other on the same day. The evidence for one was imported as justification for
the other. This sweep refutes the cross-sectional mechanism on these folds and
says nothing about the time-series one.

And the time-series one was NOT untested, which is a second error in the same
paragraph as originally written. **H-L104, iteration 104**, tested exactly it --
"throttling TOTAL book exposure by trailing MARKET-WIDE realized volatility,
scaling risk_per_trade and maximum_concurrent_assets inversely to a rolling
natr_14 against its own 90-bar median" -- and it was REFUTED: the fit did not
clear the gate at -0.0837 against a best-known POLICY score of 0.0178, so the
forward window was never opened. It was found by the diary built the same day,
which is the argument for the diary in one line.

The one thing that keeps it alive: H-L104 was scored under objective **v1**, the
non-scale-invariant one replaced in QUANT28. A mechanism whose whole effect is
to shrink the book was judged by an objective that rewarded shrinking, and it
still failed. Re-testing it under v2 is defensible; assuming it will pass is
not.

## What this does NOT claim

That it earns more. Raising exposure earns more in a rising fold and that is
leverage, not edge. No 2026 run was paired with any of this: an arm that loses
on the fittable era does not get to consult the sealed one.

Nor does it address selection. In a year where 41 of 436 assets rose, a
long-only book's ceiling is near cash, and sizing cannot move that -- only
finding those 41 can. The trend-factor line (Han, Zhou & Zhu; the 2025 JFQA
crypto version) is the candidate for that and is not started.
