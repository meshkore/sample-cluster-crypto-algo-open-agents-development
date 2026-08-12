#!/bin/zsh
# Every thirty minutes: is the system loop alive, and is it still PRODUCING?
#
# A liveness check that only asks "is the process running" is the one that
# always passes while nothing happens. This laboratory has already lost a night
# to a loop that was running and had stopped iterating, and another to one that
# was killed with its session and left no error in its log. So this asks three
# separate questions and answers them in the log:
#
#   1. Is the supervisor up? If not, start it detached.
#   2. Is the loop process up? The supervisor handles this, but if the
#      supervisor itself is wedged, nothing else would notice.
#   3. Has the journal MOVED since the last check? A loop that is alive and
#      writing nothing is the failure this exists to catch. An iteration can
#      legitimately take hours -- a full 2018-to-lock backtest is slow -- so
#      silence is only reported after it exceeds the stall window below.
#
# It deliberately does NOT restart the loop for a stall. A backtest that has run
# for two hours is not necessarily stuck, and killing it would throw away the
# work and hide the problem. It records, loudly, and leaves the judgement to a
# person reading the log.
#
# Installed as a user crontab entry:
#   */30 * * * * /bin/zsh <repo>/orchestrator-manager/loop/systems/watchdog.sh

set -u
ROOT="${0:a:h}"
REPO="${ROOT:h:h:h}"
LOG="$ROOT/watchdog.log"
JOURNAL="$ROOT/journal"
STOP="$ROOT/keepalive.stop"

# Hours of silence before the journal counts as stalled. One attempt is a web
# search, a code write, a full continuous backtest over eight years, and
# possibly two published runs -- hours is normal, most of a night is not.
STALL_HOURS=3

now="$(date -u +%FT%TZ)"

if [[ -f "$STOP" ]]; then
  print -r -- "$now watchdog: stop file present, standing down" >> "$LOG"
  exit 0
fi

supervisor=$(pgrep -f "loop/systems/keepalive.sh" | head -1)
loop=$(pgrep -f "quantlab_manager.system_loop" | head -1)

if [[ -z "$supervisor" ]]; then
  print -r -- "$now watchdog: supervisor is GONE — restarting it detached" >> "$LOG"
  cd "$REPO" || exit 1
  # `start_new_session` matters here exactly as it does in the supervisor's own
  # header: cron's child process group goes away when cron reaps it, and a
  # supervisor started without it dies within the minute.
  /usr/bin/python3 -c "import subprocess; subprocess.Popen(['zsh','orchestrator-manager/loop/systems/keepalive.sh'], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)"
  print -r -- "$now watchdog: restart issued" >> "$LOG"
  exit 0
fi

if [[ -z "$loop" ]]; then
  # Normal for the few seconds between attempts; the supervisor restarts it.
  print -r -- "$now watchdog: supervisor up, loop process not running (it restarts between attempts)" >> "$LOG"
fi

# Report at most every REPORT_MINUTES, however often this is called. Repairs
# above are unconditional and always logged; a health line every two minutes
# would bury them in a log nobody could then read.
REPORT_MINUTES=30
REPORTED="$ROOT/.last-report"
if [[ -f "$REPORTED" ]]; then
  since=$(( $(date +%s) - $(stat -f %m "$REPORTED") ))
  (( since < REPORT_MINUTES * 60 )) && exit 0
fi
: > "$REPORTED"

newest=$(ls -t "$JOURNAL"/*.jsonl 2>/dev/null | head -1)
if [[ -z "$newest" ]]; then
  print -r -- "$now watchdog: NO JOURNAL AT ALL — the loop has never written an attempt" >> "$LOG"
  exit 0
fi

age_seconds=$(( $(date +%s) - $(stat -f %m "$newest") ))
age_minutes=$(( age_seconds / 60 ))
attempts=$(ls "$JOURNAL"/*.jsonl 2>/dev/null | wc -l | tr -d ' ')
generation=$(/usr/bin/python3 -c "
import json,sys
try: print(json.load(open('$ROOT/state.json')).get('generation','?'))
except Exception: print('?')
" 2>/dev/null)

if (( age_seconds > STALL_HOURS * 3600 )); then
  print -r -- "$now watchdog: STALLED — generation $generation, $attempts attempts, nothing written for ${age_minutes}m (limit $((STALL_HOURS*60))m). Not restarting: a long backtest is not a hang, and killing it would destroy the work. Read $ROOT/run.log." >> "$LOG"
else
  print -r -- "$now watchdog: ok — generation $generation, $attempts attempts, last write ${age_minutes}m ago, $(basename $newest)" >> "$LOG"
fi
