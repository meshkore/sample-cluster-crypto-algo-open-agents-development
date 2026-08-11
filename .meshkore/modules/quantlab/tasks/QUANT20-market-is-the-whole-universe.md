---
id: QUANT20
title: "Define the market as every listed asset, not six survivors"
status: completed
priority: critical
owner: unassigned
category: quantlab
initiative: global-market-trend
created: 2026-08-11
updated: 2026-08-11
tags: [detector, market-definition, breadth, measured]
depends_on: []
blocks: [QUANT22, QUANT24]
---

# Define the market as every listed asset

## What was wrong

The major-trend detector built its composite and its breadth from six assets
chosen for having the longest continuous history — which is to say, from
survivors. Scored against the broad market's own forward return, that basket is
**not correctly ordered**: its SIDEWAYS bucket falls harder than its BEAR
bucket (−4.16% against −2.15%).

Breadth was the sharper failure. Six names can only report 0, 1/6, 2/6 … and
the thresholds sit at 0.35 and 0.50, so one asset changing its mind moved the
market between bull and bear.

## What shipped

`market_scope` (`universe` | `basket`) and `weighting` (`equal` | `turnover` |
`sqrt`), both searchable, defaulting to the measured winner: the whole listed
universe, equal weight. BEAR forward return −2.43%, correctly ordered, and the
bear branch's share of the falling fold goes 34.0% → 57.1%.

Costs 1.9s for 3,059 bars × 385 assets, so the wider market is free.

## Evidence

`orchestrator-manager/scripts/market_shootout.py`, recorded as H-L086M. Every
variant scored against the same broad benchmark so none could win by being easy
to predict.

## What is deliberately unresolved

Turnover weighting was the only variant right in all four folds while failing
the pooled ordering. It is kept searchable rather than discarded: the full
objective should settle a disagreement this real, not a scorecard.
