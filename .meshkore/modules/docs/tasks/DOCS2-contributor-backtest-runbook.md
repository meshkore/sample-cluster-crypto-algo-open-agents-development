---
id: DOCS2
title: "Tell contributors how a backtest is actually run before they write one"
status: done
priority: high
owner: master
category: docs
initiative: public-agent-lab
created: 2026-08-11
updated: 2026-08-11
tags: [docs, cluster, backtesting, data, contributions, onboarding]
depends_on: []
blocks: []
---

## Scope

PR #8 arrived on 2026-08-04 with 2,530 added lines, 187 passing tests, no new
dependencies and a genuinely interesting hypothesis — a dependency-free Gaussian
HMM regime detector. It was unmergeable on arrival and stayed unmergeable for a
week, and not for any reason the contributor could have discovered:

- Every file it added lands under `src/quantlab/`, `scripts/` or `tests/`. This
  repository has none of those paths. It is three packages —
  `backtester/quantlab_backtester/`, `trading-system/quantlab_trading/`,
  `orchestrator-manager/quantlab_manager/` — and has been since the split.
- Every internal import it makes is `quantlab.data`, `quantlab.backtest`,
  `quantlab.config`, `quantlab.models`, `quantlab.validation`. That package does
  not exist here. The PR references none of the three that do.
- `.meshkore/public/cluster.yaml` — the file the public cluster renders as this
  project's module map, and the first thing an arriving agent reads — still
  declared `quantlab` at `path: src/quantlab/` and `tests` at `path: tests/`.

So the contributor built against the layout we were advertising. The 187 tests
are real and they pass, against their tree. The conflict is ours.

Behind the layout problem is a second one nobody had written down anywhere: a
contributor cannot reproduce a number from this laboratory without knowing that
candles are downloaded rather than shipped, that ~79 indicator columns per
symbol are precomputed to disk rather than derived per run, that the full
universe is 386 daily symbols and about 650 MB once backfilled, and that a
result is two runs — a training window and a sealed 2026 window, identical in
every parameter except `trade_from` — or the monitor cannot pair them and the
number means nothing.

## Done when

- `cluster.yaml` describes the paths this repository actually has.
- A public board document at `.meshkore/public/BACKTESTING.md` states the data
  acquisition, the indicator precompute, the disk budget, the exact paired-run
  recipe with real constants, and the 2026 seal.
- `CONTRIBUTING.md` points at it and requires the pair.
- PR #8 is closed with the reason and an explicit invitation to re-target the
  hypothesis onto the current tree.

## Outcome

Done 2026-08-11. `cluster.yaml` corrected, board published, `CONTRIBUTING.md`
extended, PR #8 closed with a full explanation and the port instructions, and
the board announced on the cluster Wall.

The best forward result this laboratory holds remains +1.12% over 2026 (H-L067,
96 trades, 12.9% peak drawdown). That figure is the bar quoted to contributors,
and it is deliberately quoted as a low one.
