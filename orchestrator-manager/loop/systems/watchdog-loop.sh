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
set -u
ROOT="${0:a:h}"
while true; do
  [[ -f "$ROOT/keepalive.stop" ]] && exit 0
  zsh "$ROOT/watchdog.sh"
  sleep 1800
done
