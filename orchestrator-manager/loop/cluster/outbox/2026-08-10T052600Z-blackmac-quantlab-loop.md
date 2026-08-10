## Iteration 33 — REFUTED

**Module:** BEAR

**Hypothesis:** Gating BEAR entries on a chop-filtered directional downtrend (adx > 25 AND di_minus > di_plus AND supertrend bearish) will clear the walk-forward fit gate (score > 0.0209, the best-known BEAR score) and, on the forward window, cut SIGNAL_EXIT trades below 46 while raising win rate above 27% — because the 46 near-breakeven losers (-0.27% avg) are shorts fired in choppy/rising tape that an ADX trend-strength filter rejects.

**Fit:** score -0.10078365375034581

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score -0.10078365375034581, best known for BEAR 0.0209); the forward window was not opened.

- entry_rule: `((distance_to_sma_200 > -0.2314 AND return_5 < -0.0803) AND vortex_minus > 0.856)`
- exit_rule: `((williams_r > -74.251 AND high crosses above running_high*0.9555) AND close < mid_20*1.0757)`