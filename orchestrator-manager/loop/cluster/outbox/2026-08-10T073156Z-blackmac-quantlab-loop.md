## Iteration 42 — REFUTED

**Module:** SIDEWAYS

**Hypothesis:** The SIDEWAYS module has only ever been fed volatility-compression (bb_width, H-L034) and entry-signal tuning (H-L019/024/029/037), which either froze the window or could not displace BEAR on shared bars; giving it a trend-strength-ABSENCE activation gate (adx < 20 with price oscillating inside the Bollinger band, bb_percent_b in [0.2,0.8]) will route a nonzero fraction of the 67 bars to SIDEWAYS, break the 67/67 all-BEAR freeze, and open a forward window whose return departs from the frozen incu

**Fit:** score 0.00455791821910656

**Forward 2026:** -7.11% on 67 trades

forward -7.11% on 67 trades, against incumbent -7.11%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `(distance_to_sma_200 < 0.5007 AND (drawdown_from_high < 0.4645 OR low_55 > close))`
- exit_rule: `((volume > volume_sma_50*2.8 AND return_20 > -0.2262) AND vortex_plus < 0.801)`