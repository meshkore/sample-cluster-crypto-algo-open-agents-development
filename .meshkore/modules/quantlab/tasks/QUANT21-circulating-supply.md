---
id: QUANT21
title: "Acquire circulating supply so capitalisation is computable at all"
status: pending
priority: high
owner: unassigned
category: quantlab
initiative: global-market-trend
created: 2026-08-11
updated: 2026-08-11
tags: [data, market-cap, dependency, external]
depends_on: [QUANT20]
blocks: [QUANT25]
---

# Acquire circulating supply

## Why

The operator's definition of the cycle is capitalisation: the bull run ends at
peak total market cap and the bear ends at the trough. **We cannot compute
that.** Market cap is price × circulating supply and this laboratory holds no
supply data — the archive is Binance OHLCV and nothing else.

Every index shipped in QUANT20 is a proxy. Turnover weighting is the closest
one available and it is not the same thing: a coin can trade heavily and be
small, and a large holding that never moves is invisible to it.

## What this needs

- A supply source (CoinGecko and CoinMarketCap both publish historical
  circulating supply; both are external dependencies and both need review under
  the contribution rules).
- Point-in-time supply, not today's. Using today's supply on a 2018 bar is
  lookahead of the worst kind: it prices 2018 with what was issued since.
- A capitalisation index that is a **sum of values**, which behaves differently
  from the chained-return composite by construction — it moves when a coin is
  issued, and that is the property being bought.

## Acceptance

A capitalisation series over 2017-2025 whose peaks and troughs can be compared
against the chained composite, and a measurement saying which of the two
detects the market's turns better. If the answer is "no better", record it and
stop — the proxy is then good enough and this dependency is not worth carrying.
