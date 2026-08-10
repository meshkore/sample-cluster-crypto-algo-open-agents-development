## Iteration 75 — REFUTED

**Module:** BEAR

**Hypothesis:** Evolving the BEAR module's entry and exit rules over the served columns improves the walk-forward score without breaching the drawdown mandate.

**Fit:** score -0.08309276834264409

**Forward 2026:** -1.70% on 369 trades

forward -1.70% on 369 trades, against incumbent +0.20%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `(return_5 < 0.28 OR (aroon_down < 12.725 AND aroon_down < 12.725))`
- exit_rule: `volume < volume_sma_20*1.02`