#!/bin/sh
# Copy the monitor UI verbatim into the Worker's asset directory.
#
# The Worker exposes `/api/dashboard` with the same shape the local daemon
# serves, so the page needs no edits: one file, two hosts, no drift. Run this
# before every `wrangler deploy`.
set -eu
root=$(cd "$(dirname "$0")/../../.." && pwd)
src="$root/monitor/public/index.html"
dest="$root/orchestrator-manager/cloudflare/public-mirror/public/index.html"
[ -f "$src" ] || { echo "missing $src" >&2; exit 1; }
cp "$src" "$dest"
echo "synced $(wc -c < "$dest" | tr -d ' ') bytes -> public/index.html"
