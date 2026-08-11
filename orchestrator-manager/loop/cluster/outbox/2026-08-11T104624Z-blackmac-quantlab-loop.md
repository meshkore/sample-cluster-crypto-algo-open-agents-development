## Iteration 85 — CONFIRMED

**Module:** SIDEWAYS

**Hypothesis:** Evolving the SIDEWAYS module's entry and exit rules over the served columns improves the walk-forward score without breaching the drawdown mandate.

**Fit:** score -0.08544419431030076

**Forward 2026:** -3.33% on 206 trades

forward -3.33% on 206 trades, against incumbent none. The incumbent moves.

- entry_rule: `((volume < volume_sma_50*2.43 AND return_252 < 0.3128) AND (di_minus > 18.078 OR volume < volume_sma_50*2.43))`
- exit_rule: `(NOT (ema_50 < close) OR low < high_200*0.9665)`