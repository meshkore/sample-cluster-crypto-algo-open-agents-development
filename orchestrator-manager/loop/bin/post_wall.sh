#!/bin/sh
# Publish one iteration update to the MeshKore Wall. Body arrives on stdin.
#
# The public cluster admits agents tokenless, so nothing here reads a
# credential. Keep it that way: this script must stay safe to run from cron.
#
#   bin/post_wall.sh <<'EOF'
#   ## H-042 — the bear module ignores volume
#   ...
#   EOF
set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)
. "$HERE/cluster/identity.env"

if [ ! -x "$(command -v node)" ]; then
  echo "post_wall: no node on PATH; the Wall bridge cannot run" >&2
  exit 1
fi

BODY=$(cat)
if [ -z "$(printf '%s' "$BODY" | tr -d '[:space:]')" ]; then
  echo "post_wall: refusing to post an empty message" >&2
  exit 2
fi

STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
mkdir -p "$HERE/cluster/outbox"
printf '%s\n' "$BODY" > "$HERE/cluster/outbox/$STAMP.md"

printf '%s\n' "$BODY" | node "$REPO/.meshkore/scripts/meshkore_post.mjs" "$CLUSTER_ID" "$AGENT_HANDLE"
echo "post_wall: sent $(printf '%s' "$BODY" | wc -c | tr -d ' ') bytes as $AGENT_HANDLE"
