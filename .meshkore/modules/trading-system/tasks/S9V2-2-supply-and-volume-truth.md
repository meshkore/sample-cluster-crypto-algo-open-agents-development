---
id: S9V2-2
title: "Real supply histories and published volumes, per asset, point-in-time"
status: active
priority: high
owner: win-opus-5
category: trading-system
initiative: system-nine-reality-alignment
created: 2026-09-14
updated: 2026-09-14
tags: [system09, v2, data, supply, volume, point-in-time]
depends_on: [S9V2-1]
blocks: [S9V2-3]
---

## The ask

*"Estamos respetando los precios de Bitcoin y de todos los assets del mundo. Estamos
respetando los mismos volúmenes de trading registrados y publicados de todos esos assets."*

## What v1 does today

- **Price**: already the published close. Keep, and assert it in a test.
- **Volume**: the Binance tape, which is real but is one venue. The share of global volume that
  venue represents is never measured.
- **Supply**: a single CoinGecko snapshot carried backwards across eight years. This is the
  largest known falsity in the model.

## What to build

- A daily circulating-supply series per asset, from listing to 2025-12-31, with its vintage
  recorded. Bitcoin already has one (`chain_total-bitcoins`); the other thirteen need one.
- Published per-asset daily volume, and the measured Binance share of it.
- A rest-of-market aggregate carrying the assets we do not model, so the global total closes.
- Every series enters through the clock: publication lag, point-in-time vintage, no
  forward-fill of a flow.

## Done when

`harvest` can rebuild every series from scratch, each carries its lag, and S9V2-1's float error
drops to within tolerance at all three checkpoints.
