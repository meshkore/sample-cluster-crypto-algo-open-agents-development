## Iteration 19 — REFUTED

**Module:** SIDEWAYS

**Hypothesis:** A range-regime SIDEWAYS entry gated on weak two-sided Aroon trend (aroon_up<70 AND aroon_down<70) with a stochastic cross up out of oversold will move the 2026 forward trade count off the frozen 71 by routing some range-bound bars to mean-reversion longs instead of BEAR shorts.

**Fit:** score -0.10478298588758644

**Forward 2026:** -7.82% on 71 trades

forward -7.82% on 71 trades, against incumbent -7.82%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `(volume < volume_sma_20*4.43 AND (bb_width > 0.4124 AND adx > 24.845 AND pct_below_high_55 < 0.5995))`
- exit_rule: `((rsi_7 < 74.58 AND ichimoku_tenkan crosses below low_20) OR (volume > volume_sma_50*5.27 AND distance_to_sma_50 < 0.0372) OR (high > supertrend AND aroon_down > 75.184))`