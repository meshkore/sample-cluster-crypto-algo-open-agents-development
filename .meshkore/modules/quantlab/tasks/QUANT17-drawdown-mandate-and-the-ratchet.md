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

## Acceptance criteria

- No stored policy or historical result moves: `drawdown_basis` defaults to peak.
- The ratchet cannot return: pinned by a test, sabotage-verified.
- Every gate applies the mandate its run was measured under.
- The chart never draws a line through inactivity.
