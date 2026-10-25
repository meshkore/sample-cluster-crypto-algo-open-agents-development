# System 12 - hypothesis loop report

Updated 2026-10-25T15:49:14+00:00. 15288 hypotheses tested, 1 adopted. Next adoption needs a Sharpe gain of 0.34 on 2021-2023. Train 2021-2023 (must improve), validation 2024-2025 (must not lose), test 2026 (never looked at). 

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | per year 2021-25 |
|---|---|---|---|---|---|---|---|
| champion | +148% | -13% | +48% | +25% | +9% | +4% | +34.3% |
| frozen book (paper) | +115% | -23% | +35% | +18% | +10% | +4% | +23.5% |

## Adopted, in order

- **G00233 trail_short + trend_convex**: 3/5 years, +22.5%/yr, DD 24% (was 25%); 2026 +1.3%. Generated. trailing stop on shorts: cover when BTC rises p above its low since entry THEN convex sizing: longs x(1 + 30d BTC return / p), between 0.5 and 2.

## Pieces: mean gain over the generated tests that used them

| piece | family | tests | mean gain |
|---|---|---|---|
| eth_share | basket | 991 | +8.29% |
| long_size | size | 991 | +6.34% |
| september_light | crazy | 991 | +4.95% |
| gross_cap | size | 991 | +3.58% |
| funding_crowd | exit | 991 | +2.28% |
| long_size_mod | size | 991 | +1.88% |
| long_term_filter | entry | 990 | +1.58% |
| tp_short | take-profit | 991 | +0.90% |
| alt_short | alts | 991 | +0.25% |
| trend_convex | size | 991 | +0.08% |
| pyramid_long | size | 990 | -0.16% |
| short_weaker | basket | 989 | -0.26% |
| dd_adaptive | stop-loss | 989 | -0.53% |
| tp_long | take-profit | 990 | -0.64% |
| weekend_flat | crazy | 990 | -0.86% |
| trail_short | exit | 991 | -0.93% |
| breakout_boost | entry | 991 | -0.99% |
| stop_long | stop-loss | 990 | -1.00% |
| entry_confirm | entry | 991 | -1.08% |
| rsi_trim | take-profit | 991 | -1.26% |
| eth_trend_confirm | entry | 989 | -1.31% |
| vt_mult_mod | size | 991 | -1.36% |
| stop_short | stop-loss | 989 | -1.53% |
| rsi_cover | take-profit | 988 | -1.69% |
| short_size | size | 990 | -2.08% |
| fast_trend | exit | 991 | -2.14% |
| neg_funding_boost | entry | 990 | -2.45% |
| dip_boost | entry | 991 | -2.45% |
| vt_mult | size | 991 | -2.77% |
| short_cover | exit | 990 | -2.79% |
| calm_leverage | size | 990 | -2.92% |
| vol_break | exit | 991 | -3.50% |
| ramp_up | size | 989 | -3.60% |
| atr_trail_long | exit | 989 | -4.04% |
| time_exit_long | exit | 991 | -4.47% |
| book_brake | stop-loss | 989 | -4.71% |
| vol_inverse | size | 988 | -5.02% |
| recent_edge | size | 987 | -6.85% |
| short_below | entry | 986 | -7.44% |
| day_crash | exit | 987 | -7.55% |
| trail_long | exit | 983 | -8.59% |
| alt_season | alts | 979 | -10.56% |
| entry_delay | entry | 978 | -10.85% |
| crash_exit | exit | 976 | -13.94% |
| ma_cross_exit | exit | 976 | -16.72% |
