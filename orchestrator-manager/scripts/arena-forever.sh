#!/bin/zsh
# The arena, kept alive. Written to be left running for days with nobody watching.
#
# It calls NO language model. Not one request, not once. `arena.py` is numpy and
# scikit-learn over a CSV, and the only subprocess it ever starts is
# `publish_intraday.py`, which is the same backtest an operator runs by hand.
# The loop that ran in this laboratory before spawned `claude -p` agents and
# consumed sixty per cent of a weekly subscription in a single day.
#
# Stop it with:   touch research/agent_runs/arena/arena.stop
# Watch it with:  tail -f research/agent_runs/arena/arena.log
# Is it alive:    kill -0 $(cat research/agent_runs/arena/arena-forever.pid)
#
# **Why a supervisor at all, when `arena.py --rounds 0` already loops.** Because
# a process that runs for three days will eventually be killed by something
# nobody planned -- a memory spike, a laptop sleeping badly, an OS update. The
# arena keeps everything it must not forget on disk: the archive its surrogate
# learns from, the champion that sets the floor, the ledger the daily promotion
# cap is counted off. A restart costs the forty seconds of loading tapes and
# nothing else, and this is what turns "it died at 3 a.m." into a gap in a log.

set -u
ROOT="${0:A:h}/../.."
cd "$ROOT" || exit 1

DIR="research/agent_runs/arena"
STOP="$DIR/arena.stop"
LOG="$DIR/arena.log"
PIDFILE="$DIR/arena-forever.pid"

mkdir -p "$DIR"
rm -f "$STOP"

# A PID FILE, not `pgrep -f`. Pattern matching matched any command line that
# merely MENTIONED this script -- including the operator's own `until pgrep -f`
# check -- so the watchdog reported a healthy loop while the loop was dead. It is
# the same shape as the `pkill -f` that once killed a supervisor with its child.
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  print "arena-forever already running (pid $(cat "$PIDFILE"))"
  exit 0
fi
print $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT INT TERM

print "$(date '+%Y-%m-%d %H:%M:%S') arena-forever started (pid $$)" >> "$LOG"

while true; do
  if [[ -f "$STOP" ]]; then
    print "$(date '+%Y-%m-%d %H:%M:%S') stop file present, exiting" >> "$LOG"
    exit 0
  fi

  PYTHONPATH=backtester:trading-system:orchestrator-manager \
    .venv/bin/python orchestrator-manager/scripts/arena.py --rounds 0 \
    >> "$LOG" 2>&1 \
    || print "$(date '+%Y-%m-%d %H:%M:%S') arena exited $?; restarting in 60s" >> "$LOG"

  # A pause before restarting, so a crash on the very first round becomes one
  # log line a minute rather than a spin that fills the disk overnight.
  waited=0
  while (( waited < 60 )); do
    [[ -f "$STOP" ]] && break
    sleep 10
    (( waited += 10 ))
  done
done
