---
id: S10-2
title: "B. New system: initialise trading-system/systems/system010_conditioned_rl"
status: backlog
priority: high
owner: unassigned
profile: developer
category: trading-system
initiative: system-ten-conditioned-rl
created: 2026-09-27
updated: 2026-09-27
tags: [system10, skeleton, phase-b]
depends_on: [S10-1]
blocks: [S10-4, S10-5, S10-7]
---

> Read `.meshkore/context/system10-design.md` before starting. It is the plan this task is one piece of, and it carries
> the laboratory's standing rules under "Our conditions" and the kill conditions under section 7.

## The ask

*"Generacion de un nuevo sistema"*: the package, its runtime folder and its documentation,
registered so the laboratory can see it, and abstaining until it has a policy.

## What to build

1. `trading-system/systems/system010_conditioned_rl/` with `__init__.py`, and a brain
   registered via `@register` from `quantlab_core.brains` whose `decide(tick)` **abstains**
   (no orders) until `policy.py` has an exported policy. Modules named as in the design
   section 9: `region.py`, `env.py`, `policy.py`, `train.py`, `export.py` - each may be a
   documented stub, but the file and its docstring exist so later tasks land in named places.
2. Layering: add `system006_oracle_net_15m` as a **declared lineage** for `system010` in
   `orchestrator-manager/scripts/check_layering.py` (dataset, oracle, channels only). No
   import of `live-trading/`. The check passes.
3. `docs/SUMMARY.md` with the six headings; *Hypothesis* and *What it is* written from the
   design; the other four say "not yet written up". `docs/RESULTS.md` with the two eras
   labelled and empty. `docs/context.json` with `status: "workshop"`, `activity: "in
   development"`, `period.opened: <date>`, `data` from the catalogue, `results` empty.
   `trading-system/tests/test_system_docs.py` passes.
4. `research/system10/` with `README.md` (what is committed, what is scratch - mirror
   `research/README.md`), `rnd/agenda.jsonl` and `rnd/program.jsonl` empty, `tools/`, and
   `.gitignore` entries for `*.npz`, `*.pt`, `*.log`, `*.err`, `*.out`, `_auto_*`.
5. `trading-system/systems/README.md`: row 010 added as `workshop`, sealed 2026 "not spent",
   verdict "opened <date>; see the initiative". "The next system is 011."
6. `research/README.md`: the `system10/` row.

## Done when

`quantlab_core.brains.available()` lists `system010_conditioned_rl`; a dry backtest over one
research year runs and places zero trades; the docs test passes; layering passes; one commit.
