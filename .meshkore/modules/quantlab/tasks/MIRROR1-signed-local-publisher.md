---
id: MIRROR1
title: "Build a signed local-to-public state publisher"
status: done
priority: high
owner: codex-lead
category: quantlab
initiative: public-state-mirror
created: 2026-08-01
updated: 2026-08-01
completed_at: 2026-08-01T15:14:00Z
resolved_by: codex-lead
resolved_by_conv: public-state-mirror
commit_shas: [d4f734a]
tags: [cloudflare, observability, public, security]
depends_on: []
blocks: [MIRROR2]
---

## Scope

Add a bounded, background publisher to the local daemon. It sends only a
sanitised dashboard snapshot with a bearer secret; it never sends databases,
credentials, local paths or agent logs.

## Done when

Publisher behaviour is configurable, non-blocking, covered by tests, and its
output contract is consumed by the public viewer.

## Resolution

The local publisher is opt-in, uses a secret from its process environment and
publishes a bounded, redacted snapshot in a dedicated daemon thread. Regression
tests verify redaction, request authentication and the disabled default.
