# ARCH-0001 — Narrow trend book (the shipping architecture)

*Registered 2026-08-30T16:31:38.006820+00:00* · first architecture on record · code `c6f56f3`

The architecture in production. One pooled TCN scores every asset each bar; a second (meta) model refuses the entries it expects to lose; a slow-trend veto and a market-breadth regime gate cut the rest; the surviving names compete for two slots by conviction; a learned money model sizes what is left. Long-only spot, no leverage.

Adopted 2026-08-29 with the balanced configuration after the operator's balance criterion selected it on research years.

## Structure

- **modules**: ['oracle-nn', 'meta', 'stops', 'regime', 'sizing/money-model']
- **labeller**: zigzag-1pct
- **features**: ['ohlcv-causal', 'trend', 'vol', 'momentum']
- **universe_id**: universe.json:14
- **timeframe**: 15m
- **pipeline**: generate>filter>rank>size>survive

## Diagram

See `diagram.mmd` (mermaid).

## Backtests

Every measurement attached to this architecture is appended to `backtests.jsonl`, newest last.
