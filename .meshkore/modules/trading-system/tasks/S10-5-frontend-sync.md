---
id: S10-5
title: "D. Frontend: 010 appears in the systems list with a model card, published with no deploy"
status: done
priority: high
owner: unassigned
profile: ui-developer
category: trading-system
initiative: system-ten-conditioned-rl
created: 2026-09-27
updated: 2026-09-30
tags: [system10, frontend, monitor, phase-d]
depends_on: [S10-2]
blocks: []
---

> Read `.meshkore/context/system10-design.md` before starting. It is the plan this task is one piece of, and it carries
> the laboratory's standing rules under "Our conditions" and the kill conditions under section 7.

## The ask

*"Sincronizacion con el frontend"*. The operator's monitor has three areas - live trading,
the strategy being trained now, and the previous strategies. 010 must show up in the second
and third the moment it exists, and in the first only if it reaches phase H.

## What to build

1. The systems list: 010's box comes from `docs/context.json` through
   `cf_pusher.build_systems()`; confirm it renders with `status: workshop` and its four tabs
   (Results, Theory, Diagram, Log). Theory = the design's sections 0-3; Diagram = the
   design's section 3 drawn as SVG per `.meshkore/docs/architecture/monitor-frontend.md`.
2. The training area: 010 is an `ai-model` system, so the Training button shows a **model
   card**, not a curve. Define 010's card fields (region coverage per year, clone
   validation, offline-RL validation, seeds, current walk-forward year, GPU lane state)
   and the file `research/system10/model_card.json` the trainer will write; the page shows
   "not published yet" until it exists.
3. The pusher reads `research/system10/` state files exactly as it reads 06's and publishes
   them to the public Worker **with no deploy** (the details-map route). Worker parity for
   the model card per the frontend doc.
4. A Playwright test (local only, as for 06) that the 010 box renders, the model card
   placeholder shows, and 06's Trading area is unchanged.

## Done when

The public page shows 010 in the systems list with its four tabs, the training area shows
the card placeholder, the Playwright test passes, and nothing about 06's panels changed.
