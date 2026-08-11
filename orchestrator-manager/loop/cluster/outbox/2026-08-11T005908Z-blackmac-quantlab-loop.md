## Iteration 78 — REFUTED

**Module:** BEAR

**Hypothesis:** Deploying the H-L078B confirmed mechanism as BEAR's own entry for the first time -- BUY (seed_rules[0]) a deviation that pierces the lower Bollinger band (close < bb_lower) confirmed by heavy participation (volume_ratio_20 > 2.5), and SELL (seed_rules[1]) on mean reversion back above sma_20 or an rsi_2 snapback above 80 -- holds forward drawdown under the 30% mandate and returns forward > the incumbent's +0.20%. This is a deviation+participation trade, not the trend-reclaim direction of H-L071/H

**Fit:** score -0.07668023530948911

**Forward 2026:** -2.45% on 167 trades

forward -2.45% on 167 trades, against incumbent +0.20%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `volume < volume_sma_20*5.6`
- exit_rule: `((down_streak > 7.801 AND rsi_21 < 77.193) AND (ema_200 < low AND supertrend crosses above close) AND return_1 > -0.1038)`