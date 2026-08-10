## Iteration 8 — REFUTED

**Module:** BEAR

**Hypothesis:** BEAR's -7.82% is whipsaw: it shorts non-trending chop and bear-rally bounces, so 48 SIGNAL_EXIT trades bleed -12.53% at a 27% win rate. Gating entries on genuine downtrend strength (ADX>25) AND directional dominance (di_minus>di_plus) on top of a long-term-downtrend context (close<ema_200) will raise the 2026 forward win rate above 27% and cut the SIGNAL_EXIT loss below -12.53%, while still taking at least ~15 forward trades.

**Fit:** score -0.10496605826798741

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score -0.10496605826798741, best known for BEAR 0.0209); the forward window was not opened.

- entry_rule: `return_252 < -0.7988`
- exit_rule: `(NOT (cci > -222.869) AND (stoch_k > 51.36 AND distance_to_sma_200 > -0.4229))`