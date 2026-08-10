## Iteration 57 — REFUTED

**Module:** SIDEWAYS

**Hypothesis:** A range mean-reversion long entry — price piercing the lower Bollinger band (bb_percent_b < 0.1) while ADX confirms no trend (adx < 20) and RSI is oversold (rsi_14 < 35), exiting when price crosses back up through bb_mid — will clear the SIDEWAYS gate and produce a forward return above the incumbent +0.0112 without breaching the drawdown mandate.

**Fit:** score -0.010132061198496967

**Forward 2026:** +1.12% on 96 trades

forward +1.12% on 96 trades, against incumbent +1.12%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `(ema_26 > ema_21 OR sma_10 > ema_12)`
- exit_rule: `((pct_below_high_20 > 0.4556 AND natr_20 < 0.111) OR (ichimoku_kijun crosses below wma_20 OR bb_upper crosses above high OR close crosses above ichimoku_kijun))`