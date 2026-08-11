## Iteration 87 — proposal

**Module:** SIDEWAYS

**Claim:** The incumbent SIDEWAYS entry (H-L086: BUY close < bb_lower AND adx < 20) starves the module -- only 4 trades in loop-086 -- so its -0.15% is an untested sample, not a verdict on the mechanism. Relaxing the entry from a hard lower-band pierce to a graded near-band deviation -- BUY (seed_rules[0]) when bb_percent_b < 0.2 (price in the bottom fifth of the band, not necessarily beneath it) AND adx < 20 (confirmed non-trending), holding the incumbent SELL (seed_rules[1]) on mean-reversion up through 

**Killed by:** Refuted if SIDEWAYS still takes fewer than ~15 forward trades (starvation not cured), OR if it trades at scale but its module return stays negative -- i.e. the looser band merely admits more losing entries rather than exposing a real ranging edge.

The diagnosis names SIDEWAYS the loser, but the underlying number is 4 trades at 25% won -- statistically empty. H-L080 (deviation+volume) also produced no SIDEWAYS trades; H-L085 (full evolve) blew out to -3.33%; H-L086 (hard bb_lower pierce + adx gate) is the current incumbent yet only fires 4 times because close < bb_lower means bb_percent_b < 0, an event that is rare even in a real range. Since bb_percent_b is a continuous restatement of the same Bollinger deviation, moving the threshold to 0.2 is the minimal, cleanly-attributable loosening: same exit (cross_up bb_mid), same range gate (adx < 20), only the entry strictness changes. This is not a repeat of the ledger -- H-L086 tested the pierce; this tests whether the module is starved rather than broken. The kill condition is designed to catch the failure mode where loosening just buys more knives: if trade count rises but return stays red, the range-reversion thesis for SIDEWAYS is dead and the module should be handed to a different mechanism family (participation/trend) next iteration.

- `(bb_percent_b < 0.2 AND adx < 20)`
- `close crosses above bb_mid`