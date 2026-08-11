---
id: DESIGN4
title: "One card per job in the rail, and a centre pane that is only backtests"
status: done
priority: high
owner: master
category: design
initiative: public-state-mirror
created: 2026-08-11
updated: 2026-08-11
tags: [ui, monitor, running, jobs, multi-user]
depends_on: [DESIGN3]
blocks: []
---

## Scope

"Running now" drew one card per artefact rather than one per worker. The moment
the loop opened the sealed window, the run it launched appeared as a second
card, so a single iteration read as `loop-087-bear-2026` and `Iteration 87` side
by side with nothing saying they were the same work, and the group's count said
two.

The count has to mean something: two boxes must mean two people are working. A
contributor connecting from their own machine, running their own agents against
this system, must appear as their own box — and never merge into ours.

The archive had the same defect one level down. Each card already shows both
halves of its hypothesis, so listing the training run and the 2026 run
separately printed the same two figures twice, under two names, at two positions
in the same column.

## Delivered

- **One card per job.** A job is one worker doing one piece of work; for the
  loop, an iteration is the whole of it — framing, consultation, evolution,
  hundreds of backtests, and the single 2026 shot. Cards are titled by **who**,
  with the task in progress, the progress bar, the values under it, and the same
  two figures every other card carries.
- **Attribution is `run.submitted_by === beat.owner`.** The loop now publishes
  `owner` on every heartbeat, equal to the handle it submits its runs under. A
  new kind of worker appears correctly with no page change: publish a heartbeat
  with an `owner`, submit runs under the same handle.
- A heartbeat published before `owner` existed absorbs everything in flight and
  borrows its name from what it is running — right while one machine is the only
  worker, and self-correcting on restart.
- **Selecting a job opens a backtest**: the run in flight, else the last one that
  job produced, else its owner's most recent archived run. A job with none says
  so rather than putting something that is not a backtest in the centre pane.
- **The archive collapses to one card per hypothesis**, taking the position of
  its newest run and opening its 2026 half.
- **The iteration registry is gone.** No recent-iterations table, no verdict log,
  no per-iteration dashboard, no loop internals in the centre. What is happening
  lives in the left rail; the loop's mechanics are explained once on `/loop`,
  which is a static page and not a record.

## Acceptance criteria

- Two boxes in "Running now" mean two workers. Nothing else creates a box.
- Every card in the rail is the same shape and is titled by its author.
- Every job card is selectable and opens a backtest on the right.
- The centre pane contains one backtest and nothing else.
