## Iteration 50 — proposal

**Module:** BULL

**Claim:** Because every prior BULL attempt (H-L036/040/041/045) tried to WIN the breadth tie-break against BEAR and all returned the degenerate -7.11% or failed the gate, I abandon the routing frame. A pullback-in-uptrend entry — close above sma_200 (trend up) AND bb_percent_b below 0.2 (stretched to the lower band) AND stoch_k crossing up over stoch_d (momentum turning) — fires only on bars where BEAR's downtrend conditions are false by construction, so it needs no tie-break; I expect it to clear the wal

**Killed by:** Refuted if the fit collapses to the degenerate floor and no forward window opens, OR the window opens but produces zero long entries (still 100% short), OR forward return is <= the incumbent -7.11%.

The ledger shows BULL has only ever been fed routing tie-breaks on the overlapping breadth band (0.423/0.392); H-L045 confirms these return an identical -7.11% because they never change which bars fire, while H-L041/046 trend-stack and supertrend gates failed the fit gate outright. Rather than deepen a dead direction, I switch the mechanism to mean-reversion-within-uptrend: the close>sma_200 gate makes the rule disjoint from every BEAR condition (which requires a downtrend), so it wins bars by not contesting them. bb_percent_b<0.2 is the deviation trigger (buy the stretch to the lower band), stoch_k cross_up stoch_d is the momentum-turn confirmation. 10 nodes, three joined comparisons — a mechanism, not a fold-fitted mesh.

- `(close > sma_200 AND bb_percent_b < 0.2 AND stoch_k crosses above stoch_d)`