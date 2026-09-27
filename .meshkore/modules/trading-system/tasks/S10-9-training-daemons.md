---
id: S10-9
title: "F. Training: put 010's training under the watchdog with its own brake and progress tape"
status: backlog
priority: high
owner: unassigned
profile: deployer
category: trading-system
initiative: system-ten-conditioned-rl
created: 2026-09-27
updated: 2026-09-27
tags: [system10, daemons, watchdog, phase-f]
depends_on: [S10-8]
blocks: []
---

> Read `.meshkore/context/system10-design.md` before starting. It is the plan this task is one piece of, and it carries
> the laboratory's standing rules under "Our conditions" and the kill conditions under section 7.

## The ask

*"El arranque de los procesos de formacion"*. Training that only runs while someone is
watching is not training. 010's runner joins the 24/7 circuit, guarded the way 06's is.

## What to build

1. `research/system10/autotest.py`: a copy of 06's paired-experiment runner adapted to
   010's arms (region variants, lambda, algorithm step, seeds), reading
   `research/system10/rnd/program.jsonl`, writing the progress tape and verdicts.
2. `research/system06/watchdog.ps1`: a block for 010's runner with its own brake
   `research/system10/STOP_S10`, process liveness measured by **output age** (the trader
   lesson of 2026-09-27: a pid is not liveness), and the GPU rule enforced in code - the
   010 runner does not start a GPU training while 06's autoloop is training, and vice
   versa (a lock file under `research/`, with the owner and the time in it).
3. `pulse.py` and `cf_pusher` read 010's state so the hourly trace and the public page
   show it.
4. A `watch_experiment.py` for 010, so the operator's one-line figures are produced the
   moment an arm finishes.

## Done when

The watchdog relaunches a killed 010 runner within five minutes, respects `STOP_S10`, never
holds two GPU trainings, and the operator receives one line of figures per finished cycle.
