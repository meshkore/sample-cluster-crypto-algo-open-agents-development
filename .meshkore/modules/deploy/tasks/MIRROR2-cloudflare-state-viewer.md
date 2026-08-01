---
id: MIRROR2
title: "Deploy the public Cloudflare state viewer"
status: pending
priority: high
owner: codex-lead
category: deploy
initiative: public-state-mirror
created: 2026-08-01
updated: 2026-08-01
tags: [cloudflare, worker, public, marketing]
depends_on: [MIRROR1]
blocks: []
---

## Scope

Deploy the Worker with a dedicated R2 bucket and publisher secret, then publish
its non-secret URL in project links.

## Done when

The Worker accepts only authenticated bounded snapshots, renders the latest accepted
state, and visibly labels stale data when the local machine is offline.
