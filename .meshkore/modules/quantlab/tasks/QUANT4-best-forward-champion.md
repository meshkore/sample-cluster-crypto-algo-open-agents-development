---
id: QUANT4
title: "Persist the best valid 2026 forward champion"
status: done
priority: high
owner: codex-lead
category: quantlab
initiative: liquid-ml-research
created: 2026-08-01
updated: 2026-08-01
tags: [forward-testing, champion, dashboard, audit]
depends_on: [QUANT2, QUANT3]
blocks: []
---

## Outcome

Maintain one persistent best champion chosen from completed evaluations that
obey the 25% drawdown limit. Compare each new candidate with the stored
champion using a documented, evidence-first ranking. Replace it only when it is
strictly better; otherwise preserve the previous champion and all of its signal
criteria, execution/money-management definition, equity curve, asset results
and trade ledger.

## Acceptance criteria

- The replacement decision and compared scores are persisted and auditable.
- The dashboard's best-strategy view remains populated while new strategies run.
- Tests cover initial champion, non-replacement, replacement and restart
  persistence.

## Delivered

`src/quantlab/champion.py` owns `champion_records` (one materialised champion
with its complete public evidence) and `champion_decisions` (every comparison,
replaced or not). `AutonomousService.publish_champion()` re-ranks after each
completed Phase-1 and forward evaluation and at service start, so the record is
rebuilt from evidence already on disk. `DashboardData.snapshot()` serves it as
`best_strategy` + `champion_record`, and `public_state` mirrors it.

Ranking is evidence-first: a completed 2026 forward run under 25% drawdown
always outranks Phase-1 historical evidence, and within one class the score is
`return - maximum drawdown`. Criteria 14 to 16 in `SYSTEM_CRITERIA.md` bind it.

Deviation from the original wording: the champion is no longer forward-only.
Requiring `experiments.status IN ('PROMOTE','CHAMPION')` left the public view
permanently blank — all 316 recorded experiments are `REJECT` even though nine
2026 forward runs exist. The view now falls back to the best eligible Phase-1
backtest and labels it as historical evidence, which keeps the public surface
populated without ever presenting Phase-1 numbers as forward-validated.
