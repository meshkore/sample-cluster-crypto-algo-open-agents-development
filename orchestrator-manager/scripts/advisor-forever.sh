#!/bin/zsh
# The cluster advisor, kept alive. Same shape as arena-forever.sh, and for the
# same reason: a process meant to sit on a socket for days will eventually be
# killed by something nobody planned.
#
# What it costs. NOT one model request per message: `cluster_advisor.py` only
# calls Codex for a message that names the agent, and at most six times an hour.
# A quiet Wall costs one node process holding a WebSocket open.
#
# Stop it with:   touch research/agent_runs/advisor/advisor.stop
# Watch it with:  tail -f research/agent_runs/advisor/advisor.log
# Is it alive:    kill -0 $(cat research/agent_runs/advisor/advisor-forever.pid)

set -u
ROOT="${0:A:h}/../.."
cd "$ROOT" || exit 1

DIR="research/agent_runs/advisor"
STOP="$DIR/advisor.stop"
LOG="$DIR/advisor.log"
PIDFILE="$DIR/advisor-forever.pid"

mkdir -p "$DIR"
rm -f "$STOP"

# A PID FILE, not `pgrep -f`. Pattern matching matches any command line that
# merely MENTIONS this script -- including the operator's own health check -- so
# a watchdog built on it reports a healthy loop while the loop is dead.
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  print "advisor-forever already running (pid $(cat "$PIDFILE"))"
  exit 0
fi
print $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT INT TERM

print "$(date -u '+%Y-%m-%d %H:%M:%S') advisor-forever started (pid $$)" >> "$LOG"

while true; do
  if [[ -f "$STOP" ]]; then
    print "$(date -u '+%Y-%m-%d %H:%M:%S') stop file present, exiting" >> "$LOG"
    exit 0
  fi

  PYTHONPATH=backtester:trading-system:orchestrator-manager \
    .venv/bin/python orchestrator-manager/scripts/cluster_advisor.py \
    >> "$LOG" 2>&1 \
    || print "$(date -u '+%Y-%m-%d %H:%M:%S') advisor exited $?; restarting in 30s" >> "$LOG"

  waited=0
  while (( waited < 30 )); do
    [[ -f "$STOP" ]] && break
    sleep 5
    (( waited += 5 ))
  done
done
