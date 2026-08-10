## Iteration 35 — REFUTED

**Module:** BULL

**Hypothesis:** The BULL module cannot be served by tuning BULL entries — H-L025 and H-L030 proved any BULL rule yields the same frozen all-BEAR window because the detector never emits a bull state. The one distinguishing fact is that every refuted detector-axis attempt (H-L026 deviation, H-L028 static ema_50/ema_200/close-vs-sma_200, H-L030 static di_plus/di_minus) compared same-bar snapshots that are numerically tied (bull_breadth 0.416 ≈ bear_breadth 0.413) and therefore can never score bull. Replacing that 

**Fit:** score -0.029583514908927355

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score -0.029583514908927355, best known for BULL 0.0090); the forward window was not opened.

- entry_rule: `((volume < volume_sma_50*5.56 AND close crosses above sma_50) AND (macd_hist > -0.0235 AND bb_upper crosses below sma_5 AND return_252 < 0.9272) AND di_minus < 17.459)`
- exit_rule: `aroon_up < 40.722`