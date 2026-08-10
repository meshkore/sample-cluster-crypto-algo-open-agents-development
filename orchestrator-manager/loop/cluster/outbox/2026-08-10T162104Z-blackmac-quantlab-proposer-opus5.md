## Iteration 67 — proposal

**Module:** SIDEWAYS

**Claim:** A mean-reversion long entry -- BUY (seed_rules[0]) when close is below bb_lower while adx is sub-25 (a genuine range, not a trend) and rsi_14 is below 40 (oversold), and SELL (seed_rules[1]) when close crosses back up through bb_mid or rsi_14 exceeds 60 -- clears the SIDEWAYS evolved fold-fit gate (score > best-known 0.0086), because the edge inside a range is fading oversold extremes at the lower band back toward the mean, which is the exact inverse of the bb_upper breakout entry H-L062 measure

**Killed by:** The evolved fold-fit score fails to exceed 0.0086 and the forward window never opens. Because this is the direct inverse of the refuted H-L062 breakout, a failure here does not merely say 'breakouts fail' -- it says the served columns carry NO range-trading edge in either direction, and SIDEWAYS should be abandoned as a source of alpha rather than re-tuned.

H-L062 is the only SIDEWAYS entry in the ledger tail, and it tested the breakout thesis (buy close crossing up through bb_upper on above-average volume while adx<25) and got a fit of -0.0218 -- negative, below the 0.0086 gate. In a market the DETECTOR has classified as sideways, that negative score is the expected result of a breakout: ranges resolve most band-touches into false breaks that revert. The mechanism this proposal tests is the inverse and the textbook range edge -- buy the oversold dip at the lower band (close < bb_lower, rsi_14 < 40) confirmed by a non-trending tape (adx < 25) and sell as price reverts to the mean (cross_up close through bb_mid) or reaches overbought (rsi_14 > 60). It is deviation-family, not participation or trend. It is not a repeat of any ledger entry: H-L062 bought the top of the range, this buys the bottom. Node counts: entry 10, exit 7, both well under the 24 cap; comparisons are close(px) vs bb_lower(col), adx vs constant, rsi_14 vs constant -- no same-bar OHLC-vs-OHLC term.

- `(close < bb_lower AND adx < 25 AND rsi_14 < 40)`
- `(close crosses above bb_mid OR rsi_14 > 60)`