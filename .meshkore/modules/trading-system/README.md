---
title: "Trading system"
category: modules
updated: 2026-08-11
owner: capitaharlock
status: draft
---

# Trading system

**Purpose:** Where a strategy lives. `trading-system/quantlab_trading/` — the
decisions, and nothing about how they are measured.

## Surface

Regime detection (`regime.py`, `regime_system.py`), the rule grammar the search
mutates (`grammar.py`, `space.py`), the four-module router, position and risk
policy (`policy.py`), the brain registry (`brains.py`) and the tick contract
(`runner.py`).

## Where a contribution lands

Here. A new idea is a registered brain or a new rule the grammar can express;
registering is the only wiring step. See `.meshkore/public/BACKTESTING.md` for
how to run one and what result to report.
