## Iteration 26 — proposal

**Module:** DETECTOR

**Claim:** Replacing the tied participation (breadth) axis with a deviation axis — sign of distance_to_sma_200 plus position within the Bollinger band, carrying an explicit neutral deadband (0.4 < bb_percent_b < 0.6) — will produce a DETECTOR fit that clears the gate (score > -0.1126) and emit at least one non-BEAR bar in the 2026 forward window, moving the count off the frozen 71.

**Killed by:** Refuted if the fit score stays at or below -0.1126 (gate not cleared, forward window not opened), OR the window opens but still routes 100% of 2026 bars to BEAR, leaving the frozen 71-trade / -7.82% forward result unchanged.

Abandon, do not deepen, the trend-axis-replacement direction: H-L016, H-L021, and H-L025 each tried to replace the tied breadth axis with a trend discriminator (close/ema_200 + di dominance, signed median) and all three failed the fit gate (-0.215/-0.210 vs best-known -0.1126). Three same-direction refutations mean the trend axis genuinely does not out-separate breadth in-sample. The diagnosed defect is not 'wrong axis' but 'no deadband': bull_breadth 0.416 and bear_breadth 0.413 leave a razor-thin band, forcing every marginal 2026 bar to BEAR and freezing the forward window at 71. The deviation rule family (in rules_available) has never been used as the discriminator. These two minimal 3-comparison seeds define a bull leg (above the 200-day mean, upper Bollinger band, rsi>50) and a mirror bear leg (below mean, lower band, rsi<50) with an explicit neutral gap at 0.4<bb_percent_b<0.6 — bars in the middle route to neither, which is the structural fix the tied-threshold tie needs. If a deviation axis with a real deadband also fails the gate, that is strong evidence the fit bottleneck is the gate itself rather than the choice of axis, redirecting the next iteration.

- `(distance_to_sma_200 > 0 AND bb_percent_b > 0.6 AND rsi_14 > 50)`
- `(distance_to_sma_200 < 0 AND bb_percent_b < 0.4 AND rsi_14 < 50)`