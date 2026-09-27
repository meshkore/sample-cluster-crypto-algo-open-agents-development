---
id: S10-10
title: "G. Testing: two walk-forward exams (2024, 2025) and the odds priced against system 06"
status: backlog
priority: high
owner: unassigned
profile: developer
category: trading-system
initiative: system-ten-conditioned-rl
created: 2026-09-27
updated: 2026-09-27
tags: [system10, exam, walk-forward, phase-g]
depends_on: [S10-8]
blocks: [S10-11]
---

> Read `.meshkore/context/system10-design.md` before starting. It is the plan this task is one piece of, and it carries
> the laboratory's standing rules under "Our conditions" and the kill conditions under section 7.

## The ask

The laboratory's rule, bought with three lost sealed readings: a candidate needs 2-of-2
walk-forward exams before a sealed reading, and the odds are priced first.

## What to do

1. Exam 2024: policy trained on years to 2023, judged on 2024. Exam 2025: trained to 2024,
   judged on 2025. Four seeds each. Scored by the consistency law and by Q; drawdown
   beside every return; trade count and average trade size in money.
2. Against 06: the per-year growth-multiple ratio `(1+r_010)/(1+r_06)` for every research
   year and both exam years, per seed. Compare growth multiples, never differences of
   percentages (06 rule 8).
3. **Price the odds.** If the ratio spread across seeds and years straddles 1.0, no sealed
   reading is booked; the result is recorded as research. If both exams pass and the spread
   sits above 1.0, the odds are written down and the operator is asked for the word.
4. Both numbers, always: the maximum-profit configuration and the optimal one on Q.
5. `docs/RESULTS.md` two-era table filled for the research era; `docs/SUMMARY.md` rows.

## Done when

Both exams are tabled per seed, the ratio spread is stated, and the recommendation to the
operator is one of exactly two sentences: "book the sealed reading" or "do not".
