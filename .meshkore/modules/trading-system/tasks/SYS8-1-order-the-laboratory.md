---
id: SYS8-1
title: "Order the laboratory: shared data catalogue, documentation standard, one box per system"
status: done
priority: high
owner: unassigned
category: trading-system
initiative: system-eight-from-zero
created: 2026-09-08
updated: 2026-09-08
tags: [catalogue, documentation, dashboard, cleanup]
depends_on: []
blocks: [SYS8-2, SYS8-3]
---

## Scope

Everything this laboratory downloaded lived inside one system's folder. Move it behind a
single import, document what each system learned and refused, and make the public list a
reading list rather than a run log.

## What was done

- `trading-system/quantlab_catalog/` — the shared catalogue: `load_universe`, `research`,
  `forward`, `feargreed`, `funding`, `onchain`, `reference_markets`. Stores moved to
  `backtester/data/{external,universe,indicators}`; legacy paths still resolve, so a
  half-migrated machine keeps working.
- `inventory` reports what exists AND what does not — no 1h or 5m candles, no order-book
  depth, no news feed, no ALFRED vintages, each with its reason.
- `prune` fixed a cache leak that had the eight-month sealed window occupying 9.1 GB
  against 403 MB for eight years: 5,646 near-identical copies, 385 of BTCUSDT alone.
  9.1 GB reclaimed. It is a tool rather than a one-off delete because the leak recurs on
  every forward refresh.
- `.meshkore/context/system-documentation-standard.md` plus a `docs/` folder for all
  seven systems. System 06's is written in full: 9 things that helped, 10 that hurt, 5
  open questions, 9 transferable rules. Enforced by `tests/test_system_docs.py`.
- The public page now shows one box per SYSTEM with a **Log** tab rendering its summary,
  delivered through a route that is already live, so it needed no Worker deploy — there
  is no node on this machine and a feature that needs a deploy to appear does not appear.

## Acceptance

716 tests pass. Verified live on both worker URLs: 33,491 bytes, seven systems. The
browser test `research/system06/preview/test_systems_tab.py` asserts on the DOM, because
a markdown table that silently renders as a paragraph is invisible to a static check.
