---
title: "Infrastructure"
category: ops
tags: [launchd, cloudflare, worker, tunnel, credentials]
updated: 2026-08-02
owner: capitaharlock
status: stable
---

# Infrastructure

Everything that computes runs on one Mac. Everything public is push-only. No
service on the internet can open a connection to the origin.

```
Mac (private)                              Cloudflare (public)
  quantlab daemon  :8766 loopback
        |  POST /api/state every 5s, bearer token
        +--------------------------------> Worker quantlab-public-mirror
                                              +-- R2 bucket (latest snapshot)
                                              +-- https://quantlab-public-mirror.rjj.workers.dev
  presence agents (2)
        |  outbound WebSocket
        +--------------------------------> MeshKore cluster Wall

  ollama :11434 loopback
        |
        +-- named tunnel meshkore-ollama --> ollama-mesh.meshkore.com
```

## LaunchAgents

All `RunAtLoad` + `KeepAlive`, in `~/Library/LaunchAgents`.

| Label | What it runs |
|---|---|
| `com.asimovia.quantlab` | the research daemon and its loopback dashboard on `127.0.0.1:8766` |
| `com.meshkore.quantlab-codex-presence` | keeps `claude-sonnet-critic` online on the Wall (plist name is historical) |
| `com.meshkore.quantlab-claude-presence` | keeps `claude-opus-critic` online on the Wall |
| `com.meshkore.ollama-tunnel` | the machine's only tunnel, for a different service |

The daemon plist is mode `0600`: it carries the mirror publisher token in its
environment.

## One tunnel on this machine

`meshkore-ollama` (`71d2330a-010f-422b-9d37-11ee137f47e2`) is a named tunnel
that serves `ollama-mesh.meshkore.com` from `localhost:11434`. It belongs to a
different service and is unrelated to this laboratory.

QuantLab uses **no tunnel**. The Worker replaced it, which is both simpler and
safer: a tunnel publishes a port from the Mac, while the mirror only ever
receives what the Mac chooses to send.

The QuantLab Quick Tunnel was removed on 2026-08-02 — see
[[docs/deploy/public-surfaces]] for why it could never be a stable address. Its
plist is kept as `com.asimovia.quantlab-quick-tunnel.plist.removed`.

## Why workers.dev and not a MeshKore hostname

This repository is a public example. Putting it on a platform hostname would
associate the example with the platform, so the public monitor deliberately
lives on a generic `workers.dev` address. That address is permanent: it is
bound to the account subdomain, has no expiry window, and survives redeploys
and origin downtime.

## Deploying

```bash
# public monitor (Cloudflare)
cd orchestrator-manager/cloudflare/public-mirror && sh sync-ui.sh && npx wrangler deploy

# local daemon (copies the workspace into the runtime and reboots the agent)
PYTHONPATH=src python3 -m quantlab --config orchestrator-manager/config/default.json service install
```

`sync-ui.sh` copies `src/quantlab/dashboard.html` into the Worker's assets so
the public page is the same file as the local one. Always run it before
deploying, or the public view silently falls behind.

## Credentials

All under `.meshkore/credentials/`, mode `0600`, gitignored. Because that
directory never reaches git, the inventory is recorded here — names and
purposes only, never values.

| File | What it is | Consumed by |
|---|---|---|
| `public-cluster.json` | public cluster `c_6d80584497f943d29026`: owner + admin tokens | cluster administration |
| `private-cluster.json` | private cluster `c_8377faaafa834339b8f5` | cluster administration |
| `portal-token` | MeshKore portal access | operator tooling |
| `team-tokens.yaml` | per-agent cluster handles | presence, Wall posting |
| `public-mirror-token` | bearer token for `POST /api/state` | `QUANTLAB_PUBLIC_MIRROR_TOKEN` |

That directory's own `README.md` holds the rotation runbook. The mirror token
exists in three places and nowhere else: the credentials file, Cloudflare as
the encrypted Worker secret `PUBLISH_TOKEN`, and the daemon's LaunchAgent
environment. It is not in `wrangler.toml` or the Worker source.

Cloudflare access is wrangler OAuth as `rjj@proars.com`, held by wrangler in
`~/Library/Preferences/.wrangler/config/default.toml`. No Cloudflare API token
is stored in this repository.

The `ws` field inside the cluster JSON files embeds a token in its query
string, so redact those files key-by-key rather than printing them whole.

## Verifying the whole stack

```bash
PYTHONPATH=src python3 -m quantlab --config orchestrator-manager/config/default.json registry  # research state
curl -s http://127.0.0.1:8766/api/dashboard | head -c 200                 # origin
curl -s https://quantlab-public-mirror.rjj.workers.dev/api/state \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["mirror"])'    # edge freshness
```

If `edge_received_at` stops advancing, the Mac stopped publishing; the page
stays up and labels itself stale rather than disappearing.
