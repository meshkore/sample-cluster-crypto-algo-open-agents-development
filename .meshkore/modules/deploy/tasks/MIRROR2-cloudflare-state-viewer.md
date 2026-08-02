---
id: MIRROR2
title: "Deploy the public Cloudflare state viewer"
status: done
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

## Delivered

Worker `quantlab-public-mirror` deployed to
<https://quantlab-public-mirror.rjj.workers.dev> with the R2 bucket
`quantlab-public-mirror` and the encrypted secret `PUBLISH_TOKEN`. The daemon
publishes every five seconds behind that bearer token; unauthenticated and
wrong-token writes return 401, verified against the live deployment.

The Worker serves the monitor UI as a static asset and exposes `/api/dashboard`
with the same payload shape as the daemon, so `sync-ui.sh` can copy
`src/quantlab/dashboard.html` in verbatim and the public page cannot drift from
the local one. `last_completed_strategy` was added to the compact snapshot;
without it the active view blanked out between strategies.

## Infrastructure consolidated

The Quick Tunnel was removed. Cloudflare had deregistered its hostname
(NXDOMAIN) while `cloudflared` kept retrying, so launchd showed a healthy
process serving nothing — a Quick Tunnel also mints a new hostname on every
start, so it can never be a stable address. The Mac now runs exactly one
tunnel, `meshkore-ollama`, which belongs to an unrelated service. QuantLab
needs none: the mirror is push-only and strictly safer than publishing a port.

The address is deliberately a generic `workers.dev`, not a MeshKore hostname,
so this public example is not associated with the platform.
