## Iteration 52 — REFUTED

**Module:** SIDEWAYS

**Hypothesis:** Evolving the SIDEWAYS module's entry and exit rules over the served columns improves the walk-forward score without breaching the drawdown mandate.

**Fit:** score 0.008597713527745299

**Forward 2026:** -7.11% on 67 trades

forward -7.11% on 67 trades, against incumbent -7.11%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `(85.312 > sma_100 AND low < keltner_upper)`
- exit_rule: `((distance_to_sma_50 < -0.3152 AND high > close) OR ((distance_to_sma_50 < -0.3152 AND sma_50 > low) AND sma_50 > low))`