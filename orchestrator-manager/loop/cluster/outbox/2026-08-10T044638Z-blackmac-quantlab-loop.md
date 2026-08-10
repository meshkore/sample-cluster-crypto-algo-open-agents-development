## Iteration 30 — REFUTED

**Module:** BULL

**Hypothesis:** BULL entry tuning is abandoned as causally inert (H-L025 proved any BULL rule yields the same frozen 71-trade all-BEAR forward window at -7.82%); replacing the detector's tied same-bar breadth axis (bull 0.416 ≈ bear 0.413) with a directional-movement axis that is mutually exclusive by construction — +DI vs -DI gated by ADX>20 — will clear the fit gate (walk-forward score > -0.1126, best-known DETECTOR) AND open a 2026 forward window whose trade count differs from the frozen 71 by routing at lea

**Fit:** score -0.004038191415339343

**Forward 2026:** -7.82% on 71 trades

forward -7.82% on 71 trades, against incumbent -7.82%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `(low_200 > high AND ((volume > volume_sma_20*2.5 OR rsi_21 > 75.215) AND (volume < volume_sma_50*3.54 OR natr_20 < 0.13)))`
- exit_rule: `keltner_upper < 33.846`