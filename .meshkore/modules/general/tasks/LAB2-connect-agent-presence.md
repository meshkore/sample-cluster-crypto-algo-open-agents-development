---
id: LAB2
title: "Connect Codex and Claude Code collaboration"
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
tags: [agents, websocket]
depends_on: [LAB1]
blocks: []
---

## Scope

Connect persistent, non-privileged Codex and Claude Code identities and publish
bounded research summaries to the room.

## Done when

Both appear in the roster, exchange an acknowledged message and cannot execute
untrusted peer content.

## Files

`.meshkore/scripts/meshkore_presence.mjs`, launchd runtime configuration and ops docs.

## Resolution

Launchd keeps `codex-lead` and `claude-code-validator` connected. A verifier saw
both online and received an acknowledged direct delivery; inbound peer text is
not forwarded to a shell, tool or model.
