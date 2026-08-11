---
id: DOCS1
title: "Document the monitor's data contract for every agent that feeds it"
status: done
priority: high
owner: master
category: docs
initiative: public-state-mirror
created: 2026-08-11
updated: 2026-08-11
tags: [docs, monitor, frontend, contract, agents]
depends_on: [DESIGN3]
blocks: []
---

## Scope

The monitor had no documentation anywhere. An agent arriving at this repository
could not learn, without reading the page's source, that a hypothesis is two
runs rather than one, that `era` is decided by `trade_from` and not
`window_start`, that pairing hashes the genome rather than matching label
suffixes, or that the page exists in three copies of which only one is editable.

Every defect this surface has had came from that gap: data arriving in a shape
the page could not interpret, and the page guessing.

## Delivered

- `.meshkore/docs/architecture/monitor-frontend.md` — the contract. The three
  copies of the page and the deploy path; the three endpoints and the
  one-shape-two-hosts rule; the two-era model with `era`/`pair_key` derived
  rather than stored; the fields a run row must carry; the heartbeat's shape
  and the `last_backtest` vs `pair` distinction; a six-step checklist for
  adding a field end to end; the six invariants that were each a real bug; and
  what deleting runs actually requires across both surfaces.
- `.meshkore/context/architecture.md` — points at it, and now describes the
  four real top-level folders instead of `src/quantlab`, which has not existed
  for some time and would have sent an agent looking for the frontend in the
  wrong tree.
- `.meshkore/docs/INDEX.md` — indexed.
- `CONTRACT.md` — a contributor-facing section: launch both halves with
  identical parameters except `trade_from`, or the result cannot be read.
- `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` — two rules in the OPERATOR_CONTENT
  block, byte-identical across all three, so the first file any CLI reads
  carries both the pairing requirement and the never-hand-edit-the-copies rule.

## Acceptance criteria

- An agent can learn the pairing requirement without reading page source.
- The three OPERATOR_CONTENT blocks stay identical.
- No document claims a path that does not exist.
