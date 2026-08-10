## Iteration 38 — REFUTED

**Module:** BEAR

**Hypothesis:** The BEAR bleed comes from shorting pullback LOWS inside a rising tape (H-L032's 46 SIGNAL_EXIT losers, -12.55%), not from too few confirmed downtrends. Entering shorts only from a position of upside extension that is just beginning to roll over — RSI still elevated, Williams %R in its upper half, close crossing back below the 21 EMA — will clear the BEAR fit gate (score > 0.0209) and, on the forward window, cut SIGNAL_EXIT losers below 46 and lift forward return above the incumbent -7.11%.

**Fit:** score -0.10078365375034581

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score -0.10078365375034581, best known for BEAR 0.0209); the forward window was not opened.

- entry_rule: `(rsi_14 > 55 AND williams_r > -50 AND close crosses below ema_21)`
- exit_rule: `((volume < volume_sma_50*4.56 AND distance_to_sma_50 < -0.2768) AND (high > high_20 AND bb_percent_b < 0.715) AND close crosses below ema_50)`