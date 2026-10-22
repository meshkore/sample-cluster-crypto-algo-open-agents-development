# System 12 - hypothesis loop report

Updated 2026-10-22T13:12:29+00:00. 2635 hypotheses tested, 4 adopted. Next adoption needs a mean gain of 4.9%/yr. 2026 is read only.

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | per year 2021-25 |
|---|---|---|---|---|---|---|---|
| champion | +243% | -7% | +53% | +29% | +20% | -1% | +50.0% |
| frozen book (paper) | +115% | -23% | +35% | +18% | +10% | +5% | +23.5% |

## Adopted, in order

- **H006 ETH share of the long leg**: 5/5 years, +10.4%/yr, DD 42% (was 42%); 2026 -3.4%. Equal BTC/ETH was never tested against other splits. ETH lagged BTC since 2022; a lower ETH share may help.
- **G00008 trail_short**: 4/5 years, +7.6%/yr, DD 37% (was 42%); 2026 -0.0%. Generated. trailing stop on shorts: cover when BTC rises p above its low since entry.
- **G00858 stop_long + september_light**: 4/5 years, +8.3%/yr, DD 37% (was 37%); 2026 -1.8%. Generated. stop-loss on longs: out when BTC is p below the entry price THEN September (historically weakest month) at p of size.
- **G00878 pyramid_long + rsi_cover**: 4/5 years, +10.5%/yr, DD 38% (was 37%); 2026 +0.0%. Generated. pyramiding: longs x1.5 once BTC is p above entry (gross <= 100%) THEN cover shorts while BTC's 14-day RSI is below p (oversold).

## Pieces: mean gain over the generated tests that used them

| piece | family | tests | mean gain |
|---|---|---|---|
| long_size | size | 300 | +12.42% |
| long_size_mod | size | 228 | +9.93% |
| gross_cap | size | 255 | +7.56% |
| trend_convex | size | 178 | +3.85% |
| rsi_trim | take-profit | 162 | +3.62% |
| funding_crowd | exit | 194 | +3.55% |
| entry_confirm | entry | 177 | +3.50% |
| short_weaker | basket | 157 | +3.49% |
| stop_long | stop-loss | 196 | +3.30% |
| rsi_cover | take-profit | 152 | +3.23% |
| pyramid_long | size | 213 | +3.04% |
| tp_short | take-profit | 179 | +3.01% |
| september_light | crazy | 138 | +2.99% |
| breakout_boost | entry | 166 | +2.76% |
| dip_boost | entry | 157 | +2.75% |
| eth_share | basket | 158 | +2.54% |
| trail_short | exit | 173 | +2.52% |
| alt_short | alts | 187 | +2.13% |
| short_size | size | 162 | +1.89% |
| stop_short | stop-loss | 164 | +1.55% |
| vt_mult | size | 136 | +0.98% |
| neg_funding_boost | entry | 118 | +0.55% |
| short_cover | exit | 160 | +0.32% |
| tp_long | take-profit | 155 | -0.31% |
| time_exit_long | exit | 156 | -0.45% |
| vol_break | exit | 142 | -0.56% |
| vt_mult_mod | size | 111 | -0.77% |
| dd_adaptive | stop-loss | 128 | -0.83% |
| eth_trend_confirm | entry | 115 | -0.92% |
| calm_leverage | size | 119 | -0.98% |
| fast_trend | exit | 143 | -1.12% |
| short_below | entry | 128 | -1.54% |
| book_brake | stop-loss | 123 | -2.35% |
| weekend_flat | crazy | 139 | -2.65% |
| vol_inverse | size | 125 | -2.85% |
| ramp_up | size | 97 | -2.86% |
| long_term_filter | entry | 125 | -3.32% |
| atr_trail_long | exit | 94 | -3.96% |
| alt_season | alts | 92 | -4.22% |
| trail_long | exit | 118 | -4.36% |
| recent_edge | size | 123 | -4.51% |
| day_crash | exit | 109 | -5.44% |
| entry_delay | entry | 111 | -5.59% |
| ma_cross_exit | exit | 87 | -6.20% |
| crash_exit | exit | 76 | -10.00% |
