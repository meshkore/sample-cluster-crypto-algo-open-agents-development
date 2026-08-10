## Iteration 67 — INCONCLUSIVE

**Module:** SIDEWAYS

**Hypothesis:** A mean-reversion long entry -- BUY (seed_rules[0]) when close is below bb_lower while adx is sub-25 (a genuine range, not a trend) and rsi_14 is below 40 (oversold), and SELL (seed_rules[1]) when close crosses back up through bb_mid or rsi_14 exceeds 60 -- clears the SIDEWAYS evolved fold-fit gate (score > best-known 0.0086), because the edge inside a range is fading oversold extremes at the lower band back toward the mean, which is the exact inverse of the bb_upper breakout entry H-L062 measure

**Fit:** score 0.001921199216332492

**Forward 2026:** +1.12% on 96 trades

forward +1.12% on 96 trades, against incumbent +1.12%. The SIDEWAYS module took no trades in 2026, so this run measured the incumbent rather than the hypothesis: nothing about this direction was tested.

- entry_rule: `mid_200 < 75.005`
- exit_rule: `(ema_26 > ema_200 AND (adx < 23.428 AND close < keltner_mid AND aroon_down > 15.478) AND (distance_to_sma_50 < 0.3757 AND pct_below_high_55 < 0.1072))`