---
id: QUANT5
title: "Expose the trading timeframe and use incremental local market-data storage"
status: pending
priority: high
owner: codex-lead
category: quantlab
initiative: liquid-ml-research
created: 2026-08-01
updated: 2026-08-01
tags: [data, timeframe, caching, dashboard]
depends_on: [QUANT2]
blocks: []
---

## Outcome

Show the active signal/execution timeframe prominently in the Current and Best
forward dashboard views. Treat validated local datasets as the source of truth:
one initial historical download per symbol/timeframe, then append only missing
bars from the last verified timestamp. A full re-download is permitted only as
an explicit repair action after a failed audit.

## Acceptance criteria

- Every visible strategy states its signal and execution timeframe.
- A normal loop never requests an already audited historical range again.
- Incremental updates retain the manifest/checksum lineage and reject overlap,
  gaps or a changed historical payload.
- Tests cover initial download, no-op cache hit, append and repair mode.
