---
id: S10-11
title: "H. Forward: the sealed 2026 reading, exactly once, on the operator's word"
status: backlog
priority: high
owner: unassigned
profile: developer
category: trading-system
initiative: system-ten-conditioned-rl
created: 2026-09-27
updated: 2026-09-27
tags: [system10, sealed, 2026, phase-h]
depends_on: [S10-10]
blocks: [S10-12]
---

> Read `.meshkore/context/system10-design.md` before starting. It is the plan this task is one piece of, and it carries
> the laboratory's standing rules under "Our conditions" and the kill conditions under section 7.

## The ask

*"Forward testing segun nuestras condiciones"*: 2026 is read once, after the exams and
the odds, on the operator's word, and recorded whatever it says.

## What to do

1. Confirm in writing in the task note: S10-10 passed 2-of-2, the ratio spread does not
   straddle 1.0, and the operator has said the word. All three, or this task does not run.
2. Run the sealed year with `--forward` for the configuration S10-10 named, fresh
   $100,000 on 2026-01-01, through the cutover date of the live trader (2026-09-17 09:00
   UTC); the live book carries the record from there.
3. Record: return, maximum drawdown, Q, trade count, average trade size, versus 06's
   sealed +25.71% @ 22.1% and versus buy-and-hold. Both configurations if two were named.
4. `docs/RESULTS.md` sealed era filled; `trading-system/systems/README.md` row 010 gets its
   sealed figure and verdict; `docs/context.json` `results.sealed_2026`.
5. The reading is appended to `research/system10/rnd/sealed_readouts.jsonl` so
   `tools/quality.py` can rank it beside 06's readings.

## Done when

The sealed figure is on the record in all four places, positive or negative, and the
initiative's next step is stated: proceed to S10-12 or stop with the finding.
