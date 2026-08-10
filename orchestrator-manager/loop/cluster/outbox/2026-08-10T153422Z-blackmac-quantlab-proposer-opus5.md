## Iteration 64 — proposal

**Module:** BEAR

**Claim:** Replacing BEAR's deep-dip mean-reversion entry with a state-based relative-strength filter -- BUY (seed_rules[0]) any asset trading above its ema_50 while within 8% of its 55-bar high (pct_below_high_55 < 0.08) and carrying positive 20-bar momentum (return_20 > 0), and SELL (seed_rules[1]) when close crosses down through ema_50 or return_20 turns negative -- clears BEAR's evolved fold-fit gate and, because the 2026 forward window is 100% BEAR-routed (H-L058R), produces a forward return above the

**Killed by:** Refuted if (a) the evolved fold-fit score fails BEAR's gate so the forward window never opens; or (b) the forward window opens and the return is <= +1.12%; or (c) fewer than 15 forward trades fire, repeating H-L059's irrelevance failure mode. Any of the three kills it.

The ledger has falsified both BEAR directions it ever tried: deep-dip mean reversion is negative-edge when held (module finding: -0.20% by bar 20; H-L058 cutting its stops -> -13.87%) and the reclaim-event entry fired only 4 trades (H-L059). The incumbent wins forward (+1.12%) purely by staying in cash 92% of the time (H-L058R), not by skill. This is an explicitly NEW mechanism, not a deepening of either dead branch: instead of buying depth (bear_min_depth 0.82), it holds leadership -- assets still above ema_50, within 8% of their 55-bar high, with positive return_20. Because DETECTOR routes all 212 bars of 2026 to BEAR (H-L058R, confirmed at asset scope by H-L060R), whatever BEAR holds is what the forward book holds, so this cleanly tests whether relative strength -- not mean reversion -- is the profitable way to be long while the tape falls. Three joined comparisons, 10 entry nodes, to stay a mechanism rather than a four-fold overfit.

- `(close > ema_50 AND pct_below_high_55 < 0.08 AND return_20 > 0)`
- `(close crosses below ema_50 OR return_20 < 0)`