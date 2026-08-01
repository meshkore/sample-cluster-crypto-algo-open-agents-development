---
title: "Public state mirror"
category: deploy
updated: 2026-08-01
owner: codex-lead
status: active
---

# Public state mirror

`cloudflare/public-mirror/` is a **presentation-only** Worker. QuantLab continues
to calculate locally. Every five seconds, when configured, the local service sends
one compacted snapshot to `/api/state`; the Worker persists only that latest object
in R2 and serves it at an independent `workers.dev` URL.

The UI displays both edge receipt time and local source time. After 15 seconds it
is delayed, and after 60 seconds it says the local runner is stopped or offline.
It deliberately retains the latest truthful state instead of showing a false live
indicator.

## Provisioning (operator-only)

The Cloudflare API token must have permission to edit **Workers Scripts** and R2
resources for this account. Keep it outside this repository. From the module:

```bash
npx wrangler r2 bucket create quantlab-public-mirror
npx wrangler secret put PUBLISH_TOKEN
npx wrangler deploy
```

Set the returned independent `https://…workers.dev` URL and a matching token in
the local runtime configuration (never in Git):

```json
"public_mirror": {"enabled": true, "url": "https://…workers.dev", "token_env": "QUANTLAB_PUBLIC_MIRROR_TOKEN", "interval_seconds": 5}
```

Export `QUANTLAB_PUBLIC_MIRROR_TOKEN` only in the launchd/runtime environment.
Reinstall or restart QuantLab after changing it.

## Cost and limits

One five-second update is about 518,400 R2 Class A writes per 30-day month. R2's
published free allowance currently includes one million Class A operations and ten
million Class B operations monthly; viewer polling consumes Worker requests and
R2 reads, so review Cloudflare's current meter before promotion. The publisher
limits public snapshots to 500 assets, 500 recent trades and 720 equity points.

## Security boundaries

- The bearer secret is checked only at ingestion and is never returned.
- The Worker accepts a five MiB maximum JSON payload and does not execute it.
- Local research ignores public site and cluster input.
- The page is public by design; do not add local paths, command logs, tokens or
  personally identifying information to dashboard state.
