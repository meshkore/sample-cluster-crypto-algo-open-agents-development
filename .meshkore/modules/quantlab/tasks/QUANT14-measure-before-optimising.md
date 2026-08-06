---
id: QUANT14
title: "Restructure the measurement layer: exposure as a first-class output, and exit distance separated from position size"
status: in_progress
priority: critical
owner: unassigned
category: quantlab
initiative: liquid-ml-research
created: 2026-08-04
updated: 2026-08-04
tags: [architecture, money-management, measurement, portfolio]
depends_on: [QUANT13]
blocks: []
---

## The diagnosis this comes out of

Nine hypothesis families were tested over eight months. Every one of them was
either unprofitable or unprofitable out of sample, and the natural conclusion
was that none of them had edge. QUANT13 showed that conclusion was not
supported, because the measurement instrument was defective in two specific,
demonstrable ways:

1. **Exposure was never recorded.** The lab was running at **4.8-8.9% average
   exposure**, in the market 46% of the time. Every published return was
   therefore roughly an order of magnitude smaller than the same strategy
   fully invested would produce — and it was read, by everyone including the
   agents generating it, as though it were comparable to buy-and-hold. Nobody
   could see this. It took a bespoke diagnostic script to discover, eight
   months in.
2. **`stop_loss_pct` controlled two independent decisions.** It was the exit
   trigger *and* the denominator of `risk_budget / distance`. Widening it from
   5% to 20% moved the exit and simultaneously cut notional to a quarter. The
   consequence is not merely that results were hard to attribute — an entire
   region of the configuration space **did not exist**. "Hold a wide stop at
   full size", the single most standard idea in position sizing, was
   unrepresentable.

The pattern connecting them: **this lab was built to optimise before it could
measure.** It had a mutation schedule, a walk-forward instrument, a champion
ledger and a public dashboard, all operating on a number whose scale nobody
could interpret and a parameter space with a hole in it. That is why nine
families produced no conclusions: the results were not wrong, they were
*unreadable*.

## What changed

### Exposure is a first-class output of every run

`PortfolioEvaluation` now carries `average_exposure`, `peak_exposure` and
`time_in_market`, computed in one pass from the equity curve the run already
emits, so they cannot drift from the equity they describe. They are persisted
on both `portfolio_backtest_runs` and `forward_portfolio_runs` and returned in
the Phase-1 report next to the return.

Historical rows get `NULL`, not `0`. Those runs genuinely did not measure this,
and a zero would be a claim they did.

Also added: `MoneyManagement.exposure_calibration`, which reports how many
assets a policy needs before it reaches full investment
(`ceil(1 / maximum_position_fraction)`). This is the number that makes
`maximum_position_fraction=0.2` mean "fully invested" across five assets and
"20% invested" on one. The Phase-1 report now states the ratio of assets
actually evaluated to that figure, so a scope/policy mismatch is visible in
the result rather than hidden inside it.

### Exit distance and sizing distance are separate parameters

`risk_distance_pct` is the sizing denominator. It defaults to `None`, meaning
"use `stop_loss_pct`" — so **every policy already stored in the database keeps
its exact previous behaviour**, and no historical result is retroactively
altered. Both sizing call sites (`LongOnlyPortfolioBacktester` and
`LongOnlyExecutionBacktester`) route through `policy.sizing_distance`, and both
constructors validate it, so an invalid override fails at construction rather
than mid-run.

The unlock is covered by `test_a_wide_stop_can_now_keep_full_size`, which was
sabotage-verified: reverting the split makes it fail with 45.5% versus 12.3%
exposure, a 3.7x difference. The old coupling is *also* pinned, by
`test_a_wide_stop_alone_shrinks_position_size`, so the behaviour that caused
the confusion is documented rather than merely removed.

## Why this ordering, and what was deliberately not done

The tempting next move after QUANT13's +350% Phase-1 result was to keep
searching — genetic algorithms, neural nets, more families. That was declined
on the evidence: a search over a space with a hole in it, scored by a number
whose scale is invisible, generates more results of exactly the kind this lab
already has too many of. **Measurement first, then optimisation.**

Explicitly **not** changed here:

- **No global policy change.** `orchestrator-manager/config/default.json` is untouched. The tuned
  QUANT13 money management lives in that strategy's own
  `money_management_json`, so no other family's stored policy moves.
