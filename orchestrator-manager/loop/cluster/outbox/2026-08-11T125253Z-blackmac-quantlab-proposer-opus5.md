## Iteration 86 — proposal

**Module:** SIDEWAYS

**Claim:** Gating the SIDEWAYS deviation entry on a weak-trend (range-confirmed) filter -- BUY (seed_rules[0]) only when close pierces below the lower Bollinger band AND adx < 20 (the market is genuinely non-trending), and SELL (seed_rules[1]) when close crosses back up through bb_mid -- raises the SIDEWAYS win rate above the incumbent's 23% and turns the module's contribution positive (> 0% of deposit), because in a true range dips revert whereas the ADX filter rejects the early-breakdown dips that the de

**Killed by:** In the forward run the SIDEWAYS module takes a comparable trade count (>= ~50) yet its win rate stays <= 23% or its deposit contribution stays <= 0%. If it takes near-zero trades the run is inconclusive, not a refutation.

SIDEWAYS is the diagnosed loser: 135 trades, 23% won, -2.81%, with SIGNAL_EXIT (138 trades, -2.09%) doing the damage. That win rate is too low for a mean-reversion module, which points to entries firing on dips that don't revert -- the falling-knife failure BEAR already documented (-0.20% for non-range dips). H-L080 tried deviation + participation (no trades) and H-L085 tried blind evolution (traded, lost); neither used the `trend` primitive to check that the market is actually ranging before buying a dip. adx < 20 is that check: it admits band-piercing dips only when trend strength is weak (a real range, where reversion to bb_mid is the base rate) and rejects them when a directional move is underway. The exit sells back at the mean (cross_up through bb_mid), the reversion target the entry is betting on. Two-term entry keeps the ADX gate as the isolated, testable mechanism rather than an overfit stack. 7-node entry, 3-node exit -- well under the 24-node cap.

- `(close < bb_lower AND adx < 20)`
- `close crosses above bb_mid`