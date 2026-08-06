#!/bin/sh
# One tick of the research loop: housekeeping, then say what should happen next.
#
# This script deliberately does NOT start an agent. The iteration is driven
# from the operator's Claude Code session (see README, "How the loop is
# driven") so that every step is visible and interruptible. What this does is
# the bookkeeping that has to be right whether or not anyone is watching:
# reclaim a dead iteration, and print the single next action.
#
#   bin/tick.sh            reclaim stale locks, print next action
#   bin/tick.sh --dry-run  print only, change nothing
set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)
. "$HERE/cluster/identity.env"

LOCK="$HERE/ledger/iteration.lock"
STALE=14400                    # 4 h; matches ledger.py STALE_LOCK_SECONDS
DRY=${1:-}

log() { printf '%s tick: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$HERE/runs/tick.log"; }

if [ -f "$LOCK" ]; then
  AGE=$(( $(date +%s) - $(stat -f %m "$LOCK") ))
  ID=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('id','unknown'))" "$LOCK" 2>/dev/null || echo unknown)
  if [ "$AGE" -lt "$STALE" ]; then
    log "busy: $ID open for ${AGE}s"
    echo "BUSY  $ID has been open ${AGE}s — let it finish"
    exit 0
  fi
  # A lock older than STALE means the previous iteration died: the session was
  # closed, the machine slept, the process was killed. Record it as abandoned
  # rather than deleting it silently — an iteration that vanishes without trace
  # is exactly what the ledger exists to prevent.
  log "stale lock for $ID (${AGE}s), reclaiming"
  if [ "$DRY" = "--dry-run" ]; then
    echo "STALE $ID (${AGE}s) — would reclaim"
    exit 0
  fi
  python3 "$HERE/bin/ledger.py" abandon "$ID" \
      --notes "iteration exceeded ${STALE}s with no record and was reclaimed by tick" >/dev/null
  echo "RECLAIMED $ID"
fi

python3 "$HERE/bin/ledger.py" status
echo
echo "NEXT  run one iteration of $HERE/LOOP.md against $REPO ($BRANCH)"
log "idle, next iteration is due"
