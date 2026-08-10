## Iteration 54 — REFUTED

**Module:** BEAR

**Hypothesis:** BEAR's residual 12.92% drawdown is almost entirely the 10 STOP_LOSS shorts (-12.13%); these are entries taken mid-range into snapback bounces. Replacing the entry trigger with a fresh-low breakdown confirmed by volume participation (close breaks below the 20-bar low while volume runs >1.5x its 20-bar average and macd_hist is negative) will cut the stop tail to fewer than 10 stops and less than -12.13%, lowering total drawdown below 12.92% while holding BEAR's contribution at or above +5.52% and 

**Fit:** score -0.10078365375034581

**Forward 2026:** +0.00% on 0 trades

forward +0.00% on 0 trades, against incumbent +1.12%. No trades: the configuration stood aside rather than performed, so it is not an improvement.

- entry_rule: `(close < low_20 AND volume > volume_sma_20*1.5 AND macd_hist < 0)`
- exit_rule: `(high_200 crosses above low AND (volume < volume_sma_50*5.65 AND pct_below_high_55 < 0.5726))`