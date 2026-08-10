## Iteration 74 — proposal

**Module:** BEAR

**Claim:** Holding BEAR's confirmed entry (close cross_up ema_200 with chaikin_money_flow > 0 and adx > 20) and its confirmed trend exits (close cross_down ema_21 OR supertrend_direction < 0), adding a momentum-exhaustion profit-take -- SELL when rsi_14 crosses DOWN through 70 -- will convert a share of the 101 flat TIME_STOP exits into earlier positive rule exits, lifting BEAR return above the current +0.24% of deposit and reducing the TIME_STOP trade count, without increasing the 20-trade STOP_LOSS count

**Killed by:** Refuted if forward BEAR return <= +0.24% of deposit, OR the TIME_STOP trade count is not materially reduced below 101, OR STOP_LOSS trades rise above 20. Any of these means overbought-rollover harvesting did not convert the flat time-stopped poppers into captured gains.

The diagnosis buckets show the rule-based exits (~27 trades not in STOP_LOSS/TIME_STOP) net roughly +2.42% to carry the module to +0.24% against -2.18% from the two loss buckets: winners already leave via the trend rule, while 101 trades enter on the ema_200 reclaim, pop, chop, and get amputated flat at maximum_holding_days=4. An rsi_14 cross-down-through-70 clause harvests the intra-window peak of the poppers before the cap eats the gain -- it fires only on trades that actually got overbought, so it selectively converts flat time-stops to small wins rather than cutting choppers early. The entry is left untouched: gating it is dead (H-L072 over-gated to 28 trades, -2.14%). This is not a repeat of H-L073, which swapped in the faster TREND exit; this adds an orthogonal PROFIT-TAKE mechanism on top of it. POLICY ADVICE (not this iteration's hypothesis): the real prize is likely maximum_holding_days=4, which lets only 27 of 148 trades reach the profitable rule-exit path while bear_holding=19 sits unused -- relaxing the global cap toward the BEAR-specific holding period should be POLICY's next test.

- `(close crosses above ema_200 AND chaikin_money_flow > 0 AND adx > 20)`
- `(close crosses below ema_21 OR supertrend_direction < 0 OR rsi_14 crosses below 70)`