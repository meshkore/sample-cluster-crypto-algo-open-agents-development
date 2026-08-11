## Iteration 86 — proposal

**Module:** SIDEWAYS

**Claim:** Replacing the incumbent deep-deviation-to-mean rule with a range-gated fade -- BUY (seed_rules[0]) when price sits at the lower Bollinger band (bb_percent_b < 0.05) AND the tape is genuinely non-trending (adx < 20) AND momentum is exhausted (rsi_2 < 15), and SELL (seed_rules[1]) only when price reaches the upper band (bb_percent_b > 0.8) -- lifts the SIDEWAYS win rate above 40% (from 23%) and turns its module contribution positive on the forward window without breaching the drawdown mandate.

**Killed by:** SIDEWAYS forward win rate stays at or below 23%, OR its module return stays negative, OR the adx<20 gate starves it to fewer than ~30 forward trades so the mechanism is untested (as happened to H-L080).

SIDEWAYS lost -2.81% on 135 trades at a 23% win rate. The incumbent (entry_deviation -0.113, exit_deviation +0.0017) buys an 11%-deep dip and sells back to the mean; a tight mean exit that still wins only 23% of the time proves the entries are not reverting -- the 'sideways' tape is catching trend/breakdown days, the same falling-knife failure the ledger keeps refuting (H-REGIME-001, H-L078, H-L083). No prior SIDEWAYS proposal (H-L080 routed deviation+volume; H-L085 evolved raw rules, both fed the losing incumbent) has gated the fade on trend strength. adx<20 is the new mechanism: mean reversion only has an edge when the market is actually flat. Exiting at the upper band (bb_percent_b>0.8) instead of the mean harvests the full range amplitude, and the POLICY stop_loss (0.093) covers ranges that resolve into breakdowns rather than reverting.

- `(bb_percent_b < 0.05 AND adx < 20 AND rsi_2 < 15)`
- `bb_percent_b > 0.8`