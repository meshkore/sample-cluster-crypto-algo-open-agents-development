# System 12 - hypothesis loop report

Updated 2026-10-22T14:14:52+00:00. 3109 hypotheses tested, 7 adopted. Next adoption needs a mean gain of 5.0%/yr. 2026 is read only.

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | per year 2021-25 |
|---|---|---|---|---|---|---|---|
| champion | +326% | +29% | +72% | +45% | +36% | -23% | +79.4% |
| frozen book (paper) | +115% | -23% | +35% | +18% | +10% | +5% | +23.5% |

## Adopted, in order

- **H006 ETH share of the long leg**: 5/5 years, +10.4%/yr, DD 42% (was 42%); 2026 -3.4%. Equal BTC/ETH was never tested against other splits. ETH lagged BTC since 2022; a lower ETH share may help.
- **G00008 trail_short**: 4/5 years, +7.6%/yr, DD 37% (was 42%); 2026 -0.0%. Generated. trailing stop on shorts: cover when BTC rises p above its low since entry.
- **G00858 stop_long + september_light**: 4/5 years, +8.3%/yr, DD 37% (was 37%); 2026 -1.8%. Generated. stop-loss on longs: out when BTC is p below the entry price THEN September (historically weakest month) at p of size.
- **G00878 pyramid_long + rsi_cover**: 4/5 years, +10.5%/yr, DD 38% (was 37%); 2026 +0.0%. Generated. pyramiding: longs x1.5 once BTC is p above entry (gross <= 100%) THEN cover shorts while BTC's 14-day RSI is below p (oversold).
- **K-pr-turn-of-month-steroids System 12 + Turn of the Month on Steroids**: 5/5 years, +13.6%/yr, DD 38% (was 38%); 2026 -23.1%. Catalogue strategy pr-turn-of-month-steroids (https://doc.stocksharp.com/en/api-examples/1496_Turn_of_the_Month_on_Steroids), grade B on its own: 2021-25 +14.2%/yr, DD 16%. Combined with System 12: blended 25% or 50%, as a filter on System 12's longs, or added on top (gross <= 100%).
- **K-cal-uptober-long-october System 12 + Uptober: hold BTC during October only**: 5/5 years, +11.2%/yr, DD 38% (was 38%); 2026 +0.2%. Catalogue strategy cal-uptober-long-october (https://roguequant.substack.com/p/bitcoins-october-seasonality-exposed), grade B on its own: 2021-25 +9.7%/yr, DD 14%. Combined with System 12: blended 25% or 50%, as a filter on System 12's longs, or added on top (gross <= 100%).
- **K-vol-chaikin-capitulation System 12 + Chaikin Volatility spike capitulation buy**: 4/5 years, +9.2%/yr, DD 39% (was 38%); 2026 +0.6%. Catalogue strategy vol-chaikin-capitulation (https://www.luxalgo.com/library/concept/chaikin-volatility/), grade B on its own: 2021-25 +6.7%/yr, DD 13%. Combined with System 12: blended 25% or 50%, as a filter on System 12's longs, or added on top (gross <= 100%).

## Pieces: mean gain over the generated tests that used them

| piece | family | tests | mean gain |
|---|---|---|---|
| long_size | size | 351 | +12.44% |
| long_size_mod | size | 283 | +9.90% |
| gross_cap | size | 299 | +7.82% |
| rsi_trim | take-profit | 202 | +4.06% |
| september_light | crazy | 175 | +3.67% |
| funding_crowd | exit | 223 | +3.39% |
| stop_long | stop-loss | 225 | +3.33% |
| trend_convex | size | 222 | +3.32% |
| entry_confirm | entry | 209 | +3.30% |
| breakout_boost | entry | 207 | +3.29% |
| tp_short | take-profit | 207 | +3.28% |
| short_weaker | basket | 196 | +2.84% |
| dip_boost | entry | 182 | +2.83% |
| rsi_cover | take-profit | 192 | +2.81% |
| alt_short | alts | 219 | +2.74% |
| pyramid_long | size | 245 | +2.71% |
| eth_share | basket | 192 | +2.37% |
| trail_short | exit | 206 | +2.14% |
| short_size | size | 188 | +1.56% |
| stop_short | stop-loss | 199 | +1.36% |
| vt_mult | size | 159 | +0.81% |
| neg_funding_boost | entry | 150 | +0.67% |
| short_cover | exit | 185 | +0.46% |
| time_exit_long | exit | 188 | -0.31% |
| tp_long | take-profit | 182 | -0.48% |
| vol_break | exit | 166 | -0.71% |
| calm_leverage | size | 147 | -0.77% |
| vt_mult_mod | size | 137 | -0.77% |
| dd_adaptive | stop-loss | 154 | -0.81% |
| eth_trend_confirm | entry | 133 | -0.83% |
| fast_trend | exit | 170 | -1.10% |
| short_below | entry | 147 | -1.82% |
| book_brake | stop-loss | 149 | -2.44% |
| weekend_flat | crazy | 160 | -2.63% |
| ramp_up | size | 113 | -2.90% |
| vol_inverse | size | 144 | -3.09% |
| long_term_filter | entry | 141 | -3.19% |
| alt_season | alts | 103 | -3.84% |
| atr_trail_long | exit | 113 | -3.96% |
| recent_edge | size | 138 | -4.19% |
| trail_long | exit | 136 | -4.76% |
| entry_delay | entry | 129 | -4.79% |
| day_crash | exit | 125 | -5.12% |
| ma_cross_exit | exit | 103 | -6.52% |
| crash_exit | exit | 92 | -10.88% |
