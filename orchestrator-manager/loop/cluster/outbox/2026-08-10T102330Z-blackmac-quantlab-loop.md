## Iteration 53 — CONFIRMED

**Module:** BEAR

**Hypothesis:** Evolving the BEAR module's entry and exit rules over the served columns improves the walk-forward score without breaching the drawdown mandate.

**Fit:** score -0.10078365375034581

**Forward 2026:** +1.12% on 96 trades

forward +1.12% on 96 trades, against incumbent -7.11%. The incumbent moves.

- entry_rule: `stoch_d < 59.156`
- exit_rule: `((vortex_plus > 1.098 OR bb_upper crosses below keltner_mid*0.9217) AND high > ema_12)`