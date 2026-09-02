# ARCH-0005 — Narrow trend book, high-capacity net (192x3) + extreme-fear veto

*Registered 2026-09-02T18:57:27.530608+00:00* · parent **ARCH-0002** · code `64eaabd`

Identical decision path to ARCH-0002 - same modules, same labeller, same universe, same risk layer - with the network's capacity tripled from three 64-channel layers to three 192-channel ones (36k -> 256k parameters).

Why this is a new architecture and not a value change: the 64-channel net was inherited from the first version of this system and never questioned, and P35 proved it was the BINDING CONSTRAINT - every seed improved at 192, the gain was monotone in width, and drawdown FELL. Every refutation in the project ledger was measured through that too-small net, so capacity changes what the whole pipeline can express, not merely a number.

Evidence: P34 (two seeds, exploratory), P35 (four seeds, median +0.4611 vs bar +0.1001), P38 champion build at seed 91002 (lower-middle of the four, committed in advance): research +0.4238 REPRODUCED, sealed 2026 +32.24% at 22.5% drawdown vs incumbent +2.08% at 19.0%. Research 2025 is -1.66%: the all-years-green ideal is not met and is recorded here rather than hidden.

## Structure

- **modules**: ['oracle-nn', 'meta', 'stops', 'regime', 'sizing/money-model', 'crowd']
- **labeller**: zigzag-3pct
- **features**: ['ohlcv-causal', 'trend', 'vol', 'momentum']
- **universe_id**: universe.json:14
- **timeframe**: 15m
- **pipeline**: generate(TCN-192x3)>filter>rank>size>survive

## Diagram

See `diagram.mmd` (mermaid).

## Backtests

Every measurement attached to this architecture is appended to `backtests.jsonl`, newest last.
