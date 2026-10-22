# System 12 - hypothesis loop report

Updated 2026-10-22T09:42:44+00:00. 862 hypotheses tested, 2 adopted. Next adoption needs a mean gain of 4.4%/yr. 2026 is read only.

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | per year 2021-25 |
|---|---|---|---|---|---|---|---|
| champion | +173% | -11% | +40% | +29% | +13% | +1% | +37.9% |
| frozen book (paper) | +115% | -23% | +35% | +18% | +10% | +5% | +23.5% |

## Adopted, in order

- **H006 ETH share of the long leg**: 5/5 years, +10.4%/yr, DD 42% (was 42%); 2026 -3.4%. Equal BTC/ETH was never tested against other splits. ETH lagged BTC since 2022; a lower ETH share may help.
- **G00008 trail_short**: 4/5 years, +7.6%/yr, DD 37% (was 42%); 2026 -0.0%. Generated. trailing stop on shorts: cover when BTC rises p above its low since entry.

## Pieces: mean gain over the generated tests that used them

| piece | family | tests | mean gain |
|---|---|---|---|
| long_size | size | 104 | +7.52% |
| september_light | crazy | 1 | +7.14% |
| gross_cap | size | 99 | +5.62% |
| trend_convex | size | 71 | +3.84% |
| pyramid_long | size | 81 | +3.17% |
| stop_long | stop-loss | 66 | +2.27% |
| entry_confirm | entry | 66 | +1.74% |
| funding_crowd | exit | 64 | +1.68% |
| trail_short | exit | 66 | +1.56% |
| alt_short | alts | 58 | +1.48% |
| tp_short | take-profit | 60 | +1.44% |
| neg_funding_boost | entry | 1 | +1.37% |
| breakout_boost | entry | 55 | +1.13% |
| short_cover | exit | 62 | +1.09% |
| rsi_cover | take-profit | 1 | +0.88% |
| stop_short | stop-loss | 63 | +0.70% |
| ramp_up | size | 1 | +0.64% |
| eth_share | basket | 54 | +0.39% |
| dip_boost | entry | 60 | +0.06% |
| ma_cross_exit | exit | 1 | +0.00% |
| rsi_trim | take-profit | 1 | +0.00% |
| dd_adaptive | stop-loss | 1 | +0.00% |
| eth_trend_confirm | entry | 1 | +0.00% |
| short_weaker | basket | 0 | +0.00% |
| long_size_mod | size | 0 | +0.00% |
| vt_mult_mod | size | 0 | +0.00% |
| tp_long | take-profit | 58 | -0.26% |
| calm_leverage | size | 1 | -0.33% |
| time_exit_long | exit | 59 | -0.46% |
| vol_break | exit | 51 | -0.98% |
| vt_mult | size | 45 | -1.15% |
| fast_trend | exit | 66 | -1.16% |
| vol_inverse | size | 51 | -1.84% |
| book_brake | stop-loss | 50 | -1.93% |
| weekend_flat | crazy | 62 | -2.46% |
| short_size | size | 60 | -2.49% |
| trail_long | exit | 50 | -3.10% |
| long_term_filter | entry | 50 | -3.16% |
| day_crash | exit | 50 | -3.19% |
| recent_edge | size | 54 | -4.67% |
| short_below | entry | 48 | -4.81% |
| atr_trail_long | exit | 1 | -5.31% |
| alt_season | alts | 39 | -7.26% |
| crash_exit | exit | 40 | -8.21% |
| entry_delay | entry | 44 | -8.93% |