- **The 25% drawdown abort is untouched and stays untouchable.** Every sweep
  disqualifies rows that trip it rather than relaxing it. Stage 4 of QUANT13
  was rejected on exactly this basis.
- **The deleverage ramp is not removed.** It costs ~4.2 points and prevented
  nothing measurable, but it is a risk control, removing it is the operator's
  call, and it has been put to them with the evidence rather than decided
  quietly.
- **No historical result is recomputed or restated.** The old numbers stand as
  what those runs produced; what changes is that new ones are interpretable.

## What this makes possible next, in order

1. **Re-adjudicate the earlier families.** Several were measured through the
   defective instrument on a scope its policy did not fit — S00826
   (supertrend_adx, 15m, three majors, -14.12%) most clearly. "No edge" is not
   a fair verdict on those yet. This is the highest-value work remaining and
   it will invalidate part of the published ledger, which is the correct
   outcome rather than a cost to avoid.
2. **Baseline-contrast evaluation.** Every Phase-1 run should report its
   difference against the H-SMARSI-001 baseline on identical bars, costs and
   policy — a control, not just a benchmark. The baseline's result per
   (interval, symbol set, policy) triple is cacheable, so this costs one extra
   run per scope rather than one per candidate. Without it, "+36.97%" still has
   no interpretation.
3. **ATR-scaled distances.** Now that the exit and sizing distances are
   separate, either can become `k * ATR` independently. A fixed 20% is
   suspiciously asset-specific and almost certainly will not transfer.

## Acceptance criteria

- Exposure metrics present on every new run, `NULL` on historical ones.
- Stored policies produce bit-identical results to before the split.
- The unlock test fails if the split is reverted (verified).
- The mandated 25% abort unchanged.
- No global policy or historical result altered by this task.

## What the split bought, measured

Stage 5 is the first search over the *plane* of (exit distance, sizing
distance). The old single-parameter design could only reach the diagonal.
Signal held at the QUANT13 winner, pre-2026 BTCUSDT hourly, 73,284 bars:

| exit stop | sizing distance | return | max DD | trades | avg exposure | in market | return/exposure |
|---|---|---|---|---|---|---|---|
| 0.05 | 0.02 | -23.29% | 25.25% | 189 | 5.8% | 34.3% | -4.03 **ABORTED** |
| 0.05 | 0.20 | -10.71% | 18.44% | 557 | 4.6% | 45.3% | -2.34 |
| 0.10 | 0.10 | +18.79% | 19.35% | 396 | 8.7% | 45.4% | 2.16 |
| 0.20 | 0.10 | +66.11% | 14.11% | 349 | 8.6% | 45.5% | 7.72 |
| **0.20** | **0.20** | **+31.58%** | 7.26% | 349 | 4.6% | 45.5% | 6.92 |
| **0.35** | **0.10** | **+68.95%** | 14.11% | 344 | 8.5% | 45.5% | **8.07** |

**Best reachable before the split (diagonal): +31.58%, score 0.243.
Best reachable after: +68.95%, score 0.548.** 2.2x the return and 2.3x the
score, from making a configuration expressible rather than from tuning. The
diagonal was the wrong line through the space.

Three findings that only exposure reporting makes visible:

1. **`return_per_exposure` of 8.07**: +68.95% from 8.5% average capital
   deployed, in the market 45.5% of the time. Per unit of capital at risk this
   is a strong result, and it was previously invisible. It also means the
   headline return understates the signal and overstates the portfolio.
2. **`maximum_position_fraction` is the binding constraint, not the sizing
   distance.** Sizing distances 0.02, 0.05 and 0.10 are bit-identical
   (66.03/66.03/66.11) because the 0.20 cap binds first. This retroactively
   explains why QUANT13 stage 4's `risk_per_trade` sweep saturated — it was
   turning a dial downstream of the real limit. Every prior discussion of
   sizing in this lab was aimed at the wrong parameter.
3. **Wide exits dominate monotonically**: 0.05 aborts, 0.10 gives +18.79%,
   0.20 gives +66.11%, 0.35 gives +68.95%. The lab's default 5% is the worst
   cell in the entire grid, and until now it was the only one ever used — by
   every family, in every published result.

