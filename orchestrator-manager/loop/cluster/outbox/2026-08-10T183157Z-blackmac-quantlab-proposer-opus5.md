## Iteration 71 — proposal

**Module:** BEAR

**Claim:** Replacing BEAR's evolved dip-entry with a long-term-reclaim gate -- BUY (seed_rules[0]) only when close crosses UP through ema_200 with chaikin_money_flow > 0 and adx > 20, and SELL (seed_rules[1]) when close crosses down through ema_50 or supertrend_direction turns negative -- will cut BEAR's forward trade count from 130 to under ~40 and raise forward return above the incumbent's -1.21%, by refusing to participate in a negative-edge regime except on a confirmed structural trend reclaim.

**Killed by:** Refuted if BEAR still opens 50+ forward trades (the ema_200 reclaim is not actually rare in the bear regime) OR if forward return stays at or below the incumbent -1.21%. Either outcome means selectivity does not rescue a negative-edge module and the whole 'hold something long while the market falls' premise should be retired in favor of BEAR holding nothing.

Both prior BEAR directions are dead in the ledger: deep-dip mean reversion (H-REGIME-001, -8.46%; the -0.20% bear RSI-30 finding) and relative-strength/momentum continuation (H-L064, -25.26%). No long entry has shown positive expectancy in this regime, so I abandon the search for a better dip and instead test selectivity: the incumbent still loses -1.19% of deposit across 130 trades with 26 stop-outs (-2.54%), pure participation bleed. An ema_200 reclaim is the one confirmation untried and is structurally distinct from H-L064's ema_50/near-high tactical buy -- it should fire on only a handful of genuine regime-turn bars, so BEAR nearly stops trading a negative-edge regime and the few entries it keeps are the real bull-like turns (+2.26%). cmf>0 and adx>20 reject wick-throughs; the fast ema_50/supertrend exit caps damage when a reclaim fails. Falsified cleanly if the gate is not actually rare or does not beat -1.21%.

- `(close crosses above ema_200 AND chaikin_money_flow > 0 AND adx > 20)`
- `(close crosses below ema_50 OR supertrend_direction < 0)`