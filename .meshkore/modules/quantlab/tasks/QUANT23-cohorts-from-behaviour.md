---
id: QUANT23
title: "Define cohorts from behaviour rather than from listing date"
status: pending
priority: medium
owner: unassigned
category: quantlab
initiative: global-market-trend
created: 2026-08-11
updated: 2026-08-11
tags: [cohorts, clustering, taxonomy, measurement]
depends_on: [QUANT22]
blocks: []
---

# Cohorts from behaviour

## Why the current cohorts are a first cut

They are assigned from **listing date and turnover**, because those are the only
signals in the archive that carry information about what kind of coin something
is. That is defensible and it is crude: it puts a serious 2023 infrastructure
launch in the same bucket as a 2023 dog coin.

The operator asked for BTC / major alts / the rest / memecoins. The archive has
no sector labels, and inventing them from price is a taxonomy fitted to the
answer unless it is done carefully.

## What to try

- Cluster on **behaviour**: realised volatility, beta to the market, drawdown
  depth, turnover stability, survival. These are facts about a coin, available
  point-in-time, and they do not require anybody's opinion about what a
  memecoin is.
- Validate the clusters **out of sample in time**: fit the clustering on
  2017-2021, check the assignment still separates behaviour in 2022-2025. A
  cluster that only exists in the period that defined it is an artifact.
- Compare against the cheap signals already found: Binance's `1000x` low-price
  prefix (three assets here) and listing era. If clustering does not beat
  listing date, keep listing date and say so.

## Acceptance

A point-in-time cohort assignment that a stranger can re-derive, and a
measurement showing it separates forward behaviour better than the listing-date
cut. Otherwise the listing-date cut stands.
