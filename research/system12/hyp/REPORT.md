# System 12 - hypothesis loop report

Updated 2026-10-22T09:03:27+00:00. 582 hypotheses tested, 2 adopted. Next adoption needs a mean gain of 4.2%/yr. 2026 is read only.

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
| long_size | size | 49 | +10.46% |
| gross_cap | size | 48 | +8.69% |
| trend_convex | size | 34 | +3.13% |
| pyramid_long | size | 35 | +2.85% |
| stop_long | stop-loss | 36 | +1.78% |
| breakout_boost | entry | 34 | +1.31% |
| trail_short | exit | 33 | +1.30% |
| funding_crowd | exit | 34 | +1.24% |
| entry_confirm | entry | 34 | +1.17% |
| alt_short | alts | 32 | +0.13% |
| dip_boost | entry | 34 | +0.05% |
| tp_short | take-profit | 34 | -0.04% |
| tp_long | take-profit | 33 | -0.09% |
| eth_share | basket | 32 | -0.24% |
| time_exit_long | exit | 34 | -0.31% |
| fast_trend | exit | 33 | -0.37% |
| stop_short | stop-loss | 32 | -0.43% |
| vol_break | exit | 34 | -1.05% |
| vt_mult | size | 33 | -1.30% |
| book_brake | stop-loss | 33 | -1.43% |
| weekend_flat | crazy | 33 | -1.55% |
| short_cover | exit | 34 | -1.64% |
| long_term_filter | entry | 33 | -1.72% |
| recent_edge | size | 33 | -2.85% |
| day_crash | exit | 33 | -3.61% |
| short_size | size | 33 | -3.66% |
| trail_long | exit | 33 | -4.39% |
| vol_inverse | size | 33 | -4.67% |
| short_below | entry | 32 | -5.42% |
| entry_delay | entry | 32 | -8.76% |
| crash_exit | exit | 33 | -9.26% |
| alt_season | alts | 33 | -9.98% |
