# Public mirror publish credential

Operator decision (2026-08-03): this value is **public on purpose**.

## What it is for

It authorizes `POST /api/state` on the shared monitor:

- Monitor: <https://quantlab-public-mirror.rjj.workers.dev>
- Env var the local daemon expects: `QUANTLAB_PUBLIC_MIRROR_TOKEN`
- Raw value file next to this note: [`mirror-publish`](./mirror-publish)

Anyone running QuantLab locally can publish their compacted research state so
the left-hand sessions rail on the monitor can list their runner next to
everyone else's. Selecting a row pins the dashboard to that session.

## What it is not for

- **Not** MeshKore Wall access. The Wall is already open; no credential is
  needed to read or post there (`cluster.yaml` documents the public transport).
- **Not** GitHub, Cloudflare account, wrangler, or exchange access.
- **Not** a personal identity. It only proves the publisher knows the shared
  publish value configured on the Worker as `PUBLISH_TOKEN`.

## Why leave it in the public tree

The monitor is a shared backtesting station. Hiding the publish value behind
a private hand-off meant only machines the operator had already provisioned
could appear, which defeated the point of the multi-runner sidebar. Keeping
the value next to the public cluster docs lets a new contributor start
publishing without a private channel.

Trade-off accepted: anyone with the value can write into the monitor's R2
state under a runner id they choose. The Worker still sanitizes ids, size-
limits payloads, and never exposes Cloudflare account credentials. Abuse is
handled by rotating `PUBLISH_TOKEN` on the Worker and updating this file.

## How to use it on a local machine

```bash
mkdir -p .meshkore/credentials
cp .meshkore/public/mirror-publish .meshkore/credentials/public-mirror-token
chmod 600 .meshkore/credentials/public-mirror-token
# from the repository root
PYTHONPATH=src python3 -m quantlab.cli service install
```

`service install` also reads `.meshkore/public/mirror-publish` directly if the
credentials copy is missing, so the public file alone is enough after a
reinstall. Set `public_mirror.runner_id` / `runner_label` in config if you
want a stable name in the sidebar instead of the machine hostname.

## Rotation

If the monitor is being spammed, rotate on the machine that holds Cloudflare
credentials:

```bash
cd orchestrator-manager/cloudflare/public-mirror
npx wrangler secret put PUBLISH_TOKEN
```

Then replace the contents of `mirror-publish` (and any local
`credentials/public-mirror-token` copies) with the new value and reinstall
each LaunchAgent that should keep publishing.
