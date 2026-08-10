## Iteration 47 — REFUTED

**Module:** SIDEWAYS

**Hypothesis:** Evolving the SIDEWAYS module's entry and exit rules over the served columns improves the walk-forward score without breaching the drawdown mandate.

**Fit:** score -0.10543068080098805

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score -0.10543068080098805, best known for SIDEWAYS 0.0046); the forward window was not opened.

- entry_rule: `((return_60 < 0.8996 OR ema_21 < sma_50) AND sma_100 > high)`
- exit_rule: `(high < bb_upper AND (aroon_up < 90.829 AND chaikin_money_flow < -0.18 AND high < bb_upper))`