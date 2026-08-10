## Iteration 49 — proposal

**Module:** BEAR

**Claim:** BEAR's net loss is a stop-loss tail (20 STOP_LOSS exits, -37.36%) sitting on top of a 75%-win entry, and those stop-outs are shorts entered into oversold snapback conditions; adding an oversold-exclusion band (short only in a downtrend when rsi_14 is bearish but above the capitulation zone) will cut STOP_LOSS exit count and loss versus the -37.36% baseline and lift forward return above the incumbent -7.11%.

**Killed by:** Refuted if, after clearing the walk-forward gate and opening the forward window, STOP_LOSS exit loss is not materially reduced from -37.36% (or its trade count is not reduced from 20), OR forward return fails to beat the incumbent -7.11%. Also refuted if the fit again collapses to the degenerate floor and the window never opens.

The diagnosis is the pivot: BEAR wins 75% of 83 trades yet loses -5.75% of deposit, and the loss concentrates in 20 STOP_LOSS exits at -37.36%. High win rate + fat-tail losers means entry selection is already sound and the damage is the losing 25% — shorts that get run over by a bounce. H-L047C is the key ledger note: the sixteen identical 'best known for BEAR 0.0209' refusals were a gate artifact (H-L001's three-fold score), so no BEAR forward data existed until H-L048 finally opened the window. Now that it has, the data contradicts the entire prior BEAR direction (H-L038/043/046/048 all tuned entry confirmation). I am abandoning confirmation-strength tuning as the wrong axis. The rule keeps the bearish trend context (close < ema_50) but carves out the capitulation zone with a momentum band: rsi_14 in (35, 50) shorts a still-falling but not-yet-exhausted market, excluding the rsi_14 < 35 oversold bars where a mean-reversion snapback triggers the stop. Ten nodes, three joined comparisons — a mechanism, not a fit.

- `(close < ema_50 AND rsi_14 < 50 AND rsi_14 > 35)`