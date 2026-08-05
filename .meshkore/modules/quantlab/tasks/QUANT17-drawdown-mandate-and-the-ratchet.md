---
id: QUANT17
title: "The drawdown mandate: 25% of the deposit, not 25% from the peak"
status: in_progress
priority: critical
owner: unassigned
category: quantlab
initiative: liquid-ml-research
created: 2026-08-05
updated: 2026-08-05
tags: [risk, mandate, money-management, measurement, ui]
depends_on: [QUANT16]
blocks: []
---

## The operator's mandate

"I deposit 100,000 and never want to lose more than 25% of it. If that happens
the algorithm is worthless and must be thrown away. But if it made 300,000 and
gives back 150,000, that is not a problem for me."

That is a different rule from the one this laboratory had been enforcing, and
the difference turned out to be worth more than every strategy change made so
far.

## What the operator spotted, and what it actually was

The equity chart for S00852 ran to 2025 with a **flat line from mid-2021**. It
was not a cash position. `max_drawdown` was measured from the running PEAK, and
the de-leverage ramp was driven by the same number, so:

1. equity falls ~24.7% below the 2021 peak,
2. the ramp scales the risk budget to ~2% of normal,
3. every candidate position lands under `minimum_position_fraction`,
4. nothing opens, so equity cannot grow,
5. so the peak never updates and the drawdown never shrinks.

**A one-way ratchet.** S00852 opened its last position on **2021-05-19** and
then held nothing for four and a half years while reporting itself legal. The
"+1480%" was earned by mid-2021 and frozen. Verified directly: 941 trades, last
exit 2021-05-19, `open_positions == 0` on every subsequent bar.

## The fix, measured

`drawdown_basis` is now an explicit policy field, `"peak"` or `"initial"`,
defaulting to `"peak"` so no stored policy moves. `config/default.json` sets
`"initial"` with the limit back at 0.25 — the operator's mandate, stated where
mandates belong.

Same strategy, same parameters, pre-2026 386-asset daily, only the basis changed:

| basis | return | peak DD | **capital DD** | trades | last active |
|---|---|---|---|---|---|
| peak | +1480.02% | 24.72% | 2.96% | 941 | **2021-05-18** |
| **initial** | **+2836.21%** | 51.24% | **2.96%** | 2,232 | **2025-12-31** |

Nearly double the return, 2.4x the trades, and it keeps trading to the end of
history instead of dying in 2021. **The account never fell more than 2.96% below
the 100,000 deposit under either basis** — the ratchet was not protecting
anything, it was destroying compounding.

Walk-forward went from **not eligible** (drawdown breach in 1 of 12 folds) to
**eligible**, 7 of 12 folds profitable.

## One continuous account, which is the question that matters

The phase split restarts capital at 100,000 on 2026-01-01, which makes the
mandate bind far harder in 2026 than it would for a real account that entered
the year up many multiples. Run as one account, 2017 to today, 386 assets:

| basis | strategy | final equity | return | peak DD | capital DD | last active | |
|---|---|---|---|---|---|---|---|
| peak | router | $1,580,018 | +1480% | 24.72% | 2.96% | 2021-05-18 | legal, bricked |
| peak | control | $130,875 | +30.88% | 26.00% | 3.20% | 2019-07-15 | **ABORTED** |
| **initial** | **router** | **$2,813,877** | **+2713.88%** | 51.24% | **2.96%** | **2026-07-28** | **legal** |
| initial | control | $71,627 | -28.37% | 59.50% | 28.37% | 2020-03-11 | **ABORTED** |

100,000 becomes **$2.81M** across both bull and bear markets, still trading, and
never more than 2.96% below the deposit. The control is killed under either
mandate — it loses 28.4% of capital and trips the abort.

## Three gates that contradicted the new mandate

Changing the basis exposed three places that hardcoded the peak rule and would
have silently discarded the result:

1. `ForwardEvaluator.qualified_strategy` gated on `max_drawdown < 0.25`, so the
   best Phase-1 run this lab has produced was **not eligible for 2026 at all**.
2. `DashboardData._best_phase1` did the same, so the monitor fell back to
   showing S00848 at +350% as the high-water mark. It also *ranked* on
   `return - peak_drawdown`, penalising a run for a giveback its mandate allows.
3. Both now apply the basis each run recorded, and legacy rows with no basis
   keep the old rule exactly.

`capital_drawdown`, `drawdown_basis` and `last_active_timestamp` are persisted
on both phases and migrated as NULL on historical rows — those runs did not
measure this, and a zero would claim they did.

## The chart

Two changes, both requested:

- The equity line **stops where the strategy stopped deploying capital**.
  Everything past that was the engine emitting a point per bar while holding
  nothing, drawing years of flat line that read as deliberate patience.
- A **red marker** at the exit, with a dropline and a label distinguishing
  `drawdown abort` from `stopped trading`.

Truncation uses the engine's per-bar `active` flag, falling back to
`open_positions` for curves stored before the flag existed, and never truncates
a run it cannot judge.

## Is this a good mandate? The honest answer

It is coherent and it is the right call for compounding, with one real cost the
operator should own: **nothing now limits the giveback of profit.** The 51% peak
drawdown is permitted by construction. An account up 28x that round-trips to up
2x has broken no rule.

