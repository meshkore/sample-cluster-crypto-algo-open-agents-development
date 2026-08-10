## Iteration 72 — REFUTED

**Module:** BEAR

**Hypothesis:** Replacing BEAR's bare ema_200-reclaim entry with a durable-reclaim gate -- BUY (seed_rules[0]) only when close crosses UP through ema_200 while price is already above ema_50 (the 50-day reclaimed first, not a one-bar spike) AND di_plus > di_minus (buyers directionally dominant), and SELL (seed_rules[1]) when close crosses down through ema_50 or supertrend_direction turns negative -- will suppress the false-reclaim entries that produced the 26 STOP_LOSS exits (-6.35%), raising BEAR's win rate abo

**Fit:** score -0.08298662906755802

**Forward 2026:** -2.14% on 28 trades

forward -2.14% on 28 trades, against incumbent -0.39%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `bb_upper crosses below low`
- exit_rule: `94.24 crosses above sma_100`