## Iteration 64 — REFUTED

**Module:** BEAR

**Hypothesis:** Replacing BEAR's deep-dip mean-reversion entry with a state-based relative-strength filter -- BUY (seed_rules[0]) any asset trading above its ema_50 while within 8% of its 55-bar high (pct_below_high_55 < 0.08) and carrying positive 20-bar momentum (return_20 > 0), and SELL (seed_rules[1]) when close crosses down through ema_50 or return_20 turns negative -- clears BEAR's evolved fold-fit gate and, because the 2026 forward window is 100% BEAR-routed (H-L058R), produces a forward return above the

**Fit:** score -0.10078365375034581

**Forward 2026:** -25.26% on 116 trades

forward -25.26% on 116 trades, against incumbent +1.12%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `(close > ema_50 AND pct_below_high_55 < 0.08 AND return_20 > 0)`
- exit_rule: `(NOT ((vwap_rolling crosses above sma_20 AND ema_12 > ema_26)) AND (ema_50 > ichimoku_tenkan AND rsi_21 < 92.791 AND aroon_up > 82.761))`