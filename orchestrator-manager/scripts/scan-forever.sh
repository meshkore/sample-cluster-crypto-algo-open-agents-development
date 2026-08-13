#!/bin/zsh
# The unattended half of the search, and the reason it is safe to leave running.
#
# It calls NO language model. Not one request, not once. The loop that ran in this
# laboratory before spawned `claude -p` agents to write strategy code and burned
# sixty per cent of a weekly subscription in a single day for one measurable
# result. This runs numpy over a CSV. It costs electricity.
#
# Stop it with:   touch research/agent_runs/scan/scan.stop
# Watch it with:  tail -f research/agent_runs/scan/scan.log
#
# `SCAN_INTERVAL` defaults to six hours. Faster is pointless: the research tape
# cannot change and the sealed tape grows by one day per day, so re-scoring more
# often than the data arrives just rewrites the same ledger line.

set -u
ROOT="${0:A:h}/../.."
cd "$ROOT" || exit 1

SCAN_DIR="research/agent_runs/scan"
STOP="$SCAN_DIR/scan.stop"
LOG="$SCAN_DIR/scan.log"
INTERVAL="${SCAN_INTERVAL:-21600}"

PIDFILE="$SCAN_DIR/scan-forever.pid"

mkdir -p "$SCAN_DIR"
rm -f "$STOP"

# A PID FILE, not `pgrep -f`. The watchdog used pattern matching first and it
# matched any command line that merely MENTIONED this script -- including the
# operator's own `until pgrep -f scan-forever.sh` check -- so the supervisor
# reported a healthy loop while the loop was dead. Same shape as the `pkill -f`
# that once killed the supervisor along with its child. A pid is exact.
print $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT INT TERM

print "$(date '+%Y-%m-%d %H:%M:%S') scan-forever started (pid $$, every ${INTERVAL}s)" >> "$LOG"

while true; do
  if [[ -f "$STOP" ]]; then
    print "$(date '+%Y-%m-%d %H:%M:%S') stop file present, exiting" >> "$LOG"
    exit 0
  fi

  PYTHONPATH=backtester:trading-system:orchestrator-manager \
    .venv/bin/python orchestrator-manager/scripts/hypothesis_scan.py --cycles 3 \
    >> "$LOG" 2>&1 \
    || print "$(date '+%Y-%m-%d %H:%M:%S') scan exited non-zero; retrying next cycle" >> "$LOG"

  # Sleep in short steps so the stop file is honoured within a minute rather
  # than up to six hours later. A stop control that takes a quarter of a day to
  # take effect is not a stop control.
  local waited=0
  while (( waited < INTERVAL )); do
    [[ -f "$STOP" ]] && break
    sleep 30
    (( waited += 30 ))
  done
done
