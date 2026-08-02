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
`cloudflare/public-mirror/`. The local daemon pushes a redacted, size-bounded
snapshot to `POST /api/state` every five seconds behind a bearer token; the
Worker stores the latest one in R2 and serves it read-only. Nothing on the
internet can reach the Mac — the flow is outbound only, which is why this
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
