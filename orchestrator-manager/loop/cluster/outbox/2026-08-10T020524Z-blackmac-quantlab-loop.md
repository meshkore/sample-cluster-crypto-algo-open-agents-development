## Iteration 18 — REFUTED

**Module:** BEAR

**Hypothesis:** The 48 SIGNAL_EXIT trades that bleed -12.53% are bear-rally bounces: BEAR shorts into oversold exhaustion and gets mean-reverted out at a small loss 48 times. Gating shorts to bearish-but-not-oversold conditions (close<ema_50 AND di_minus>di_plus AND 35<rsi_14<55) will cut the SIGNAL_EXIT count below 48 and lift forward return above the incumbent -0.0782 by refusing to enter shorts that are already stretched to the downside.

**Fit:** score -0.10496605826798741

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score -0.10496605826798741, best known for BEAR 0.0209); the forward window was not opened.

- entry_rule: `chaikin_money_flow > -0.167`
- exit_rule: `(ema_12 crosses above sma_200*1.0717 AND (natr_14 > 0.054 AND vortex_minus < 0.786))`