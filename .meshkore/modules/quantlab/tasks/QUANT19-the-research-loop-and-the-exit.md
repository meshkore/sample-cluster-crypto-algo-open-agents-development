---
id: QUANT19
title: "The research loop, and the finding that the exit is what loses money"
status: in_progress
priority: critical
owner: unassigned
category: quantlab
initiative: liquid-ml-research
created: 2026-08-05
updated: 2026-08-05
tags: [process, ledger, observability, exits, time-stop, cluster]
depends_on: [QUANT18]
blocks: []
---

## What the operator asked for

Stop running one-off experiments. Put the research on a formal loop that never
stops: frame a falsifiable hypothesis, consult the cluster, implement, backtest
pre-2026, open 2026 once, measure what went wrong, adjust, repeat. Keep a
register of everything tried so the branch's evolution is legible, and keep
questioning every piece of the four-module model rather than drifting to a new
idea whenever one gets hard.

Also: separate the machinery from the laboratory. The public repository should
contain the trading system and its branches; the orchestrator, the loop and the
cluster bridge belong somewhere else.

## The split

    other/
      loop-crypto-algorithm/     public repo — the trading system
      quantlab-orchestrator/     the loop, the ledger, the cluster bridge

The orchestrator holds `LOOP.md` (seven stages, ten invariants), an append-only
hypothesis ledger, a ranked backlog, and the Wall bridge. It holds no strategy
code. The ten hypotheses already settled were back-filled into the ledger so
iteration 11 did not start from an empty history.

The loop is driven from the operator's visible Claude Code session on a
ten-minute tick rather than as a detached headless agent. An unattended process
that edits a trading repository and pushes commits is not something to start in
the background, and the operator asked to be able to watch it.

## H-011 — the anatomy of the 2026 loss

We had a number (−11.04%) and no idea where it came from. Decomposing it, on
2026 and on the 2022-2025 holdout with the same instrument:

| exit reason | 2026 | holdout |
|---|---|---|
| `TAKE_PROFIT` | 86 trades, +40,244, 100% win | 1,442 trades, +1,485,318 |
| `SIGNAL_EXIT` | 128 trades, −46,716, **2% win** | 858 trades, −806,635, **10% win** |
| `STOP_LOSS` | 3 trades, −3,853 | 179 trades, −600,257 |

The entries are not the problem, and neither is the regime label. Nearly 40% of
2026 trades reached take-profit at +12.62%. What loses the money is the exit:
when a position does not resolve quickly, the signal keeps holding it and gives
back about 10% per trade.

Bucketed by realised holding period the structure is identical in both eras:

| held | 2026 | holdout |
|---|---|---|
| 0-3 days | **+19,716** (66% win) | **+902,068** (85% win) |
| 3-7 days | −20,988 (18%) | −148,192 (51%) |
| 7-21 days | −10,172 (21%) | −620,621 (30%) |
| 21-60 days | +778 | −54,851 (30%) |

Unlike QUANT18's volume signal, whose sign flipped between 2017-2021 and
2022-2025, this shape does not flip. It is one of the few properties measured in
this project that holds across all three windows.

The decomposer had a defect of its own on the first run: it read a non-existent
`exposure` key off the equity curve and reported 0.0% monthly exposure against a
21.22% average. Fixed by deriving the invested fraction from cash and equity.

## H-012 — the time stop

`MoneyManagement.maximum_holding_days` closes a position once it has aged out,
regardless of the signal. It is checked *after* the signal exit so the
`TIME_STOP` count measures positions the signal still wanted to hold — the ones
the rule is actually overriding. Both exit at the open, so the ordering changes
attribution and never PnL. `None` is the default, so no stored policy moves.

The caveat is written into the code: bucketing by realised duration is
conditional on outcome. Cutting at day three truncates a loser at its day-three
loss; it does not convert it into a winner. The rule therefore had to be swept,
not assumed.

Five tests, each sabotage-verified — firing one bar late, the branch made a
no-op, and the ordering swapped all produce failures.

## Acceptance

- [x] Orchestrator split out of the public repo, with the ledger seeded
- [x] Ten-minute tick that reclaims a dead iteration instead of losing it
- [x] H-011 recorded: the exit is the defect, and the shape transfers across eras
- [x] Time stop implemented, defaulting to off, with sabotage-verified tests
- [ ] Time stop swept on the holdout with the de-leverage ramp disabled
- [ ] 2026 opened once, only if the holdout gate is cleared
