---
id: SYS8-3
title: "Initialise system 08: the working loop, running, once the hypothesis exists"
status: archived
priority: high
owner: unassigned
category: trading-system
initiative: system-eight-from-zero
created: 2026-09-08
updated: 2026-09-10
tags: [system08, loop, daemon, watchdog, hypothesis]
depends_on: [SYS8-1, SYS8-2]
blocks: []
---

## Scope

`trading-system/system008_residual_momentum_ls/` exists and is deliberately empty of ideas. **The
referee is built** — `loop.py`: frame, measure, exam 1, exam 2, price the edge, sealed,
write up. A stage cannot be skipped, cannot be re-run until it passes, and the sealed
window has one door with three locks. Twelve tests hold it, each corresponding to a real
loss.

**The runner is not built**, and that is what this task is.

## Blocked on

**The hypothesis.** The operator holds it (*"ya te lo explicaré"*). A loop that turns
without a claim to test is not an infinite loop, it is noise in the logs, so nothing is
scheduled until the claim exists. This is the only thing blocking; every other dependency
is done.

## What this task does when unblocked

1. A runner that walks candidates through the gate and publishes a heartbeat carrying an
   `owner`, so the public page attributes its work with no page change at all.
2. A watchdog block in the same shape as the system 06 fleet — workers and a deadline in
   a control file, the script named as DATA rather than hard-coded, because a hard-coded
   name once had the watchdog faithfully resurrecting a finished study while the live one
   ran unsupervised.
3. Its own `research/system08/` working directory and sealed ledger.
4. A row appended to `docs/SUMMARY.md` on every adoption or refusal, in the same commit
   as the result — a minute while the numbers are on screen, an afternoon of archaeology
   afterwards.

## Acceptance

The loop runs unattended, survives a reboot, and its first sealed reading — win or loss —
is written by `record_sealed`, which refuses any reading the gate did not authorise.

---

## Closed out — 2026-09-10

Archived with the generation it belonged to. System 08 is in a **design-only** phase: no
code, no backtests, no measurements, until the operator authorises it in words.

Nothing here is lost. Every option and experiment worth revisiting is catalogued in
[`.meshkore/context/experiment-catalogue.md`](../../../context/experiment-catalogue.md),
which is the one place to look before proposing work — so that we do not re-open a question
this laboratory has already answered.
