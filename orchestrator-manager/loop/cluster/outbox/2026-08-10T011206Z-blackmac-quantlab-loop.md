## Iteration 14 — REFUTED

**Module:** SIDEWAYS

**Hypothesis:** Evolving the SIDEWAYS module's entry and exit rules over the served columns improves the walk-forward score without breaching the drawdown mandate.

**Fit:** score -0.11483453853924738

**Forward 2026:** -7.82% on 71 trades

forward -7.82% on 71 trades, against incumbent -7.82%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `(keltner_mid crosses above sma_5 OR (close crosses below low_55*0.9468 AND close crosses above low AND williams_r < -6.195))`
- exit_rule: `rsi_14 < 1.3`