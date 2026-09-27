---
id: S10-12
title: "H. Forward: package 010 as a live engine and run it in a shadow paper book beside 06"
status: backlog
priority: high
owner: unassigned
profile: developer
category: trading-system
initiative: system-ten-conditioned-rl
created: 2026-09-27
updated: 2026-09-27
tags: [system10, live, engine, paper, phase-h]
depends_on: [S10-11]
blocks: []
---

> Read `.meshkore/context/system10-design.md` before starting. It is the plan this task is one piece of, and it carries
> the laboratory's standing rules under "Our conditions" and the kill conditions under section 7.

## The ask

The live layer was built so that a better brain replaces the old one without resetting the
book. 010 must fit that contract exactly, and prove itself in paper beside 06 before any
swap - and the swap itself happens only on the operator's word.

## What to build

1. `system010_conditioned_rl/export.py` writes `live-trading/engines/v4-rl-<name>/` with a
   manifest (provenance, exams, sealed figure), the policy weights, the region predicate,
   the feature registry hash, and the levers the manifest declares so the trader's
   "refuse to trade degraded" check can verify them.
2. A `Brain` adapter in `system010` so `decide(tick)` with `tick = {timestamp, candles,
   account}` returns `Decision.orders` in the live layer's shape, consulting the policy only
   inside R and managing exits outside it. `live-trading/tests/test_live_layer.py` gains a
   test that a v4 package loads, feeds, and decides on a recorded tick.
3. **Shadow book.** A second paper book under `live-trading/state/shadow/` driven by the v4
   engine on the same bars as 06's live book, published to the Trading area as a second
   curve. It never places orders in the primary book.
4. Only on the operator's word: `engines/current.json` to v4. The `ENGINE_SWAP` row is
   logged, the book is untouched, and 06's package stays on disk for a swap back.

## Done when

The v4 package passes the live-layer tests, the shadow book has run beside 06 for the
number of bars the operator asks for, and the swap - if he asks for it - is one line in the
order ledger with the book intact across it.
