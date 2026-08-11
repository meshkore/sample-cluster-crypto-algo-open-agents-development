---
id: QUANT27
title: "Wire the read-only Codex advisor into the public research loop"
status: in_progress
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

- [ ] The loop constructs the Codex reviewer only when explicitly enabled.
- [ ] Its executable, authentication failure, timeout and unusable reply are
      recorded without leaking credentials or billing details.
- [ ] Its validated review is recorded and mirrored to the cluster under its
      own handle.
- [ ] Inbound cluster messages reach the review briefing as untrusted evidence.
- [ ] Tests cover the enabled, unavailable and cluster-publication paths.
