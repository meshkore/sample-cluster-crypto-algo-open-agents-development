# Plan v2: is there an edge that survives out of sample? (operator, 2026-10-19)

Two independent reviews agree there is not enough evidence of an edge to arm real capital. The priority
is not a better backtest but finding out whether an advantage survives out of sample. Every step has a
condition that FALSIFIES it; when it holds, it is documented and we move on without "fixing" it with more
parameters. Translated from the operator's Spanish; the operator's text is the authority.

## General rules from now on

- Today's 14 is retired from every report. PIT only.
- 2026 stays sealed. A new prospective window opens today (`PROSPECTIVE_LOCK`, from 2026-10-19 00:00 UTC);
  it is never used for any selection.
- No new indicators, filters or sizing add-ons (Rocket showed none beats its placebo). Rocket is paused
  (`research/rocket/STOP`).
- Every metric carries a confidence interval (block bootstrap of daily returns, ~10-day blocks) and is
  reported on >= 2 seed sets, keeping the worse.
- Deliverable per phase: a short report with the metric, its CI, the result on both seed sets, and the
  sentence "falsified / not falsified". No phase starts without the previous one's report.

## Phase 0: execution and leakage audit (1 week)

1. Signal at the close of bar t; fill at the open of t+1 (or the close of t+1 as the conservative case).
   Re-run the current release with both.
2. Model stops, breakeven and trailing inside the bar, worst case (low touches the stop and high touches
   the TP in the same bar: assume the stop).
3. Return vs cost curve: 0.20 / 0.30 / 0.45 / 0.60 / 0.80% round trip. Per-pair slippage from ADV (dearer
   on PIT pair 14 than on BTC).
4. 8-day embargo (= max hold) at the year boundaries between train and test; check no label of the end of
   N-1 uses prices of N.
5. Check the gate and breadth are computed on the year's PIT universe, not on today's 14.
**Falsified if** with fill at t+1 and 0.45% cost the release loses more than half of its nested PIT
return: the edge was fictitious microstructure and the current system is retired.

## Phase 1: alpha or only beta? (1 week)

1. Three benchmarks on PIT: (a) BTC buy and hold; (b) equal-weight basket of the year's PIT universe,
   monthly rebalance; (c) naive rule: the EW basket when BTC > daily MA100, cash otherwise, same cost.
2. Daily regression of the strategy on (a) and (b): annualised alpha with t-stat, beta, correlation.
3. Sharpe, DD and return of the strategy vs (c) on 2022-2025 nested and on 2026.
4. Variant (d): rule (c) with x2 overweight on the top 7 by 90-day return (the book's own cross-sectional
   momentum factor).
**Falsified if** the residual alpha vs (b) has t < 2, or the strategy does not beat (c)/(d) in nested PIT
Sharpe: the MLPs add nothing; go to Phase 3 with the simple rule as the base.

## Phase 2: ablation and multiplicity correction (1-2 weeks)

1. Ablation on PIT nested, in this order, measuring each step: selector alone + fixed sizing -> + exit /
   forecast model -> + regime gate -> + x2 momentum and equity filter -> full system. A component stays
   only if it improves nested Sharpe on both seed sets.
2. Model baselines: ridge / logistic and a GBM with monotone constraints on the same 44 features and
   target. If the MLP does not beat them nested, it is replaced.
3. Training weights by label uniqueness (rows overlapping over the 96-bar horizon).
4. On the PIT configuration ledger: Hansen's SPA (stationary bootstrap) against benchmark (c); p-value.
5. Review the DSR: effective number of trials and the variance of Sharpe across trials; it must be
   consistent with PBO 0.76.
**Falsified if** SPA p > 0.10: no configuration of the ledger beats the benchmark after multiplicity.

## Phase 3: selection redesign (2 weeks)

1. Cut the ~40 levers to 3-5 swept ones; the rest fixed at justified defaults.
2. Replace "release = argmax" with bagging: average the positions / signals of the top-k (k = 20-50)
   configurations of the plateau. Nested PIT vs argmax.
3. New score: nested Sharpe with its lower CI bound as the objective; DD <= 18% as a constraint (margin to
   25%); drop "positive every year" and the minimum trading frequency as hard rules. Cash is a valid
   position in a bear regime.
4. One target: a single model of the expected net return of the entry, cost included (or P(TP before SL)
   at several horizons), instead of selector + forecast.
5. The same pipeline at 4h and 1d. At 0.3-0.45% cost, 15m is probably not the horizon.
**Falsified if** bagging + the reduced space neither improves nested PIT nor lowers the seed noise
(median 7.7 points): the variation between configurations is pure noise.

## Phase 4: portfolio risk (1 week, in parallel)

1. Volatility-target sizing (e.g. 1% daily risk per position) with a total portfolio risk budget.
2. Limits per asset and per correlated group (clusters on 90-day correlation) instead of "max 3
   correlated".
3. Stress: BTC -20% and alts -35% at once within 48 h, spreads x3, stops filled 2% worse. Resulting DD.
4. Replace the fixed x2 on the top 7 with a bounded, volatility-adjusted multiplier.
**Falsified if** risk sizing does not cut the tail DD without destroying the net return: keep the current
sizing with the added limits.

## Phase 5: forward test and the path to capital

1. From the honest backtest: mu and sigma of the net return per trade; trades needed n ~ (2 sigma / mu)^2.
   If n > 2,000, the per-trade edge is too small to validate in a year.
2. Acceptance band: bootstrap distribution of return and DD at 1/3/6/12 months; paper must stay between
   p5 and p95.
3. Paper logging: signal timestamp, theoretical price, order, simulated fill, assumed vs observed slippage.
4. Stops: CUSUM on per-trade PnL against the expected; hard stop if DD > bootstrap p95 or realised
   slippage > 2x the assumed.
5. Scaling: 0% until 6 months inside the band -> 10% of capital -> 50% at 12 months -> 100% after another
   half year. Any exit from the band returns to 0% and reopens the audit.

## Status

| phase | status | report |
|---|---|---|
| 0 | FALSIFIED 2026-10-19: worse seed set loses 56% with t+1 fill + 0.45%; all frictions negative on both | `PHASE0.md` |
| 1 | FALSIFIED 2026-10-19: alpha vs EW basket t < 2 everywhere (best 1.41); no Sharpe gain over rule c | `PHASE1.md` |
| 2 | skipped by the plan (phase 1 falsified -> phase 3 with the simple rule as base) | |
| 3 | FALSIFIED 2026-10-19: nothing passes DD <= 18% long-only, seed noise 8.5 pts; BUT the net-return model has a robust OOS cross-sectional IC (98/120 cells t > 2) | `PHASE3.md` |
| 4 | NOT FALSIFIED 2026-10-19: risk layer cuts tail DD 59 -> 43% and lifts net 2022-25 -4 -> +13% (medians); still no config with DD <= 18% every year; nested worse seed set -13.6% | `PHASE4.md` |
| 3b | FALSIFIED 2026-10-19: market-neutral long/short, worse seed set Sharpe -0.06, wins 2022/2025, loses the 2023-24 rallies | `PHASE3B.md` |
| read 1 | 2026 signal: only 4h / 1-day gross IC survives (0.05, t 2.5); tail spread about 0, below cost | `READINGS.md` |
| forward | RUNNING: Windows task plan-v2-forward-ic every 4 h scores the frozen 4h / 1-day signal on the prospective window (`forward/FORWARD.md`); external review round 2 requested (public brief updated) | `forward_ic.py` |
| 5 | no candidate: best honest Sharpe 0.82 needs ~6 years of forward data at 2 sigma | `PHASE4.md` |
