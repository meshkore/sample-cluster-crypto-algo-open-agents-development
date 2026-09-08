---
id: SYS8-2
title: "Freeze system 06 and stop every job that belonged to it"
status: done
priority: high
owner: unassigned
category: trading-system
initiative: system-eight-from-zero
created: 2026-09-08
updated: 2026-09-08
tags: [freeze, daemons, watchdog]
depends_on: [SYS8-1]
blocks: [SYS8-3]
---

## Scope

Operator, 2026-09-08: *"para todo lo anterior"*. The machine stops belonging to system 06.

## What was done

Stopped five `v4_refnet_search` workers and the hourly `pulse`; the autoloop and the
autotest were already halted by their own flags. `research/system06/STOP` now guards all
four at the watchdog level, and `OPTIMIZE.json`'s deadline was moved to now so the
optimizer fleet cannot return before its authorised 2026-09-20. The watchdog was then run
by hand and relaunched nothing.

v4 had spent 28 hours on five cores refining thresholds for `_wf23_ref` — a net that had
already lost its second exam by forty points — with its leader standing at fit +0.3011
and held-out −0.2928, textbook overfit. The same day's finding (A125) made that class of
edge unable to buy a sealed reading anyway. The Optuna study stays on disk and is
resumable; nothing measured is lost.

**Left running deliberately:** `cf_pusher`, which is the public dashboard's only source
and whose absence would freeze the operator's window, and `wall_listener`, which is
cluster comms rather than system 06 work.

## Acceptance

Two processes remain, both infrastructure. The watchdog was executed after the stop and
resurrected nothing.
