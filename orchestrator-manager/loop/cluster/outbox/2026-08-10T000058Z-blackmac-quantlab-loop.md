## Iteration 9 — REFUTED

**Module:** SIDEWAYS

**Hypothesis:** The SIDEWAYS module has no prior fit in the ledger and is currently mis-specified as a trend/breadth gate (trend_period 292, slope_period 59) rather than a range gate; replacing it with a low-directionality range filter (adx < 20) plus a mean-reversion trigger (close crossing back up through bb_lower while rsi_14 < 45) will produce a nonzero 2026 forward trade count with a walk-forward forward return strictly greater than the incumbent -7.82%.

**Fit:** score -0.16639662440968137

**Forward 2026:** -7.82% on 71 trades

forward -7.82% on 71 trades, against incumbent -7.82%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `close < ema_9`
- exit_rule: `(chaikin_money_flow > 0.363 AND pct_below_high_20 < 0.2072)`