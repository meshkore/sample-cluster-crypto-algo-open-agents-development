---
id: self-improving-arena
title: "A laboratory that scores curves properly and improves itself unattended"
status: active
priority: critical
oneliner: "Rank on the shape of the equity curve, not its total return, and let an unattended surrogate-assisted search refit its own models and publish what beats the champion."
modules: [quantlab, trading-system, public-mirror, tests]
target: "continuous"
created: 2026-08-15
updated: 2026-08-15
owner: master
related: [liquid-ml-research, public-state-mirror, intraday-second-system]
---

## Why this exists

The operator looked at the reigning champion's equity curve and described what
ranking on total return had bought: flat for three years, everything earned in
the 2021 bull run, a quarter given back from the peak, four consecutive losing
months, and an ending below its own high. Then the question no measure in this
laboratory could answer — *what happens to someone who buys at the top of that
chart?* They lose everything the strategy ever made. Final return only ever
describes the person who bought on day one.

Second requirement, given at the same time: the laboratory must not stop when the
operator does. It has to keep proposing, measuring, learning and publishing
without a person in the loop, and without a language model in the loop either —
the previous continuous loop spawned headless agents and burned sixty per cent of
a weekly subscription in one day for one measurable result.

## What is live

**The objective.** `quantlab_manager/quality.py` scores a curve as the geometric
mean of six properties, so each holds a veto and no amount of return buys past a
catastrophic drawdown: growth (log scale, full marks at +2,000%), the return of
the unluckiest buyer, maximum drawdown, ulcer index, longest run of losing
months, and the R² of log equity against time. Applied in exactly three places
and there is no fourth — `hypothesis_scan.money` fits sizing on it,
`Orchestrator._publish` stamps it on every run reaching the mirror, and the
Cloudflare Worker crowns the public board on it.

**The arena.** `orchestrator-manager/scripts/arena.py`, supervised by
`arena-forever.sh`. Three things refit themselves and none is a language model:

1. a gradient-boosted surrogate over the search space, refit every round on every
   genome ever measured, ranking 1,500 proposals so only 40 are measured;
2. an evolving population — elites crossed and mutated, a quarter random
   immigrants so the surrogate cannot confirm itself;
3. the strategy's own meta-label, refit per winning genome and the whole backtest
   pair re-run with it, published beside its control.

Its efficiency is reported rather than asserted: `rank_correlation` per round is
the Spearman between what the surrogate predicted and what that round turned out
to be, computed before the truth was known.

## What it has already established

- **The edge decayed at the end of 2024.** Six promoted systems, six different
  trigger hours, thresholds 0.75% to 2.5%: all positive across 2018–2024, all
  negative in 2025, all negative in 2026. The sealed year is not a separate
  puzzle — it is year two of a decline inside the training data, hidden because
  seven good years outweigh one bad one in an eight-year sum.
- **Filters are four for four.** Market gate at 40%, gate at 30%, a borrowed
  meta-label, and a purpose-fitted one: every one improves training and hollows
  out 2026. A filter selective enough to fix the training curve abstains through
  the sealed year, and abstention reads as a positive number.
- **The board's positive 2026 figures were abstentions.** The three best-scoring
  training systems took 1, 0 and 3 sealed trades. Everything with enough sealed
  trades to judge is negative there.
- **The screen does not predict the engine.** Six recorded comparisons, five
  collapse to zero, and the killer is `unlucky` every time.

## Task plan

- #QUANT30 in progress — the objective, the arena, and the four corrections it
  needed before it could run unattended. Running now.
- #QUANT31 pending — the recency veto. The change that attacks the decay rather
  than its symptom, and the one decision waiting on the operator.
