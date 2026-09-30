---
id: S10-6
title: "E. Conditions: find the causal region that holds 80% of the oracle's best trades, and price its coverage"
status: done
priority: high
owner: unassigned
profile: developer
category: trading-system
initiative: system-ten-conditioned-rl
created: 2026-09-27
updated: 2026-09-30
tags: [system10, region, feasibility, phase-e]
depends_on: [S10-4]
blocks: [S10-7]
---

> Read `.meshkore/context/system10-design.md` before starting. It is the plan this task is one piece of, and it carries
> the laboratory's standing rules under "Our conditions" and the kill conditions under section 7.

## The ask

The operator's central idea: *"apply it only in the places and above all the CONDITIONS in
which 80% of the best trades have occurred... the window has to be wide enough to train and
to execute."* This task finds that region, states it so a person can read it, and reports
what it costs in coverage - before a single policy is trained.

## What to build

`system010_conditioned_rl/region.py` and `research/system10/tools/conditions.py`:

1. **The best trades.** Run 06's zigzag oracle over the research years (to 2025-12-31) and
   take the top quantile of swings by net return after 0.30% (the quantile is a parameter;
   report at 50%, 30%, 20%).
2. **The conditions.** Fit, on years up to N-1 for each N, an interpretable causal predicate
   over the frozen feature registry (a shallow tree or threshold set) that covers at least
   80% of those swings. Print it as rules. The current gates (trend, breadth, meta, fear)
   are **version zero** and are scored first, so the learned region is measured against
   them and not against nothing.
3. **Coverage.** Per year: fraction of bars inside R, fraction of top swings inside R, and
   the capturable return inside R under 06's shipped exit rule (not the oracle cap).
   Report the composition confound (nine symbols in 2018, twelve in 2022) explicitly.
4. **Feasibility, inside R.** The block bootstrap from
   `research/system08/experiments/feasibility.py` on the capturable daily returns inside R:
   `P(year >= +20%)`, `p05`, and the probability of the worst observed year. This is the
   gate in the design's section 7: if it fails, say so to the operator before S10-7.
5. **The operator's worry.** If the 80% region covers too little of the tape for a
   three-slot book to deploy, widen R to the smallest region where the bootstrap passes and
   report the fraction of best trades given up. Both regions are recorded.

No 2026 bar is loaded. Output: `research/system10/rnd/conditions_<date>.json` and a section
in `docs/RESULTS.md`; the rules themselves go into `docs/SUMMARY.md` *What it is*.

## Done when

The region is printed as rules, coverage per year is tabled, the bootstrap inside R is
read against +20% and the answer is in front of the operator, and version zero (the gates)
is scored on the same table.
