# How to bring the circuit back up

Stopped deliberately on 2026-08-30 (operator: one job at a time, champion attempt first).
The STOP file in this directory keeps the watchdog from relaunching the loop and the
experiment runner; the pulse, the Cloudflare pusher and the wall listener are untouched
and still publishing.

When the champion attempt finishes (research table -> median vs bar -> the single 2026
readout, all in research/system06/champion_wide.log):

1. `del research\system06\STOP`
2. `Start-ScheduledTask -TaskName system06-watchdog`  (relaunches the autoloop and the runner)
3. The runner picks up P23-progressive-entries first - it was interrupted mid-training and
   nothing was scored.

Do not start a second heavy job while a training is running: the box is 32 GB and three
concurrent jobs stretched a single epoch past fifteen minutes (and cost P22 a MemoryError).
