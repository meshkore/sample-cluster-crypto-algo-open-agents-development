## Iteration 66 — proposal

**Module:** BULL

**Claim:** A BULL momentum-continuation entry -- BUY (seed_rules[0]) a 20-bar-high breakout (close crossing UP through high_20) confirmed by trend structure (ema_50 > ema_200) and trend strength (adx > 25), and SELL (seed_rules[1]) when close crosses down through ema_21 or supertrend flips bearish (supertrend_direction < 0) -- clears the BULL evolved fold-fit gate (score > best-known 0.0399) and opens a forward window, because buying confirmed-uptrend breakouts is a mechanism distinct from H-L061's mean-re

**Killed by:** The evolved fold-fit score does not exceed 0.0399, so no forward window opens (the same gate failure that refuted H-L061 at 0.002).

The diagnosis is stale (12 iterations with no forward window) and BULL is the rotation target with only one prior attempt on record. That attempt, H-L061, tried to monetize the documented bull-regime pullback edge (RSI-30 bounces +2.26% over 20 bars) via rsi_14 < 35 above sma_200 and scored only 0.002 against the 0.0399 gate -- so the mean-reversion framing, however real forward, does not fit the folds. Rather than deepen a refuted direction, this proposes the orthogonal bull mechanism: trend-continuation. New-high breakouts (cross_up close/high_20) filtered by structural alignment (ema_50 > ema_200) and non-trivial trend strength (adx > 25) capture the persistence that is most consistently present across bull-labeled training folds, which is what the fold-fit gate actually rewards. The exit is deliberately tight (ema_21 loss or supertrend flip) so the rule sheds inventory the moment momentum stalls -- BULL's job is to hold winners while the market rises, not to average into fading trends. Node counts: entry 10, exit 7, both well under the 24 cap, and no same-bar tautology (close is compared to the rolling 20-bar high, an aggregate, not this bar's own high).

- `(close crosses above high_20 AND ema_50 > ema_200 AND adx > 25)`
- `(close crosses below ema_21 OR supertrend_direction < 0)`