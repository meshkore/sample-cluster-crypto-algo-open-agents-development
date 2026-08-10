## Iteration 61 — proposal

**Module:** BULL

**Claim:** A BULL entry that buys oversold pullbacks inside a confirmed uptrend -- close above sma_200 while rsi_14 dips below 35, exiting when rsi_14 crosses up through 60 or close crosses down through sma_200 -- clears the BULL gate (evolved fold fit score > best-known 0.0399), because in bull regimes RSI-30 bounces return +2.26%/20 bars (H-REGIME-001), the edge that trend-continuation buy-strength entries (H-L056, scored 0.002) leave unclaimed.

**Killed by:** Refuted if the evolved fit score does not exceed 0.0399, or if -- having cleared it -- the buy-the-dip rule does not beat the incumbent BULL evolved rule on fold return. A 2026 forward return equal to the incumbent +1.12% is NOT confirmation and NOT refutation: all 212 forward bars classify BEAR (H-L058R, H-L060), so BULL does not fire there and the forward window cannot exercise this rule.

H-L056 tested the buy-strength mechanism for BULL and failed the gate (0.002 vs 0.0399); this proposes the opposite mechanism -- mean reversion conditioned on trend, grounded in H-REGIME-001's +2.26% bull-regime bounce -- so it is not a repeat. The gate stage is the only place BULL can currently be measured, because H-L058R and H-L060 establish that 2026 is a single market-wide BEAR regime where BULL never trades; that is why 16 prior bull/sideways hypotheses (H-L057C) were 'refuted' by a window that never exercised them. ADVICE FOR DETECTOR, not part of this hypothesis: until regime_scope or the detector thresholds admit some non-BEAR bars into the forward window, no BULL rule -- including this one -- can be forward-validated, and H-L060 showed the naive market->asset scope switch made it worse (-19.35%). The productive next move after this fold-level test is a DETECTOR iteration that recovers 2026 bull/sideways classification without the H-L060 blowup, so a validated BULL rule finally has bars to trade.

- `(close > sma_200 AND rsi_14 < 35)`
- `(rsi_14 crosses above 60 OR close crosses below sma_200)`