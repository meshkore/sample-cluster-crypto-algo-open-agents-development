## Iteration 59 — REFUTED

**Module:** BEAR

**Hypothesis:** Replacing BEAR's evolved mean-reversion dip-buy entry with a confirmed trend-reclaim entry — close crossing UP through ema_21 while di_plus leads di_minus and volume exceeds its 20-bar average, exiting when close crosses back below ema_21 or di_minus retakes di_plus — yields a forward return above the incumbent +1.12% with residual drawdown below 12.92%, because reclaim entries buy nascent bear-market rallies that have momentum and participation rather than falling-knife dips that decay to -0.20

**Fit:** score -0.10078365375034581

**Forward 2026:** -1.63% on 4 trades

forward -1.63% on 4 trades, against incumbent +1.12%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `(close crosses above ema_21 AND di_plus > di_minus AND volume > volume_sma_20)`
- exit_rule: `vortex_minus > 1.427`