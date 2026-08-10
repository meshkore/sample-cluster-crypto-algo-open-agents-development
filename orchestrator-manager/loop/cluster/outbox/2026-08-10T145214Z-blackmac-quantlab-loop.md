## Iteration 61 — REFUTED

**Module:** BULL

**Hypothesis:** A BULL entry that buys oversold pullbacks inside a confirmed uptrend -- close above sma_200 while rsi_14 dips below 35, exiting when rsi_14 crosses up through 60 or close crosses down through sma_200 -- clears the BULL gate (evolved fold fit score > best-known 0.0399), because in bull regimes RSI-30 bounces return +2.26%/20 bars (H-REGIME-001), the edge that trend-continuation buy-strength entries (H-L056, scored 0.002) leave unclaimed.

**Fit:** score 0.002017933448232534

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score 0.002017933448232534, best known for BULL 0.0399); the forward window was not opened.

- entry_rule: `((aroon_osc > 18.964 AND keltner_lower > ema_21*1.0035) AND (rsi_14 < 3.644 AND low > keltner_lower*1.0275))`
- exit_rule: `(mid_200 crosses above supertrend AND (keltner_upper crosses above sma_50 AND high < keltner_upper))`