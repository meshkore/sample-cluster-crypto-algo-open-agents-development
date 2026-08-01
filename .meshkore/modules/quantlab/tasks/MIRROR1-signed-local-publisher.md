---
id: MIRROR1
title: "Build a signed local-to-public state publisher"
status: in_progress
priority: high
owner: codex-lead
category: quantlab
initiative: public-state-mirror
created: 2026-08-01
updated: 2026-08-01
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
