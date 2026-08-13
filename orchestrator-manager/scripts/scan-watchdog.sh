#!/bin/zsh
# The layer that actually guarantees the search never stays down.
#
# It checks every two minutes that `scan-forever.sh` is alive and restarts it if
# not. Two minutes rather than thirty because a supervisor that notices a death
# half an hour later has already lost half an hour, and this check costs one
# `pgrep`.
#
# Like everything else in this pair it calls NO language model. That is the whole
# design: the guarantee that work continues is free and mechanical, and the
# operator's assistant is woken only to READ results, never to keep the lights on.
# The previous arrangement had it the other way round and cost sixty per cent of a
# weekly subscription in a day.
#
# Stop both layers with:  touch research/agent_runs/scan/scan.stop
# The watchdog honours the same stop file as the loop it supervises, so one
# command stops everything rather than leaving a supervisor to resurrect a
# process the operator just killed -- which has happened here before.

set -u
ROOT="${0:A:h}/../.."
cd "$ROOT" || exit 1

SCAN_DIR="research/agent_runs/scan"
STOP="$SCAN_DIR/scan.stop"
LOG="$SCAN_DIR/watchdog.log"
LOOP="orchestrator-manager/scripts/scan-forever.sh"
PIDFILE="$SCAN_DIR/scan-forever.pid"

mkdir -p "$SCAN_DIR"
print "$(date '+%Y-%m-%d %H:%M:%S') watchdog started (pid $$)" >> "$LOG"

while true; do
  if [[ -f "$STOP" ]]; then
    print "$(date '+%Y-%m-%d %H:%M:%S') stop file present, watchdog exiting" >> "$LOG"
    exit 0
  fi

  # `kill -0 <pid>` asks the kernel, which cannot be confused by a command line
  # that happens to contain this script's name. The first version used
  # `pgrep -f scan-forever.sh` and matched the operator's own status check, so it
  # sat reporting health over a dead loop.
  alive=0
  if [[ -r "$PIDFILE" ]]; then
    kill -0 "$(cat "$PIDFILE")" 2>/dev/null && alive=1
  fi
  if (( ! alive )); then
    print "$(date '+%Y-%m-%d %H:%M:%S') search loop is down -- restarting" >> "$LOG"
    # The stop file is removed by the loop on start, so restarting here after an
    # operator stop would defeat the control. The check above is what prevents
    # that, and it is deliberately the FIRST thing in the iteration.
    nohup zsh "$LOOP" > /dev/null 2>&1 &
    print "$(date '+%Y-%m-%d %H:%M:%S') restarted as pid $!" >> "$LOG"
  fi

  sleep 120
done
