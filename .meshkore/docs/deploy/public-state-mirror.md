---
title: "Public state mirror"
category: deploy
updated: 2026-08-01
owner: codex-lead
status: active
---

# Public state mirror

`cloudflare/public-mirror/` is a **presentation-only** Worker. QuantLab continues
to calculate locally. Every five seconds, when configured, each local service sends
one compacted snapshot to `/api/state`, tagged with a `runner.id` that defaults to
the machine's hostname. The Worker keeps one object per runner in R2
(`runner/<id>.json`) plus a small index (`runners/index.json`), rather than a single
overwritten object — several contributors' machines can publish at once without
one erasing another's evidence.

`GET /api/dashboard` (no query) returns whichever runner published most recently,
which is what the page shows with no interaction — this preserves the original
single-runner behaviour exactly. `GET /api/dashboard?runner=<id>` returns one named
session, and `GET /api/runs` returns the index for the sidebar that lists live and
past sessions. `PUBLISH_TOKEN` stays a single shared secret across an operator's own
machines; it is not a per-contributor credential, so this only ever aggregates
sessions the operator already controls, not arbitrary public writers.

The UI displays both edge receipt time and local source time. After 15 seconds it
is delayed, and after 60 seconds it says the local runner is stopped or offline.
It deliberately retains the latest truthful state instead of showing a false live
indicator. The sidebar uses the same signal per session (last-seen age) to mark a
session live versus historical.

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

Running the same laboratory from a second machine under the same account needs no
new secret or config: copy the same `QUANTLAB_PUBLIC_MIRROR_TOKEN` and the runner id
defaults to that machine's own hostname. Set `public_mirror.runner_id`/`runner_label`
explicitly only to override the default label shown in the sidebar.

Before every `wrangler deploy`, run `cloudflare/public-mirror/sync-ui.sh` (copies
`src/quantlab/dashboard.html`, the single source of truth for the page, into
`public/index.html`) and `node cloudflare/public-mirror/test.mjs` (exercises the
Worker's routing and storage logic against an in-memory R2 stand-in; there is no
`wrangler dev` credential requirement to run it).

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

## Versioned research evidence

After every completed iteration, QuantLab writes a small public ledger at
`research/public/`: `current.json`, `best-strategy.json` and
`iterations.json`. The supervised local service receives the repository path
and automatically commits and pushes this ledger to `main` when Git credentials
are available. It stages only this directory, never runtime SQLite state,
downloads, raw MeshKore logs or agent logs. A push failure is intentionally
non-fatal to research and can be retried on the next completed iteration.
