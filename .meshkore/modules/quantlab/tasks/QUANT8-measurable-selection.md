---
id: QUANT8
title: "Remove the sizing lookahead and rank strategies against a benchmark"
status: in_progress
priority: critical
owner: master
category: quantlab
initiative: liquid-ml-research
created: 2026-08-02
updated: 2026-08-02
tags: [correctness, selection, benchmark, lookahead]
depends_on: [QUANT7]
blocks: []
---

## Why this exists

Two defects make every number this laboratory has produced unsafe to act on.

**The sizing reads the future.** `portfolio.py` computes each day's volatility
from returns through that day's close, then uses it to size a position filled
at that same day's open. The signal and the liquidity gate are both correctly
lagged; volatility was missed. The engine therefore shrinks exposure on days it
has not lived through yet, which is a systematic flattery: it de-risks exactly
the days that turn out badly. It inflates Phase 1 and Phase 2 alike.

**Nothing is compared to anything.** There is no benchmark anywhere in the
codebase. A long-only crypto strategy that returns +0.2% has told you nothing
until you know what buying and holding returned over the same window. Both
independent reviewers reached this conclusion separately, and the evidence
supports them: across 216 paired runs the Phase-1 rank correlates +0.06 with
the forward rank, so the current selection is measuring noise.

## What done looks like

1. Volatility used for sizing at bar *t* is computed from data through *t-1*,
   consistent with the signal and liquidity lag. A regression test pins it.
2. A benchmark module computes, over the identical window and cost model, both
   buy-and-hold BTC and an equal-weight portfolio of the assets the strategy
   could have traded.
3. Every run stores its benchmark return and its excess return.
4. The champion ranks on risk-adjusted **excess** return, keeping the rule that
   a losing strategy never outranks a profitable one.
5. Results produced by the pre-fix engine cannot become champion. They stay in
   the database for audit, marked with the engine version that produced them.
6. The public page shows the benchmark next to the strategy, so a reader can
   see whether the laboratory beat doing nothing.

## Notes

The walk-forward selection protocol is the next question and deliberately not
in this task. It cannot be evaluated honestly until the engine stops leaking
and there is a benchmark to measure against.
