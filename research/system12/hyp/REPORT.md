# System 12 - hypothesis loop report

Updated 2026-10-21T19:29:30+00:00. 110 hypotheses tested, 2 adopted. Next adoption needs a mean gain of 3.4%/yr. 2026 is read only.

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | per year 2021-25 |
|---|---|---|---|---|---|---|---|
| champion | +173% | -11% | +40% | +29% | +13% | +4% | +37.9% |
| frozen book (paper) | +115% | -23% | +35% | +18% | +10% | +7% | +23.5% |

## Adopted, in order

- **H006 ETH share of the long leg**: 5/5 years, +10.4%/yr, DD 42% (was 42%); 2026 -3.4%. Equal BTC/ETH was never tested against other splits. ETH lagged BTC since 2022; a lower ETH share may help.
- **G00008 trail_short**: 4/5 years, +7.6%/yr, DD 37% (was 42%); 2026 -0.0%. Generated. trailing stop on shorts: cover when BTC rises p above its low since entry.

## Pieces: mean gain over the generated tests that used them

| piece | family | tests | mean gain |
|---|---|---|---|
| gross_cap | size | 3 | +20.83% |
| long_size | size | 2 | +16.23% |
| vt_mult | size | 2 | +6.12% |
| trail_short | exit | 3 | +2.22% |
| trend_convex | size | 3 | +1.93% |
| pyramid_long | size | 3 | +1.32% |
| stop_long | stop-loss | 19 | +0.98% |
| recent_edge | size | 3 | +0.00% |
| weekend_flat | crazy | 3 | +0.00% |
| tp_short | take-profit | 3 | -0.05% |
| book_brake | stop-loss | 2 | -0.12% |
| fast_trend | exit | 2 | -0.18% |
| entry_confirm | entry | 3 | -0.32% |
| vol_break | exit | 3 | -0.32% |
| tp_long | take-profit | 3 | -0.40% |
| stop_short | stop-loss | 3 | -0.55% |
| eth_share | basket | 2 | -0.60% |
| funding_crowd | exit | 2 | -0.60% |
| day_crash | exit | 2 | -0.60% |
| breakout_boost | entry | 3 | -0.85% |
| long_term_filter | entry | 2 | -1.05% |
| time_exit_long | exit | 3 | -1.13% |
| alt_season | alts | 2 | -3.52% |
| short_size | size | 2 | -3.82% |
| trail_long | exit | 32 | -4.28% |
| dip_boost | entry | 3 | -4.59% |
| alt_short | alts | 2 | -5.06% |
| vol_inverse | size | 3 | -5.08% |
| short_cover | exit | 2 | -6.72% |
| short_below | entry | 2 | -11.78% |
| crash_exit | exit | 3 | -12.47% |
| entry_delay | entry | 3 | -12.64% |
