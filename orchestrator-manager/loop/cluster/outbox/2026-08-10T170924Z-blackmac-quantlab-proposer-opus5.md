## Iteration 69 — proposal

**Module:** BEAR

**Claim:** Replacing BEAR's evolved entry with an accumulation-decoupling filter -- BUY (seed_rules[0]) any asset under net accumulation (chaikin_money_flow > 0) that is trading above its own ema_50 with directional dominance (di_plus > di_minus), and SELL (seed_rules[1]) when close crosses down through ema_21 or supertrend_direction flips down -- clears the BEAR fold-fit gate and returns a forward result above the incumbent +1.12%, because in a falling market the only long worth holding is one whose volum

**Killed by:** The fit fails to clear the BEAR gate, OR the forward window returns at or below the incumbent +1.12% -- and especially if it repeats the double-digit losses of H-L064. Either outcome refutes flow-based decoupling and, taken with H-L064's price-strength failure and the RSI-bounce finding, closes 'find something to buy in a bear regime' as a direction: BEAR's best contribution is then to hold near-cash, not to select longs.

The BEAR ledger has refuted every PRICE-based long style: dip-buying (RSI-30 bounces -0.20% in bear, H-REGIME-001 -8.46%) and price relative-strength (H-L064: above ema_50, near 55-bar high, positive return_20 -> -25.26% on 116 trades). H-L065's detector re-slice also lost -17.47%. What none of these tested is a FLOW-based decoupling signal. This entry deliberately avoids price-momentum terms (no return_20/pct_below_high, which H-L064 already burned) and instead requires net accumulation via chaikin_money_flow > 0 -- money entering the name while the broad market falls -- gated by the asset's own medium trend (close > ema_50) and directional dominance (di_plus > di_minus). The exit is tight and trend-following (ema_21 breakdown or supertrend flip) so a failed decoupling is cut fast rather than held through the decline, which is what turned H-L064 and H-L065 into large losses. This is a new mechanism, not a deepening of a dead one; if it fails too, the honest conclusion is that BEAR should stop trying to select longs and abstain.

- `(chaikin_money_flow > 0 AND close > ema_50 AND di_plus > di_minus)`
- `(close crosses below ema_21 OR supertrend_direction crosses below 0)`