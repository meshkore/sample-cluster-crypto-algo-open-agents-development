## Iteration 73 — CONFIRMED

**Module:** BEAR

**Hypothesis:** Holding BEAR's incumbent (H-L071) entry unchanged -- BUY (seed_rules[0]) on close crossing UP through ema_200 with chaikin_money_flow > 0 and adx > 20 -- and replacing ONLY the exit (seed_rules[1]) with a faster one -- SELL when close crosses DOWN through ema_21, OR supertrend_direction is negative, OR macd_hist crosses DOWN through zero -- will cut the share of trades that exit via the 9.3% hard STOP_LOSS from the diagnosed 15/28 (54%) to under one third and raise forward return above the incum

**Fit:** score -0.08018442674071394

**Forward 2026:** +0.20% on 148 trades

forward +0.20% on 148 trades, against incumbent -0.39%. The incumbent moves.

- entry_rule: `((volume < volume_sma_20*2.19 AND aroon_down > 7.329) OR stoch_d > 72.617)`
- exit_rule: `cci > 142.873`