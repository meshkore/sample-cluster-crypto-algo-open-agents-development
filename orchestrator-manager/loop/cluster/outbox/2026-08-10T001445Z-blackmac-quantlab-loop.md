## Iteration 10 — REFUTED

**Module:** BULL

**Hypothesis:** The incumbent's -7.82% is a short-side loss produced by a bear/DETECTOR stack that has monopolized the last several iterations while BULL sat untouched; a minimal three-condition BULL long gate — price above the 200-EMA (long-term uptrend), di_plus dominant over di_minus (directional up), and positive Chaikin money flow (accumulation) — will open a nonzero long-trade count in the 2026 forward window and lift forward return above -7.82%.

**Fit:** score -0.004038191415339343

**Forward 2026:** -7.82% on 71 trades

forward -7.82% on 71 trades, against incumbent -7.82%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `((pct_below_high_200 > 0.6717 AND bb_mid crosses above sma_5*0.9699) AND (volume > volume_sma_20*4.36 AND ichimoku_kijun crosses above mid_200))`
- exit_rule: `((low < high AND return_1 < -0.1294) OR (sma_20 < high_200 OR natr_14 < 0.167) OR pct_below_high_200 < 0.1217)`