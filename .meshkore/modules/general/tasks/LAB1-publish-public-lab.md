---
id: LAB1
title: "Publish and secure the public collaboration surface"
status: done
priority: high
owner: codex-lead
category: general
initiative: public-agent-lab
created: 2026-08-01
updated: 2026-08-01
completed_at: 2026-08-01T12:59:00Z
resolved_by: codex-lead
resolved_by_conv: public-agent-lab
commit_shas: [562ea2c]
tags: [meshkore, github, security]
depends_on: []
blocks: [LAB2]
---

## Scope

Create the public MeshKore room, standard ledger, GitHub governance and stable
monitor URL without publishing credentials.

## Done when

Public endpoints resolve, tests and CI pass, secrets are excluded and main is
published.

## Files

`.meshkore/`, `.github/`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`.

## Resolution

Public MeshKore cluster, GitHub repository and Cloudflare monitor were created.
Quality gates, contribution policy, threat model and secret exclusions passed.
