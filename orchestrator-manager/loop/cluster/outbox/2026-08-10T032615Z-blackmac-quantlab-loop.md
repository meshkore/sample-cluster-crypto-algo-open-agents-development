## Iteration 24 — REFUTED

**Module:** SIDEWAYS

**Hypothesis:** A deliberately maximally-permissive range gate for SIDEWAYS (adx < 20 AND price sitting in the middle 60% of the Bollinger band, 0.2 < bb_percent_b < 0.8) will STILL leave the 2026 forward window frozen at 71 trades, all routed to BEAR — demonstrating that no SIDEWAYS entry rule can move the window because the detector's neutral breadth band is only ~0.003 wide (bull_breadth 0.4161 vs bear_breadth 0.4134) and therefore almost never classifies a bar as sideways.

**Fit:** score -0.110541413789079

**Forward 2026:** -7.82% on 71 trades

forward -7.82% on 71 trades, against incumbent -7.82%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `(sma_100 crosses above high*0.9044 OR volume < volume_sma_20*sma_10)`
- exit_rule: `((high crosses below ema_200 AND money_flow_index > 22.897) AND (NOT (ema_50 crosses above mid_55) AND NOT (ema_50 crosses above mid_55)) AND distance_to_sma_200 < -0.3231)`