The monotonic ordering is itself a warning, not just a win: a parameter whose
best value sits at the edge of the tested range has not been bracketed, and
"wider is always better" eventually degenerates into "no stop at all", which
is a different strategy wearing a stop's name. The range needs extending
until the curve turns over before 0.35 is treated as a finding rather than a
boundary artifact.

## Stage 6: selecting at the deployment scope, as the new decision requires

The same plane, swept directly on the declared five-asset basket. 332,225
hourly bars per cell, 25 minutes total — the cost the
select-at-deployment-scope decision accepts.

| exit | sizing | cap | return | max DD | trades | exposure | in market | ret/expo |
|---|---|---|---|---|---|---|---|---|
| 0.10 | 0.10 | 0.10 | +43.48% | 25.17% | 658 | 7.9% | 47.1% | **ABORTED** |
| 0.10 | 0.10 | 0.20 | -20.48% | 25.05% | 201 | 7.9% | 38.3% | **ABORTED** |
| 0.10 | 0.20 | 0.10 | +40.39% | 25.16% | 657 | 7.8% | 47.1% | **ABORTED** |
| 0.10 | 0.20 | 0.20 | +40.39% | 25.16% | 657 | 7.8% | 47.1% | **ABORTED** |
| 0.20 | 0.10 | 0.10 | +360.02% | 20.85% | 1,360 | 11.7% | 59.0% | 30.66 |
| 0.20 | 0.10 | 0.20 | +272.04% | 25.29% | 450 | 12.3% | 47.1% | **ABORTED** |
| 0.20 | 0.20 | 0.10 | +350.09% | 20.38% | 1,362 | 11.8% | 59.0% | 29.77 |
| 0.20 | 0.20 | 0.20 | +350.09% | 20.38% | 1,362 | 11.8% | 59.0% | 29.77 |
| **0.35** | **0.10** | **0.10** | **+433.88%** | **19.06%** | **1,281** | 11.4% | 58.9% | **38.09** |
| 0.35 | 0.10 | 0.20 | +289.66% | 25.47% | 406 | 12.2% | 47.2% | **ABORTED** |
| 0.35 | 0.20 | 0.10 | +417.69% | 19.25% | 1,283 | 11.4% | 58.9% | 36.62 |
| 0.35 | 0.20 | 0.20 | +417.69% | 19.25% | 1,283 | 11.4% | 58.9% | 36.62 |

**6 of 12 cells are legal.** The winner, exit 0.35 / sizing 0.10 / cap 0.10 at
**+433.88% and 19.06% drawdown**, beats the QUANT13 configuration on *both*
axes — 84 points more return at 1.3 points less drawdown — and is exactly the
shape the old single-parameter design could not express: a wide exit with
exposure governed by the position cap rather than by the stop distance.

Three structural readings:

1. **Every exit=0.10 cell aborts.** A tight exit is not merely suboptimal at
   this resolution, it is fatal, and it fails by *breaching the risk limit* —
   the parameter installed to control risk was the one destroying capital.
2. **Which term binds depends on the sizing distance.** At sizing 0.20 the
   `risk_budget / distance` term binds and the cap is inert (0.10 and 0.20 give
   bit-identical results, twice). At sizing 0.10 that term is larger, so the cap
   binds and its value matters — cap 0.20 aborts where cap 0.10 survives. This
   is why sweeping these three dials as if independent was wrong: exposure is
   `min(cap, risk_budget/sizing)` and only one of them is live at a time.
3. **Legality is not monotone in return.** +289.66% aborts while +360.02%
   does not. Ranking candidates by return alone would select an illegal
   configuration, which is what the abort exists to catch and what a
   score-ordered leaderboard would have hidden.

## Stage 7: bracketing the exit rather than adopting a boundary value

Stage 6's winner sits at the largest exit distance tested, so it is a boundary
artifact until shown otherwise. A parameter whose best value is the edge of its
range has not been measured, it has been truncated — and "wider is always
better" has a degenerate limit: a stop wide enough never to fire is not a stop,
it is a different strategy exiting on signal alone while carrying a risk
control in name only.

Stage 7 therefore extends the exit range to 0.99 with sizing and cap pinned to
the winner, at basket scope. Either the curve turns over and 0.35 is a real
optimum, or it does not and the honest conclusion is that this system has no
working stop — which will be stated plainly rather than left implicit behind a
large number.
