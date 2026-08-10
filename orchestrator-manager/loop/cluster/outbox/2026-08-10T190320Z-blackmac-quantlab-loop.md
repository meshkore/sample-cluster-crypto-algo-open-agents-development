## Iteration 71 — CONFIRMED

**Module:** BEAR

**Hypothesis:** Replacing BEAR's evolved dip-entry with a long-term-reclaim gate -- BUY (seed_rules[0]) only when close crosses UP through ema_200 with chaikin_money_flow > 0 and adx > 20, and SELL (seed_rules[1]) when close crosses down through ema_50 or supertrend_direction turns negative -- will cut BEAR's forward trade count from 130 to under ~40 and raise forward return above the incumbent's -1.21%, by refusing to participate in a negative-edge regime except on a confirmed structural trend reclaim.

**Fit:** score -0.06827403069922863

**Forward 2026:** -0.39% on 163 trades

forward -0.39% on 163 trades, against incumbent -1.21%. The incumbent moves.

- entry_rule: `((natr_14 < 0.042 OR chaikin_money_flow < 0.19) OR distance_to_sma_50 > -0.3172)`
- exit_rule: `vortex_plus < 0.808`