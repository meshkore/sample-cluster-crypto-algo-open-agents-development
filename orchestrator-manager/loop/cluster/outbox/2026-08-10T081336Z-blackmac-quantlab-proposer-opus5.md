## Iteration 46 — proposal

**Module:** DETECTOR

**Claim:** Abandoning the four failed bull-side tie-break attempts (H-L036/040/041/045) and instead gating BEAR activation on a genuine trend-regime flag — supertrend_direction bearish AND di_minus>di_plus AND adx>25 — while permitting a BULL state disjoint by construction on supertrend_direction bullish AND di_plus>di_minus, will break the 67/67 all-BEAR freeze: BEAR-routed trade share falls below 90% and forward return rises above the incumbent -7.11%.

**Killed by:** Refuted if BEAR still captures >=90% of trades (freeze intact), OR forward return <= -7.11%, OR the fit fails to clear the DETECTOR gate (score <= -0.0732, the best known for DETECTOR).

The ledger shows every recent DETECTOR/routing hypothesis (H-L036, H-L040, H-L041, H-L045) attacking the freeze from the BULL side — adding a discriminant to let BULL win the shared breadth band (bull 0.423 / bear 0.392). All four either left routing at 67/67 with forward unchanged at -7.11%, or failed the fit gate. That direction is exhausted and should be abandoned, not deepened. The mechanism the ledger keeps missing: `breadth < 0.392` is a deviation signal, so BEAR fires on pullbacks inside a rising tape and wins every shared bar because nothing forbids it. So constrain BEAR from the supply side with a trend flag (supertrend bearish + di_minus>di_plus + adx>25) that structurally cannot be true while the trend is up, and pair it with a BULL permit that is disjoint by the sign of supertrend_direction — a column that has never appeared in a DETECTOR seed. The two seeds cannot both be true on the same bar, which is the property every prior bull-side attempt failed to guarantee. Each seed is 10 and 7 nodes, well under the 24-node cap, and expresses the 'trend' rule type rather than another deviation/participation term.

- `(supertrend_direction < 0 AND di_minus > di_plus AND adx > 25)`
- `(supertrend_direction > 0 AND di_plus > di_minus)`