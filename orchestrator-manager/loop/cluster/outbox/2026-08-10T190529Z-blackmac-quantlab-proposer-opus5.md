## Iteration 72 — proposal

**Module:** BEAR

**Claim:** Replacing BEAR's bare ema_200-reclaim entry with a durable-reclaim gate -- BUY (seed_rules[0]) only when close crosses UP through ema_200 while price is already above ema_50 (the 50-day reclaimed first, not a one-bar spike) AND di_plus > di_minus (buyers directionally dominant), and SELL (seed_rules[1]) when close crosses down through ema_50 or supertrend_direction turns negative -- will suppress the false-reclaim entries that produced the 26 STOP_LOSS exits (-6.35%), raising BEAR's win rate abo

**Killed by:** Refuted if the forward run returns <= -0.39% (at or below incumbent), OR BEAR's win rate stays <= 47%, OR the STOP_LOSS exit drag is not reduced below -6.35% -- any of these means the durability filter removed trades without removing losers and added no edge.

Diagnosis: BEAR's loss is concentrated in 26 STOP_LOSS exits (-6.35%) against near-zero SIGNAL_EXIT drag (-0.43%) at a 47% win rate -- the classic signature of bull-trap reclaims that pop above ema_200 then reverse into the 9.3% stop. The ledger establishes the mechanism to keep: H-L071 (ema_200 reclaim) is CONFIRMED and the current incumbent, while H-L064 (buy strength near highs, -25.26%) and dip-buying are dead. So I do not abandon the reclaim -- I gate its durability. Requiring close > ema_50 demands the medium trend was reclaimed first (a proper bottoming sequence, filtering one-bar spikes), and di_plus > di_minus demands the up-move has directional backing rather than a fade into resistance. No ema_200-slope node exists, so close > ema_50 is the available persistence proxy. Entry drops from 4 loose conditions to 3 mechanistically-linked comparisons; the exit is held at the confirmed H-L071 exit so the test isolates entry quality.

- `(close crosses above ema_200 AND close > ema_50 AND di_plus > di_minus)`
- `(close crosses below ema_50 OR supertrend_direction < 0)`