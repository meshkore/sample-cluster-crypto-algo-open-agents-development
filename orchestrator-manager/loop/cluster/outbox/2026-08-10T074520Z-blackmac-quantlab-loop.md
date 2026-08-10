## Iteration 43 — REFUTED

**Module:** BEAR

**Hypothesis:** Gating BEAR entries on distribution rather than trend/oscillator confirmation — net selling flow (chaikin_money_flow < 0) with elevated participation (volume > volume_sma_20) and price below its volume-weighted fair value (close < vwap_rolling) — will clear the walk-forward fit gate (score > 0.0209, best-known BEAR) and, on the forward window, cut SIGNAL_EXIT trades below 46 and raise BEAR win rate above 27%, because it removes shorts opened into bought-up pullbacks (positive-flow, above-VWAP) t

**Fit:** score -0.10078365375034581

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score -0.10078365375034581, best known for BEAR 0.0209); the forward window was not opened.

- entry_rule: `((sma_200 > wma_20 OR high crosses below close) AND williams_r > -62.563)`
- exit_rule: `sma_50 crosses below high_200`