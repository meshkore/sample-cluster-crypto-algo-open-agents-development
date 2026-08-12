#!/bin/zsh
# Keep the intraday loop running until someone deliberately stops it.
#
# The same supervisor the four-module loop uses, for the same reason: a
# LaunchAgent is the proper answer and needs Full Disk Access this machine has
# not granted. Deliberately dumb -- it restarts the loop when the loop exits and
# does not try to be clever about why.
#
# It must be STARTED DETACHED or it dies with whatever shell launched it. The
# first intraday loop ran 29 iterations and was killed mid-iteration when its
# parent session was torn down, with no error in its log to say so:
#
#     python3 -c "import subprocess,sys; subprocess.Popen(
#         ['zsh', 'orchestrator-manager/loop/intraday/keepalive.sh'],
#         start_new_session=True)"
#
# `start_new_session=True` is the load-bearing part -- it puts the supervisor in
# its own process group, so a signal sent to the launching session's group does
# not reach it. `nohup` alone does not do this.
#
# Stop it with:  touch orchestrator-manager/loop/intraday/keepalive.stop

set -u
ROOT="${0:a:h}"
REPO="${ROOT:h:h:h}"
LOG="$ROOT/run.log"
STOP="$ROOT/keepalive.stop"

cd "$REPO" || exit 1
export PYTHONPATH="$REPO/backtester:$REPO/trading-system:$REPO/orchestrator-manager"

# The credentials the seats need. Read from the files rather than inherited,
# because a supervisor that outlives its launching shell inherits nothing:
# without these the critic sits out every iteration and the pairs never publish,
# and both failures are silent.
[[ -f "$REPO/.meshkore/credentials/zai-api-key" ]] && \
  export ZAI_API_KEY="$(tr -d '\n' < "$REPO/.meshkore/credentials/zai-api-key")"
[[ -f "$REPO/.meshkore/credentials/public-mirror-token" ]] && \
  export QUANTLAB_PUBLIC_MIRROR_TOKEN="$(tr -d '\n' < "$REPO/.meshkore/credentials/public-mirror-token")"

backoff=5
while true; do
  if [[ -f "$STOP" ]]; then
    print -r -- "$(date -u +%FT%TZ) keepalive: stop file present, exiting" >> "$LOG"
    exit 0
  fi
  print -r -- "$(date -u +%FT%TZ) keepalive: starting the intraday loop" >> "$LOG"
  .venv/bin/python -u -m quantlab_manager.intraday_loop \
    --iterations 0 --pause 45 >> "$LOG" 2>&1
  status=$?
  print -r -- "$(date -u +%FT%TZ) keepalive: loop exited ($status), waiting ${backoff}s" >> "$LOG"
  sleep $backoff
  # Backoff, so a loop that dies instantly on a bad deploy does not spin the CPU
  # all night. Reset once it has managed to stay up for a while.
  (( backoff = backoff < 300 ? backoff * 2 : 300 ))
done
