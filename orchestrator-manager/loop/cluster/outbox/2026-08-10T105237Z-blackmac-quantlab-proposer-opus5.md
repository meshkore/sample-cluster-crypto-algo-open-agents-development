## Iteration 56 — proposal

**Module:** BULL

**Claim:** A trend-continuation breakout entry — close crossing above the 20-bar high while price is above the 200-bar EMA and volume exceeds 1.3x its 20-bar average — clears the walk-forward gate and beats the BULL best-known score of 0.0399, and its forward return exceeds the incumbent +1.12%.

**Killed by:** Refuted if the fit fails to clear the gate, if the walk-forward score is <= 0.0399 (no improvement on BULL best-known), or if the forward return is <= the incumbent +0.0112.

The diagnosis rotated to BULL because it was stale and untouched for four iterations. The entire BULL ledger fails in two ways: (1) H-L036/040/041/045 fought the breadth tie-break and routed short into a rising tape (degenerate -7.11%); (2) H-L050 abandoned routing for a pullback entry that bought weakness (bb_percent_b < 0.2) and scored -0.0054, under BULL best 0.0399. Both are exhausted. This tests the untried opposite mechanism: a momentum-continuation breakout that buys strength, not the dip. The three joined comparisons are the three available rule archetypes — trend (close > ema_200), deviation/breakout (cross_up close over high_20), and participation (volume > 1.3x volume_sma_20) — so the seed is a genuine mechanism, not a curve-fit. The exit seed (close crossing below ema_50) closes on trend deterioration rather than a fixed stop, since the ledger shows STOP_LOSS tails were the dominant loss source in the sibling modules. Entry tree is 12 nodes, well under the 24 cap.

- `(close > ema_200 AND close crosses above high_20 AND volume > 1.3*volume_sma_20)`
- `close crosses below ema_50`