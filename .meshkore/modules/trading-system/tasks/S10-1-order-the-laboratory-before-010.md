---
id: S10-1
title: "A. Cleanup: order the laboratory before opening system 010"
status: done
priority: high
owner: unassigned
profile: developer
category: trading-system
initiative: system-ten-conditioned-rl
created: 2026-09-27
updated: 2026-09-30
tags: [system10, cleanup, phase-a]
depends_on: []
blocks: [S10-2]
---

> Read `.meshkore/context/system10-design.md` before starting. It is the plan this task is one piece of, and it carries
> the laboratory's standing rules under "Our conditions" and the kill conditions under section 7.

## The ask

The operator's first phase: *"primero limpieza"*. Open 010 into a tidy laboratory, so that
nothing it inherits is stale and nothing it measures is confounded by a leftover.

## What to do

1. `research/system06/`: delete scratch that the README says is not committed (`_auto_*`
   folders, `*.log`, `*.err`, `*.out`, `__pycache__`, stale `.npz` not referenced by
   `live-trading/engines/*`). Do NOT touch `rnd/`, `registry/`, `knowledge/`, `best.json`,
   `config.json`, the engine caches or anything the live trader reads
   (`live-trading/state/`). Check `git status` shows only deletions of ignored or scratch files.
2. Confirm the standing circuit is intact and untouched: `system06-watchdog` task Ready, the
   live trader logging bars, `engines/current.json` = the engine the operator chose. Record
   the three facts in the task's closing note.
3. Regenerate `.meshkore/context/LESSONS.md` (`python -m quantlab_catalog.lessons`) so 010's
   first instruction - read the previous systems - reads a current file.
4. Run the three suites (`backtester/tests`, `trading-system/tests`,
   `orchestrator-manager/tests`) and `orchestrator-manager/scripts/check_layering.py`.
   All green, or the failures are listed by name in the closing note and fixed before S10-2.
5. `trading-system/systems/README.md`: confirm "The next system is 010" and that every row
   has a verdict. Add nothing about 010 yet - S10-2 does.

## Done when

Three suites green, layering green, `LESSONS.md` regenerated, the scratch gone, the live
circuit confirmed intact, and one commit whose message lists what was deleted and why.
