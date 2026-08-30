# ARCH-0002 — Narrow trend book + extreme-fear veto (non-price information)

*Registered 2026-08-30T16:31:38.040861+00:00* · parent **ARCH-0001** · code `c6f56f3`

Adds the first decision input in this project that does NOT derive from price: the real Fear & Greed index, vetoing new entries below the index's own published Extreme Fear boundary. Measured first (A65): entries on the most fearful days were the only losing bucket in the champion's 3,158-trade map, -0.10%/trade at 34% win against +0.96% at 48% in greed.

It is the only lever so far to improve the HELD-OUT median (-0.8% -> +2.0%).

## Structure

- **modules**: ['oracle-nn', 'meta', 'stops', 'regime', 'sizing/money-model', 'crowd']
- **labeller**: zigzag-1pct
- **features**: ['ohlcv-causal', 'trend', 'vol', 'momentum']
- **universe_id**: universe.json:14
- **timeframe**: 15m
- **pipeline**: generate>filter>rank>size>survive

## Diagram

See `diagram.mmd` (mermaid).

## Backtests

Every measurement attached to this architecture is appended to `backtests.jsonl`, newest last.
