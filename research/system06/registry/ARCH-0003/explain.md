# ARCH-0003 — Wide deep-history universe (24 assets)

*Registered 2026-08-30T16:31:38.071045+00:00* · parent **ARCH-0002** · code `c6f56f3`

The operator's hypothesis: watch more markets, take only the highest-certainty opportunities. Universe widened to 24 symbols screened for 4.4 years of history and $5M turnover.

REJECTED. Three seeds trained on all research years read the sealed 2026 at +35.1%, -21.1% and -43.5% - median -21.1%. Research selection had already refused it (median score +0.0037 against a +0.0972 bar, 2018 negative on every seed). The single good draw is exactly what the median-of-reseeds rule exists to catch. The second finding matters as much: the forward-year seed spread is 78pp, far wider than the narrow book's - dilution shows up as variance, not only as a lower mean.

## Structure

- **modules**: ['oracle-nn', 'meta', 'stops', 'regime', 'sizing/money-model', 'crowd']
- **labeller**: zigzag-1pct
- **features**: ['ohlcv-causal', 'trend', 'vol', 'momentum']
- **universe_id**: universe_deep.json:24
- **timeframe**: 15m
- **pipeline**: generate>filter>rank>size>survive

## Diagram

See `diagram.mmd` (mermaid).

## Backtests

Every measurement attached to this architecture is appended to `backtests.jsonl`, newest last.
