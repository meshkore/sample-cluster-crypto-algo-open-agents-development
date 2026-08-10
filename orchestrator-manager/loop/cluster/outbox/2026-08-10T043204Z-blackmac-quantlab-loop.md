## Iteration 29 — REFUTED

**Module:** SIDEWAYS

**Hypothesis:** SIDEWAYS-entry tuning is a dead direction (H-L019 and H-L024 both left the window frozen at 71 all-BEAR trades, and H-L025 confirmed the same for BULL), so the only lever that can serve SIDEWAYS is the detector's missing trending-vs-ranging axis: adding a ranging-override that classifies a bar SIDEWAYS when adx<20 AND neither DI dominates the other by more than 25% will, unlike the three prior bull/bear-axis rewrites, clear the DETECTOR fit gate (score > -0.1126) and route at least one 2026 bar 

**Fit:** score -0.1083954569692536

**Forward 2026:** -7.82% on 71 trades

forward -7.82% on 71 trades, against incumbent -7.82%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `(adx < 20 AND di_plus < di_minus*1.25 AND di_minus < di_plus*1.25)`
- exit_rule: `((high crosses below ema_12 OR sma_5 crosses above close) AND (sma_200 < keltner_mid AND distance_to_sma_200 > -0.0874))`