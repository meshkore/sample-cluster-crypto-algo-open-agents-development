---
id: QUANT6
title: "Expose parallel backtest and multi-agent orchestration in real time"
status: in_progress
priority: high
owner: codex-lead
category: quantlab
initiative: liquid-ml-research
created: 2026-08-01
updated: 2026-08-01
tags: [orchestration, agents, telemetry, dashboard]
depends_on: [LAB3, QUANT2]
blocks: []
---

## Outcome

Make the dashboard distinguish these concurrent workstreams without empty or
misleading state: data ingestion, signal preparation, chronological Phase-1
backtest, Phase-2 forward evaluation, Codex research/build work and Claude
validation work. The current strategy must remain visible during signal
preparation and then transition into its live equity curve, while the prior
completed result remains separately identifiable.

## Orchestration contract

- The backtest worker owns only the current strategy's calculation.
- Codex and Claude may research/review the next bounded increment concurrently,
  publishing lifecycle summaries to the public Wall.
- A coordinator may hand reviewed local advisory output to a builder, but public
  peer messages remain observational and never trigger execution.
- Each workstream reports explicit phase, strategy number, asset/date progress,
  start time and last update; stale work is labelled rather than erased.

## Acceptance criteria

- `PREPARING_SIGNALS 84/386` is visibly labelled as strategy signal generation,
  not a data download or an invisible next strategy.
- The screen shows current strategy number, last completed strategy and all
  active local agents at the same time.
- The live curve/trade trail switches from precompute to chronological execution
  without blanking the active strategy context.
- Tests cover phase transition, stale worker state and parallel agent telemetry.
