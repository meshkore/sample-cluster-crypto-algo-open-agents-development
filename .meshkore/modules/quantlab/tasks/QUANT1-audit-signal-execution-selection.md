---
id: QUANT1
title: "Audit signal, execution and selection against the observed forward loss"
status: completed
priority: critical
owner: codex-lead
category: quantlab
initiative: liquid-ml-research
created: 2026-08-01
updated: 2026-08-01
tags: [research, liquidity, money-management, forward-testing]
depends_on: []
blocks: [QUANT2, QUANT3]
---

## Scope

Identify whether the loss originates in signal generation, universe selection,
portfolio execution, risk constraints, costs, selection bias or dashboard
labelling. Define the minimum evidence required before another strategy enters
forward evaluation.

## Findings

- S00200 was `REJECT` in the experiment record but had reached forward because
  Phase 2 only checked positive portfolio return. This is fixed: Phase 2 and
  the public best-forward view now require `PROMOTE`/`CHAMPION` evidence and a
  Phase-1 drawdown below 25%.
- The three original signal families emit binary 0/1 targets. Their apparent
  confidence cannot support confidence-weighted sizing or claim ML behavior.
- The previous all-USDT universe lacked a liquidity/capacity gate. The next
  task owns the model-led replacement and complete point-in-time liquidity
  evidence.
