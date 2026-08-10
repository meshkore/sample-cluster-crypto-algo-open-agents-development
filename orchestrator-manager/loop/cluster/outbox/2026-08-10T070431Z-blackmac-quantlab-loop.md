## Iteration 40 — REFUTED

**Module:** BULL

**Hypothesis:** BULL entry-tuning is abandoned as causally inert (H-L025/030/035); the only lever that serves BULL is a detector discriminant, and since H-L036 proved routing is breakable (67->27 trades), giving the detector a multi-horizon return-momentum axis disjoint-by-construction from the bear structure -- close>sma_200 AND ema_50>ema_200 AND return_60>0 -- will open a forward window that routes a nonzero fraction of trades to BULL and beats the incumbent -7.11%.

**Fit:** score 0.00010669845327093697

**Forward 2026:** -7.11% on 67 trades

forward -7.11% on 67 trades, against incumbent -7.11%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `((distance_to_sma_50 > -0.479 AND distance_to_sma_200 > 0.8774) AND low crosses below vwap_rolling)`
- exit_rule: `((macd_hist < 58.302 AND return_60 > -0.1076) OR (aroon_up < 74.7 AND macd_hist < -0.0464) OR bb_width > 0.4558)`