#!/bin/sh
# Copy the monitor UI verbatim into the Worker's asset directory.
#
# The Worker exposes `/api/dashboard` with the same shape the local daemon
# serves, so the page needs no edits: one file, two hosts, no drift. Run this
# before every `wrangler deploy`.
set -eu
root=$(cd "$(dirname "$0")/../../.." && pwd)
# Every page the monitor serves, not just the dashboard. `loop.html` was added
# to `monitor/public/` and NOT here, so the local daemon served it and the edge
# returned 404 -- one file out of two is exactly the drift this script exists
# to prevent.
for page in index.html loop.html live.html; do
  src="$root/monitor/public/$page"
  dest="$root/orchestrator-manager/cloudflare/public-mirror/public/$page"
  [ -f "$src" ] || { echo "missing $src" >&2; exit 1; }
  cp "$src" "$dest"
  echo "synced $(wc -c < "$dest" | tr -d ' ') bytes -> public/$page"
done
