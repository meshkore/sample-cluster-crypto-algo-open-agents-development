---
title: "Backtester"
category: modules
updated: 2026-08-11
owner: capitaharlock
status: draft
---

# Backtester

**Purpose:** The instrument. `backtester/quantlab_backtester/` — candles,
~79 precomputed indicator columns per symbol, order fills, the book, scoring.

## Surface

Data download and validation (`data.py`), the on-disk indicator panel cache
(`indicator_store.py`, `indicators.py`), the bar-by-bar session (`session.py`,
`engine.py`), the run store (`ledger.py`) and the HTTP service (`server.py`).

## The rule that makes this module different

It is the same instrument for everybody, which is the only reason two people's
numbers can be compared. Changing it invalidates every result already recorded,
so it changes only in its own pull request with its own argument — never as part
of a strategy contribution. `orchestrator-manager/scripts/check_layering.py`
enforces the boundary.
