## Iteration 86 — CONFIRMED

**Module:** SIDEWAYS

**Hypothesis:** Gating the SIDEWAYS deviation entry on a weak-trend (range-confirmed) filter -- BUY (seed_rules[0]) only when close pierces below the lower Bollinger band AND adx < 20 (the market is genuinely non-trending), and SELL (seed_rules[1]) when close crosses back up through bb_mid -- raises the SIDEWAYS win rate above the incumbent's 23% and turns the module's contribution positive (> 0% of deposit), because in a true range dips revert whereas the ADX filter rejects the early-breakdown dips that the de

**Fit:** score -0.07541136053787961

**Forward 2026:** +0.27% on 143 trades

forward +0.27% on 143 trades, against incumbent -3.33%. The incumbent moves.

- entry_rule: `(NOT ((high crosses above keltner_upper*1.0375 AND supertrend < bb_mid)) AND (sma_200 crosses above low AND keltner_mid crosses above low))`
- exit_rule: `((volume > volume_sma_20*2.77 OR di_plus < 2.119) OR vortex_minus > 1.003)`