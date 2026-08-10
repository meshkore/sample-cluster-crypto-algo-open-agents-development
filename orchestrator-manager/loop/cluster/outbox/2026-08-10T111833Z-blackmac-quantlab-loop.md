## Iteration 56 — REFUTED

**Module:** BULL

**Hypothesis:** A trend-continuation long entry that buys confirmed strength — close above ema_50, a fresh di_plus/di_minus bullish cross, and above-average volume participation — clears the BULL gate (evolved score > best-known 0.0399) and, once the forward window opens, beats the incumbent +1.12%. This inverts the two exhausted BULL frames: the deviation/pullback long that bought weakness (H-L050) and the breadth tie-break that fought the router (H-L036/040/041/045).

**Fit:** score 0.002017933448232534

**Forward 2026:** not opened -- the fit did not clear the gate

the fit did not clear the gate (score 0.002017933448232534, best known for BULL 0.0399); the forward window was not opened.

- entry_rule: `((close > low AND low > ema_200) AND (bb_width > 0.4594 AND high crosses above low) AND close > ema_50)`
- exit_rule: `bb_mid > -0.3661`