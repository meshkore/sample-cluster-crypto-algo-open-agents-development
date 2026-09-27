---
id: S10-7
title: "F. Training: an environment over the frozen backtester's ledger, golden-tested"
status: backlog
priority: high
owner: unassigned
profile: developer
category: trading-system
initiative: system-ten-conditioned-rl
created: 2026-09-27
updated: 2026-09-27
tags: [system10, environment, phase-f]
depends_on: [S10-3, S10-6]
blocks: [S10-8]
---

> Read `.meshkore/context/system10-design.md` before starting. It is the plan this task is one piece of, and it carries
> the laboratory's standing rules under "Our conditions" and the kill conditions under section 7.

## The ask

The policy needs somewhere to act. That somewhere must charge exactly what the laboratory
charges and account exactly as the backtester accounts, or its reward is a fiction.

## What to build

`system010_conditioned_rl/env.py`:

- `reset(year, seed)` opens a $100,000 account on 1 January of a research year; `step(a)`
  applies the action at the NEXT bar's open through the backtester's own fill, cost and
  impact code (called, not copied), and returns the state (feature window + book state +
  regime id), the reward and `done` at year end.
- Reward per the design section 4: delta log equity - lambda * delta drawdown-from-peak -
  costs; terminal Q. lambda is a constructor argument.
- Outside R the policy is not consulted: the environment manages open positions with 06's
  shipped exit rule and advances. Inside R the action set is
  `{abstain, enter half, enter full, hold, exit}`, long-only, three slots.
- Deterministic under a seed; vectorised across symbols where the backtester allows.
- **Golden test**: replay 06's champion decisions through the environment for one research
  year and assert the equity curve equals the backtester's own `launch.per_year` result to
  the cent. A mismatch is a bug in the environment, never a tolerance.

## Done when

The golden test passes for two research years, a random policy runs a year in under the
time budget the task notes, and `docs/SUMMARY.md` *What it is* describes the environment.
