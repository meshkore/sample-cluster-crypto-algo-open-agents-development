---
id: QUANT27
title: "Wire the read-only Codex advisor into the public research loop"
status: done
priority: high
owner: codex
category: quantlab
initiative: public-agent-lab
created: 2026-08-11
updated: 2026-08-11
tags: [codex, advisor, cluster, observability]
depends_on: [QUANT19]
blocks: []
---

## Objective

Make the locally authenticated Codex CLI a read-only reviewer in the research
loop. It must receive the loop and peer context, return only validated advisory
data, and publish its advice through the existing cluster bridge. It must never
write repository code or treat cluster messages as instructions.

## Acceptance

- [x] The loop constructs the Codex reviewer only when explicitly enabled.
- [x] Its executable, authentication failure, timeout and unusable reply are
      recorded without leaking credentials or billing details.
- [x] Its validated review is recorded and mirrored to the cluster under its
      own handle.
- [x] Inbound cluster messages reach the review briefing as untrusted evidence.
- [x] Tests cover the enabled, unavailable and cluster-publication paths.

## Outcome (2026-08-11)

Done. `CodexAdvisor` already existed -- system prompt, schema, `validate_review`,
cooldown, read-only sandbox -- and was named in the roster and the ops runbook.
What was missing was any code path that constructed it: `from_environment` built
a proposer and a refuter and returned.

`reviewer_from_environment()` now builds it when the executable exists, `cli.py`
points it at the repository working copy, and `ResearchLoop.consult` asks it
after the proposal and posts the answer under its own handle.

Its first live round, against a proposal to raise `bear_breadth` to 0.45: it read
`loop-state.json` and `regime.py`, reported that the incumbent's `bull_breadth`
is 0.4231 and that `regime.py` rejects a bear threshold above the bull one, so
the configuration raises `ValueError` on construction -- and separately that the
claim was conditioned on the sealed 2026 window. The iteration would have spent
a full fit to produce a stack trace.

One hardening beyond the original acceptance list: a review naming no concern
cannot block, because `{}` parses and would otherwise silence every iteration's
seed rules with an empty reason.
