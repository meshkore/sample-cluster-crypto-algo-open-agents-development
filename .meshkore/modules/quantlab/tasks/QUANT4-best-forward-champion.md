---
id: QUANT4
title: "Persist the best valid 2026 forward champion"
status: pending
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

Maintain one immutable best-forward champion chosen only from completed,
promoted 2026 forward evaluations that obey the 25% drawdown limit. Compare
each new candidate with the stored champion using a documented forward-only
ranking. Replace it only when it is strictly better; otherwise preserve the
previous champion and all of its signal criteria, execution/money-management
definition, equity curve, asset results and trade ledger.

## Acceptance criteria

- No Phase-1-only or rejected strategy can appear as Best forward.
- The replacement decision and compared scores are persisted and auditable.
- The dashboard's Best forward view remains populated while new strategies run.
- Tests cover initial champion, non-replacement, replacement and restart
  persistence.
