## Iteration 27 — REFUTED

**Module:** BEAR

**Hypothesis:** Evolving the BEAR module's entry and exit rules over the served columns improves the walk-forward score without breaching the drawdown mandate.

**Fit:** score -0.10496605826798741

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score -0.10496605826798741, best known for BEAR 0.0209); the forward window was not opened.

- entry_rule: `(macd_hist > -0.0048 AND (chaikin_money_flow > -0.412 OR di_minus < 28.666) AND rsi_14 > 45.27)`
- exit_rule: `(pct_below_high_55 > 0.3288 AND (chaikin_money_flow < -0.168 AND bb_lower > ema_21*1.0354 AND mid_20 > low) AND vwap_rolling crosses above supertrend)`