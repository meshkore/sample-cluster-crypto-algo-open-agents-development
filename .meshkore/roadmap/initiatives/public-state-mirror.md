---
id: public-state-mirror
title: "Public state mirror for the local research runner"
status: active
priority: high
oneliner: "Publish a clearly timestamped, read-only view of the local QuantLab runner."
modules: [deploy, public-mirror, quantlab, design]
target: "2026-08"
created: 2026-08-01
updated: 2026-08-01
owner: codex-lead
related: [public-agent-lab]
---

## Why this exists

The research engine belongs on the operator's Mac. The public site must only
mirror the last signed update, distinguish fresh from stale state, and make the
repository and agent room easy to discover.

## Done when

The source is reviewed, the mirror is deployed on an independent Cloudflare URL,
and a stopped local runner is visibly labelled as stale rather than live.

## Task plan

- #MIRROR1 active — implement the bounded publisher and read-only public UI.
- #MIRROR2 pending — provision the Cloudflare Worker/R2 bindings and publish it.
- #MIRROR3 in progress — version a public-safe ledger of research progress.
- #DESIGN1 in progress — make the English public observatory visually distinctive.
