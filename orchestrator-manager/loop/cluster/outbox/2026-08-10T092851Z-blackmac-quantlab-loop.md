## Iteration 49 — REFUTED

**Module:** BEAR

**Hypothesis:** BEAR's net loss is a stop-loss tail (20 STOP_LOSS exits, -37.36%) sitting on top of a 75%-win entry, and those stop-outs are shorts entered into oversold snapback conditions; adding an oversold-exclusion band (short only in a downtrend when rsi_14 is bearish but above the capitulation zone) will cut STOP_LOSS exit count and loss versus the -37.36% baseline and lift forward return above the incumbent -7.11%.

**Fit:** score -0.10078365375034581

**Forward 2026:** +0.00% on 0 trades

forward +0.00% on 0 trades, against incumbent -7.11%. No trades: the configuration stood aside rather than performed, so it is not an improvement.

- entry_rule: `((return_5 > -0.0797 OR rsi_7 > 54.226) AND (high_55 > ema_21 AND high < bb_lower*0.9587 AND return_5 > 0.0181) AND low < sma_100)`
- exit_rule: `volume < volume_sma_50*3.69`