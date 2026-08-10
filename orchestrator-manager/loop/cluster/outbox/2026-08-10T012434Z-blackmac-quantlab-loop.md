## Iteration 15 — REFUTED

**Module:** BULL

**Hypothesis:** Replacing the BULL entry with a distinct 55-day-high breakout gate confirmed by trend strength (adx > 25) and positive money flow will change the 2026 forward trade count away from the frozen 71 and lift forward return above the incumbent -0.0782.

**Fit:** score -0.004038191415339343

**Forward 2026:** -7.82% on 71 trades

forward -7.82% on 71 trades, against incumbent -7.82%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `((high_200 crosses above low_200 AND cci < 206.005 AND rsi_21 < 58.785) AND (distance_to_sma_200 > 0.3691 AND di_minus < 48.695 AND high crosses below sma_20))`
- exit_rule: `(NOT (supertrend_direction > -0.916) OR rsi_21 > 73.219)`