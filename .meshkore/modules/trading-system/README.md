---
title: "Trading system"
category: modules
updated: 2026-08-11
owner: capitaharlock
status: draft
---

# Trading system

**Purpose:** Where a strategy lives — the decisions, and nothing about how they
are measured. The folder holds **three shared packages and one folder per
hypothesis**; `trading-system/systems/README.md` is the index and the map.

## Surface

`quantlab_core/` — the shared runtime, and only that: the brain registry
(`brains.py`), the tick contract (`runner.py`), money and risk policy
(`policy.py`) and the per-bar liquidity gate (`universe.py`). It imports no
system. Until 2026-09-16 it also held System 001's grammar and regime router,
which meant the shared runtime imported a strategy — the exact coupling the
folder split exists to prevent.

`quantlab_catalog/` — the shared data catalogue. One import for candles, the
frozen universe, funding, Fear & Greed, on-chain series and reference markets.
`quantlab_catalog.paths.DATA_ROOT` is the single location of every byte of data.

`quantlab_ml/` — the shared learning library: the feature table, triple-barrier
labels, purged time-series splits and meta-labelling.

`systems/systemNNN_<hypothesis>/` — one folder per system, numbered by the day it
opened. Nine of them, of which one is the champion and one is a live candidate;
the rest are frozen, closed or stopped, each with its own `docs/`. **Read
`systems/README.md` first** — it is one row per system with its sealed 2026
result and its verdict.

The separation is enforced, not conventional:
`orchestrator-manager/scripts/check_layering.py` fails the build if a system
imports another system (outside a declared lineage), if a shared package imports
a system, or if anything below imports the manager.

## Where a contribution lands

A new hypothesis is a new folder under `systems/`, and registering the brain is
still the only wiring step — `available()` discovers any package on the path
named `systemNNN_*`, so a system that exists cannot be invisible. Sizing, stops
and the drawdown mandate live in `quantlab_core/policy.py` and changing them
changes every system's recorded result. See `.meshkore/public/BACKTESTING.md`
for how to run one and what result to report.
