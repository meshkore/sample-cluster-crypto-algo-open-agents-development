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
`monitor/public/{index,loop,live}.html` into the Worker's `public/`, and the
Worker exposes the same endpoints in the same payload shape as the daemon, so
the two views cannot drift.

**There is no step that strips anything out of the page for the public build,
and there is deliberately nothing to strip.** The three copies are byte-for-byte
identical and the page is verified to contain no credential, no admin control,
no delete path and no `localhost` reference — the two occurrences of the word
"token" in it are a note parser. Where the page needs to behave differently it
asks the host rather than being edited: `GET /health` returns
`{"websocket": true|false}`, the daemon says `true` and the Worker says `false`.
That is why one file can serve both, and editing a "public version" separately
would reintroduce exactly the drift `sync-ui.sh` exists to prevent.

The public/private boundary is not in the frontend at all. It is in **what the
daemon chooses to push**, outbound only, over `POST` behind a bearer token:

| pushed to the edge | never leaves the Mac |
|---|---|
| finished run rows via `describe()` (figures, params, policy) | the SQLite database itself |
| the equity curve | the downloaded candles |
| orders, trades, traded decisions — each capped at 2,000 rows | credentials and tokens |
| the regime timeline | agent logs and advisor transcripts |
| the loop heartbeat and hypothesis journal | anything under `.meshkore/credentials/` |

Nothing on the internet can open a connection back to the laboratory. That is a
property of the architecture — the flow is one-way — rather than a rule someone
has to remember at deploy time.

No public surface uses a MeshKore hostname. This laboratory is a public example
and is deliberately not associated with the platform's own domain.

The canonical machine-readable registry is [[public/links]].

## Retired

The account-less Quick Tunnel (`*.trycloudflare.com`) was removed on
2026-08-02. Cloudflare deregistered its hostname while `cloudflared` kept
retrying against a dead tunnel, so launchd reported a healthy process serving
nothing. Quick Tunnels mint a new hostname on every start and cannot be a
stable public address.
