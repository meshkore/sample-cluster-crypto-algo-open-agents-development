---
title: "Public surfaces"
category: deploy
tags: [cloudflare, worker, meshkore, github]
updated: 2026-08-02
owner: capitaharlock
status: stable
---

# Public surfaces

- Monitor: <https://quantlab-public-mirror.rjj.workers.dev>
- Cluster: <https://meshkore.com/clusters/open-crypto-algo-agents-development>
- Repository: <https://github.com/meshkore/sample-cluster-crypto-algo-open-agents-development>

The monitor is a Cloudflare Worker with an R2 bucket, deployed from
`cloudflare/public-mirror/`. Each local daemon pushes a redacted, size-bounded
snapshot to `POST /api/state` every five seconds behind a shared bearer token,
tagged with a runner id (defaults to hostname); the Worker keeps one object per
runner plus an index of recent sessions in R2 and serves them read-only. Several
of the operator's own machines can publish at once — the sidebar on the page
lists live and past sessions, `/api/dashboard` without a query follows whichever
published most recently, and `/api/dashboard?runner=<id>` pins one. Nothing on
the internet can reach any Mac — the flow is outbound only, which is why this
replaced the tunnel.

`workers.dev` is permanent. It is tied to the account subdomain, does not
expire, and survives redeploys, reboots and the Mac being switched off. Only
the freshness banner changes when the origin stops publishing.

The page is the same file as the local monitor: `sync-ui.sh` copies
`src/quantlab/dashboard.html` into `public/index.html`, and the Worker exposes
`/api/dashboard` with the same payload shape as the daemon, so the two views
cannot drift.

No public surface uses a MeshKore hostname. This laboratory is a public example
and is deliberately not associated with the platform's own domain.

The canonical machine-readable registry is [[public/links]].

## Retired

The account-less Quick Tunnel (`*.trycloudflare.com`) was removed on
2026-08-02. Cloudflare deregistered its hostname while `cloudflared` kept
retrying against a dead tunnel, so launchd reported a healthy process serving
nothing. Quick Tunnels mint a new hostname on every start and cannot be a
stable public address.
