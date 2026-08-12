#!/bin/zsh
# Run the watchdog every thirty minutes, for as long as this stays up.
#
# WHY THIS IS NOT A LAUNCHAGENT OR A CRONTAB, both of which were tried:
#
#   - `crontab -l` blocks on a macOS permissions prompt that nobody is present
#     to answer at three in the morning.
#   - A LaunchAgent loads and immediately exits 127 with "can't open input
#     file": this repository lives under `~/Documents`, which macOS protects
#     under TCC, and launchd has not been granted Full Disk Access. It cannot
#     read the script, and would not be able to read the journal either.
#
# A process started from the operator's own shell inherits that shell's TCC
# grant, so it can read the repository. The cost is honest and worth stating:
# THIS DOES NOT SURVIVE A REBOOT. If the machine restarts, it must be started
# again the same way the supervisor is:
#
#     python3 -c "import subprocess; subprocess.Popen(
#         ['zsh','orchestrator-manager/loop/systems/watchdog-loop.sh'],
#         start_new_session=True)"
#
# TWO QUESTIONS ON TWO CLOCKS. "Is it up" and "is it producing" are different
# questions and want different intervals. A dead supervisor should be replaced
# within a couple of minutes -- on a thirty-minute tick it costs half an hour of
# a night that was supposed to be spent working. Whether the loop is PRODUCING
# cannot be judged that often: one attempt is a long web search, a code write
# and an eight-year backtest, so a two-minute view of it says nothing at all.
#
# So this ticks every two minutes and `watchdog.sh` decides what to say: it
# always repairs, and it reports at most every thirty minutes, which is the
# cadence the operator asked for.
set -u
ROOT="${0:a:h}"
while true; do
  [[ -f "$ROOT/keepalive.stop" ]] && exit 0
  zsh "$ROOT/watchdog.sh"
  sleep 120
done
