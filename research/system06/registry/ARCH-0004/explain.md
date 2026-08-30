# ARCH-0004 — Wide universe + seasoning gate (causal listing age)

*Registered 2026-08-30T16:31:38.100968+00:00* · parent **ARCH-0003** · code `c6f56f3`

Fixes the flaw that sank ARCH-0003. The universe screen asks 'does this coin have 4.4 years of history?' ONCE, today - but the book needs that answer at each bar. A coin with four years of history in 2026 had four months of it in 2018, and we were trading it as though the screen had vetted it. That is a look-ahead in the MEMBERSHIP of the universe rather than in prices, and it lines up exactly with the years that failed: 2018 for the full-history candidate, 2019/2020 in the walk-forward.

The seasoning module asks the question causally: a symbol is untradable until it has min_age_days of its own history at that moment.

## Structure

- **modules**: ['oracle-nn', 'meta', 'stops', 'regime', 'sizing/money-model', 'crowd', 'seasoning']
- **labeller**: zigzag-1pct
- **features**: ['ohlcv-causal', 'trend', 'vol', 'momentum']
- **universe_id**: universe_deep.json:24
- **timeframe**: 15m
- **pipeline**: generate>filter>rank>size>survive

## Diagram

See `diagram.mmd` (mermaid).

## Backtests

Every measurement attached to this architecture is appended to `backtests.jsonl`, newest last.
