## Iteration 13 — REFUTED

**Module:** BEAR

**Hypothesis:** Swapping the BEAR branch rule from `participation` (symmetric close>sma_50 AND close>sma_200, always-on, no momentum gate) to `trend` (sma_50>sma_200 AND close>sma_50 AND rsi_14>55) raises the BEAR win rate above 27% and shrinks the SIGNAL_EXIT aggregate loss above -12.53%, lifting forward BEAR return above -7.82% and clearing the 0.0209 BEAR walk-forward bar.

**Fit:** score -0.10496605826798741

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score -0.10496605826798741, best known for BEAR 0.0209); the forward window was not opened.

- entry_rule: `(money_flow_index > 58.082 AND (rsi_7 < 86.104 AND high < ichimoku_tenkan))`
- exit_rule: `((volume < volume_sma_20*1.8 AND ema_9 crosses above ema_50*1.0237) AND rsi_7 > 98.388 AND sma_100 crosses above ema_200)`