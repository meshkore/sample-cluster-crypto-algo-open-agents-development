---
id: QUANT7
title: "Run substantive Codex–Claude strategy deliberations on the public Wall"
status: done
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

## Delivered

`src/quantlab/deliberation.py` builds the five-part Wall sequence from local
records: research brief (`codex-lead`) when a strategy enters evaluation, then
red-team review (`claude-code-validator`), decision record and result with
retrospective (`quantlab-orchestrator`) when Phase 1 finishes. Committee critics
now publish their actual advisory as an implementation handoff instead of a
lifecycle ping. `autonomous.wall_deliberation_enabled` gates the whole surface;
messages are clipped to 3,500 characters. Covered by `tests/test_deliberation.py`.

## Root cause found while delivering this

The Wall was not merely thin, it was disconnected. `cluster_update()` shells out
to `node scripts/meshkore_post.mjs`, and the LaunchAgent `PATH` contained no
node, so every post since the daemon was installed raised `FileNotFoundError`
into a bare `except OSError: return`. The daemon now resolves node from config,
`PATH` and the known Homebrew/nvm prefixes, records a `cluster` WARNING when it
cannot, and `service.install` writes the newest nvm bin into the agent `PATH`.

## Still open

Peer replies remain deliberately unread by the runtime. A human reads the Wall
and turns useful objections into tasks or pull requests; wiring public text into
a model prompt would break the contribution threat model.
