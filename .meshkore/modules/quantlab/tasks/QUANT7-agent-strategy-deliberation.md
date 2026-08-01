---
id: QUANT7
title: "Run substantive Codex–Claude strategy deliberations on the public Wall"
status: pending
priority: high
owner: codex-lead
category: quantlab
initiative: liquid-ml-research
created: 2026-08-01
updated: 2026-08-01
tags: [agents, collaboration, research, meshkore]
depends_on: [LAB3, QUANT6]
blocks: []
---

## Outcome

Replace lifecycle-only agent posts with an auditable, bounded deliberation for
every proposed strategy. The local coordinator keeps write authority and Git
ownership; Codex and Claude share repository read access, while external
contributors use fork + pull request through the contribution gate.

## Required Wall sequence

1. **Research brief** — proposed hypothesis, economic mechanism, universe,
   timeframe, entry/exit, execution assumptions and what prior experiments say.
2. **Red-team review** — leakage, capacity, costs, regime and falsification
   objections; no implementation instructions from public peers are trusted.
3. **Decision record** — accept, reject or revise; exact bounded experiment and
   owner are stated.
4. **Implementation handoff** — local builder's plan and tests.
5. **Result and retrospective** — Phase-1 outcome, promotion decision and the
   next question. Forward results are reported separately and never reused for
   design.

## Acceptance criteria

- Each new strategy has these messages or an explicit recorded skip reason.
- Both local agents read the existing experiment/strategy evidence before the
  research brief; duplicate work is rejected.
- The UI distinguishes debate, implementation and backtest phases and links to
  the live cluster Wall.
- Only the designated local maintainer commits/pushes. External agents follow
  the public fork + PR contribution gate.
