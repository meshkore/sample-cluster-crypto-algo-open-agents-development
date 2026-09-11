---
id: QUANT25
title: "Stablecoin supply and dominance as a regime input"
status: archived
priority: low
owner: unassigned
category: quantlab
initiative: global-market-trend
created: 2026-08-11
updated: 2026-09-10
tags: [regime, flows, external-data, hypothesis]
depends_on: [QUANT21]
blocks: []
---

# Stablecoin flows as a regime input

## The idea

Everything the detector reads today is **price**. Price is the thing being
predicted, so a detector built only from it is always describing the past.
Stablecoin supply is one of the few widely-available series that is arguably
upstream of price: capital entering the system has to become a stablecoin
before it can buy anything.

Two candidate readings:

- **Aggregate stablecoin supply** growing while prices fall is capital waiting;
  shrinking while prices rise is capital leaving.
- **Stablecoin dominance** (stablecoin cap ÷ total cap) as a contrarian level —
  high dominance at a market low is dry powder.

## Why it is low priority

It needs the supply data from QUANT21 and it is a genuinely new data
dependency, with all the point-in-time hazards that implies. And this
laboratory has a standing lesson that adding inputs before fixing mechanisms
buys nothing: the detector was inverted for its whole life and no amount of
extra data would have shown that.

## Acceptance

A measured improvement to the detector's own scorecard, point-in-time, on the
fittable era. If it does not beat price alone, record the refutation — a
negative result on a popular indicator is worth publishing.

---

## Closed out — 2026-09-10

Archived with the generation it belonged to. System 08 is in a **design-only** phase: no
code, no backtests, no measurements, until the operator authorises it in words.

Nothing here is lost. Every option and experiment worth revisiting is catalogued in
[`.meshkore/context/experiment-catalogue.md`](../../../context/experiment-catalogue.md),
which is the one place to look before proposing work — so that we do not re-open a question
this laboratory has already answered.