If that is uncomfortable, the natural refinement is a **ratcheting floor** — a
capital floor that steps up as profit is banked (say, never give back below 75%
of the highest month-end equity, or of realised gains), which keeps the
"let winners run" property while putting a moving floor under accumulated
profit. That is a mandate decision, not a tuning one, so it is put to the
operator rather than chosen quietly.

## What did NOT change

- 2026 is still never used for selection. The parameters were fixed on pre-2026
  evidence before the basis changed.
- The forward row for S00852 produced under the peak basis was **replaced**, not
  kept alongside: it described a superseded mandate. Forward-evaluation ledger
  is now **two** for this configuration (peak basis, then initial basis), and
  both returned the same -0.80%, because a run starting at 100,000 in a bear
  year never makes a new high and the two bases coincide.
- The abort remains a constraint on the search, never a parameter inside it.

## Result

**S00852, published:** Phase-1 pre-2026 **+2836.21%**, peak DD 51.24%, capital
DD **2.96%**, 2,232 trades, 126 assets, active to 2025-12-31, walk-forward
eligible at 7/12. Control contrast **+2864.6 points** with 8.3 points less peak
drawdown. Forward 2026 **-0.80%** at 6.60% peak DD.

Live on the monitor as the Phase-1 high-water mark.

## The ratcheting floor, chosen and measured (operator accepted the refinement)

`drawdown_basis="ratchet"` keeps the deposit floor and steps it up as profit is
made: `floor = 75% of deposit + banked_fraction x highest profit ever reached`.
The operator's own example fixes the shape -- "made 300,000, gave back 150,000,
no problem" is banking half.

Swept on one continuous 2017-today account:

| profit banked | final equity | last active | |
|---|---|---|---|
| 0% (deposit basis) | $2,813,877 | 2026-07-28 | |
| **10-30%** | **$2,813,877** | 2026-07-28 | **floor never binds -- free protection** |
| 40% | $2,813,023 | 2026-07-28 | costs $854 |
| 50% | $1,509,763 | 2023-07-25 | costs half the account |

**Banking 30% of peak profit costs nothing measurable** while putting a hard
floor under accumulated gains. Set to 0.30 -- comfortably inside the flat region
rather than at 0.40, one step from the cliff, per the bracketing lesson.

A bug was found and fixed on the way: the abort branch special-cased `"initial"`
and let everything else fall through to peak drawdown, so `"ratchet"` silently
behaved as `"peak"` and every banking fraction produced a bit-identical result.
That identity is what gave it away. The abort now asks the policy, and a
regression test asserts the three bases cannot agree.

## Bear-phase segmentation: the label was never enough

A bear market is not one environment. Pre-2026, inside BEAR regimes, mean
forward 30-day return of liquid assets:

| phase | forward 30d | n | hit |
|---|---|---|---|
| composite 30-50% below its high | **-32.30%** | 3,336 | **9%** |
| composite 50-70% below its high | -11.78% | 6,572 | 26% |
| **composite 70-100% below its high** | **+6.86%** | 10,728 | 52% |
| 0-60 bars into the bear | -12.71% | 7,480 | 33% |
| **240+ bars into the bear** | **+8.20%** | 3,194 | 52% |

The shallow, early part of a bear is the most destructive cell measured anywhere
in this laboratory -- a 9% hit rate over 30 days. The deep, late part is
positive. Same label, opposite expectation. Both measures are causal: elapsed
bars count backwards from now, and the composite's running high uses only closed
bars.

`_RegimeRouter` now refuses to participate in a bear until the composite is
`bear_min_depth` below its high **or** the episode is `bear_min_age` bars old --
either qualifies, because the 2018 bear got deep quickly and the 2022 one did
not. Thresholds sit on the measured band boundaries and are **not** bracketed;
they are parameters so a sweep can move them one at a time.

Measured on the continuous account: **$2,813,877 -> $2,910,657** with fewer
trades (2,264 -> 2,116). The gate earns its place before 2026 as well as in it.

## What it does in 2026, predicted from pre-2026 evidence alone

The 2026 bear sits ~40% below the composite high -- squarely in the -32.30%
band. The gate therefore stands aside, and the forward run is **+0.00% on zero
trades**, against the control's -23.82% and a -47.2% median asset.

That is worse than the +4.33% incumbent and better than everything else, and it
matters that the decision was made on pre-2026 evidence only: this is a
prediction that paid, not a fit. Standing aside is also the honest answer to
"long-only in a market where the median asset falls 47%".

## Still open: the breadth thrust

A Zweig-style thrust on the reference basket's own breadth series looks
promising and is NOT yet implemented, because the sample is too small to act on:

| thrust | signals | +30d | +90d |
|---|---|---|---|
| 40% -> 61.5% within 10d | 14 (4 in BEAR) | +10.64% | +19.98% |
| 30% -> 60% within 15d | 9 (4 in BEAR) | +17.30% | +29.07% |
| 20% -> 50% within 20d | 19 (6 in BEAR) | +5.25% | +25.01% |

Consistently positive across all four parameterisations, but 9-19 events in nine
years is the same "few independent observations" problem as cycle counting.
Recorded as the next lead, with its numbers, rather than shipped on n=14.

## Acceptance criteria

- No stored policy or historical result moves: `drawdown_basis` defaults to peak.
- The ratchet cannot return: pinned by a test, sabotage-verified.
- Every gate applies the mandate its run was measured under.
- The chart never draws a line through inactivity.
