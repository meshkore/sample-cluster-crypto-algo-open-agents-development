## Iteration 73 — proposal

**Module:** BEAR

**Claim:** Holding BEAR's incumbent (H-L071) entry unchanged -- BUY (seed_rules[0]) on close crossing UP through ema_200 with chaikin_money_flow > 0 and adx > 20 -- and replacing ONLY the exit (seed_rules[1]) with a faster one -- SELL when close crosses DOWN through ema_21, OR supertrend_direction is negative, OR macd_hist crosses DOWN through zero -- will cut the share of trades that exit via the 9.3% hard STOP_LOSS from the diagnosed 15/28 (54%) to under one third and raise forward return above the incum

**Killed by:** Refuted if STOP_LOSS remains the dominant exit (>= 50% of trades) OR forward return does not exceed -0.39%. That would mean the loss is entry-driven (ema_200 reclaims are false breakouts that fail regardless of exit speed), not exit-driven, and the reclaim-entry family should then be reconsidered rather than re-tuned.

The diagnosis attributes nearly the entire -2.14% loss to STOP_LOSS (15 of 28 trades, -2.35%), while the REGIME_GATE exit lost only -0.23% -- the trades are being carried to the wide 9.3% hard stop rather than cut by rule. H-L072 already REFUTED the entry-stricter lever (it cut trades to 28 and worsened return to -2.14% vs incumbent -0.39%), so I keep H-L071's confirmed entry untouched and attack the untried lever: exit speed. H-L071's exit fires only on the slow ema_50 cross / supertrend flip; swapping to ema_21 cross-down plus a macd_hist zero-cross gets the position out of a failing reclaim well before the 9.3% stop. This is a distinct hypothesis from every BEAR entry in the ledger (H-REGIME-001 dip-buy, H-L071 base reclaim, H-L072 durable reclaim) -- it changes only seed_rules[1].

- `(close crosses above ema_200 AND chaikin_money_flow > 0 AND adx > 20)`
- `(close crosses below ema_21 OR supertrend_direction < 0 OR macd_hist crosses below 0)`