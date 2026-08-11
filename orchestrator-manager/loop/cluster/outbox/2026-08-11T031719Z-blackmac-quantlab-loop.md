## Iteration 81 — INCONCLUSIVE

**Module:** BULL

**Hypothesis:** Evolving the BULL module's entry and exit rules over the served columns improves the walk-forward score without breaching the drawdown mandate.

**Fit:** score 0.005574099658950615

**Forward 2026:** +0.20% on 148 trades

forward +0.20% on 148 trades, against incumbent +0.20%. The BULL module took no trades in 2026, so this run measured the incumbent rather than the hypothesis: nothing about this direction was tested.

- entry_rule: `(close crosses above high_20 AND ema_50 > ema_200 AND adx > 25)`
- exit_rule: `(mid_200 > bb_upper OR high_20 < keltner_mid*0.9645)`