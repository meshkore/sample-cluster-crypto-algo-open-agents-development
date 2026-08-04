---
id: QUANT11
title: "Combine established factors (trend, momentum, order-flow) into one majority-vote strategy"
status: completed
priority: high
owner: unassigned
category: quantlab
initiative: liquid-ml-research
created: 2026-08-04
updated: 2026-08-04
tags: [hypothesis, ensemble, trend, momentum, order-flow]
depends_on: []
blocks: []
---

## Why this exists

Nine single-factor hypotheses (trend persistence, volatility expansion,
volume climax, trade abstention, SuperTrend+ADX on two scopes, Donchian
breakout) have been tested here without one clearing the drawdown/cost/
benchmark bar. The operator's explicit instruction: stop breadth-first
single-factor hunting and commit to one serious, well-reasoned combined
strategy instead of another isolated idea on another branch.

## What was built

`H-MULTI-001`, family `multi_factor_trend`: a majority vote across three
independently-computed, individually well-established factors --

1. **Trend** -- close above its N-bar SMA, and that SMA still rising.
2. **Momentum** -- RSI above a floor.
3. **Order-flow imbalance** -- the taker-buy-volume share of total volume
   (already present in every `Bar` from Binance's own kline response,
   `taker_buy_volume`), averaged over a short window, compared against its
   own longer-window baseline.

Long once >=2 of 3 agree (deliberately not requiring consensus, to trade
more often, per the operator's explicit request for trade volume). The
position is not closed by a single dissenting factor -- only once all 3
turn against it, reusing H-DONCH-001's asymmetric entry/exit lesson (this
was posted to the cluster Wall as an open design question and settled with
that reasoning rather than assumed).

**Honesty notes, both already in the hypothesis text and worth repeating
here:**
- The order-flow "factor" is not literal market-maker detection. There is
  no L2 order book anywhere in this pipeline -- taker-buy ratio from public
  OHLCV klines is the closest available proxy for aggressor imbalance, and
  it may simply be adding noise dressed up as a signal.
- No fitted ML model is used. A learned combiner over these same features
  was considered and rejected for this pass: this lab's causal-replay
  engine has no train/inference split, and fitting a classifier without
  one carries a real look-ahead risk a fixed-rule vote does not. Worth
  revisiting as a second iteration if the rule-based version clears
  Phase 1.
- Trading on 2-of-3 rather than requiring unanimity is a deliberate choice
  to trade more often, not a claim that more trades means a better
  strategy -- it very plausibly means a lower per-trade edge instead.

Runs on the lab's default daily-bar, full liquid-universe scope (no data
override needed, unlike H-STA-001) -- this is a swing/position system by
construction, not an intraday one.

Committed directly to `main`, not a side branch, per explicit instruction:
this is meant to be evaluated as the flagship candidate, not one more
parallel experiment.

## What was NOT promised

No result is claimed yet. This hypothesis is exactly as unproven as every
other one tested here until this lab's own Phase-1 pipeline runs it. It
combines individually well-established ideas, which is a better starting
point than an unverified external mechanism, but that is not the same
thing as evidence that it works.

## Acceptance criteria

- No exemption from the drawdown limit, cost model or benchmark comparison.
- Whatever the result, it is reported honestly, including if it fails —
  which is what has happened to every prior hypothesis here.
- If it fails, the specific reason (which factor(s) dragged, whether trade
  frequency itself was the problem) should be diagnosable from the same
  per-asset/per-trade data every other family already produces, not a new
  ad hoc analysis.

## Result (2026-08-04)

**Phase-1** (S00840 lineage, S00841, pre-2026 daily/386-asset universe, params
`trend_period=95, rsi_period=14, flow_short=5, flow_long=20, rsi_floor=50,
min_votes=2`): **+36.97% return, 16.0% max drawdown, 2,195 trades, 36.5% win
rate**, 116 assets traded. Buy-and-hold reference over the same window:
+1950.59%.

**Walk-forward**: 12 folds evaluated, **8 profitable**, consistency 0.667,
eligible = 1. The first new family to clear the gate.

**Locked forward 2026** (FWD2-S00841-20260803, 2026-01-01 → 2026-08-03):
**-9.57% return, 12.64% max drawdown, 527 trades, 27.7% win rate**, 23 assets
traded. Equal-weight market over the identical window: **-22.6%**.

So: the best Phase-1 result this lab has produced, walk-forward eligible, and
it still loses 9.57% out of sample while beating the market by ~13 points. Both
halves of that matter. The 527 trades settle the operator's objection that the
engine was not really trading candle by candle — it was. Not promoted; a
long-only strategy that reliably loses less than a falling market is not the
same thing as a strategy.

Two structural findings came out of reviewing this run, both now fixed
elsewhere:

- The champion card's "13" was `assets_traded`, not `trades` — S00743's forward
  run has `assets_traded=13` and `trades=41`. A UI/semantics confusion, not a
  strategy that trades 13 times a year.
- A graded confidence (this family emits `votes/3`, so 0.667 for a 2-of-3
  vote) is compared against the money-management `minimum_confidence`
  threshold. S00743's evolved policy carries `minimum_confidence=0.75`, which
  would reject every 2-of-3 vote outright — a money-management setting that
  silently mutes a signal family and looks exactly like the signal failing.
  This is why H-SMARSI-001 (QUANT13) emits binary 1.0.
