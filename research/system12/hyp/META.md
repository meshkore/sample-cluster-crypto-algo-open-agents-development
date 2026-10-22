# System 12 - second layer: trade autopsy and decision tree

Walk-forward chain 2021-2025 (each year the champion chosen on earlier years): 115 trades, 70 losers.

## Out-of-sample check of the tree (each year predicted by a tree trained on earlier years only)

| year | days in position | right direction (base) | when the tree trusts | when it doubts | share doubted |
|---|---|---|---|---|---|
| 2021 | 267 | 62% | 70% | 57% | 62% |
| 2022 | 297 | 51% | 58% | 44% | 52% |
| 2023 | 312 | 50% | 52% | 49% | 60% |
| 2024 | 315 | 50% | 47% | 53% | 59% |
| 2025 | 278 | 49% | 65% | 47% | 93% |
| 2026 | 118 | 46% | 46% | 45% | 64% |

A useful layer shows 'when it doubts' clearly BELOW 'when it trusts' in most years.

## Losers vs winners at entry (median)

| feature | losers | winners |
|---|---|---|
| btc_ret_7d | -0.013 | -0.006 |
| btc_ret_30d | -0.012 | -0.013 |
| btc_ret_90d | +0.061 | +0.069 |
| btc_vs_ma20 | -0.017 | -0.015 |
| btc_vs_ma50 | -0.002 | -0.012 |
| btc_vs_ma100 | -0.005 | +0.025 |
| btc_vs_ma200 | +0.065 | +0.092 |
| ma50_slope_10d | -0.004 | +0.003 |
| ma20_vs_ma50 | -0.004 | -0.009 |
| rsi_14d | +49.847 | +47.163 |
| vol_30d | +0.534 | +0.567 |
| vol_7d_vs_90d | +0.919 | +0.971 |
| dd_from_90d_high | +0.128 | +0.120 |
| funding_7d | +0.000 | +0.000 |
| ethbtc_30d | -0.021 | -0.043 |
| breadth_50d | +0.286 | +0.154 |
| alt_lead_30d | -0.035 | -0.036 |

## The 15 worst trades

| entry | side | days | return | RSI | BTC vs MA50 | 30d return |
|---|---|---|---|---|---|---|
| 2024-07-16 | long | 18 | -14.4% | 52 | +1.0% | -2.1% |
| 2025-01-16 | long | 18 | -13.5% | 54 | +2.0% | -6.9% |
| 2023-01-12 | long | 57 | -10.9% | 72 | +7.9% | +6.3% |
| 2025-09-30 | long | 11 | -7.5% | 49 | +0.6% | +4.7% |
| 2022-10-26 | long | 14 | -5.7% | 58 | +3.3% | +7.3% |
| 2022-03-17 | long | 26 | -5.3% | 47 | +2.3% | -5.9% |
| 2022-02-08 | long | 4 | -5.1% | 63 | +3.2% | +5.6% |
| 2021-07-06 | long | 3 | -4.1% | 51 | -6.7% | -5.7% |
| 2022-07-26 | short | 2 | -3.7% | 53 | -4.7% | -1.3% |
| 2024-01-30 | long | 2 | -3.6% | 51 | +1.7% | +3.2% |
| 2025-01-03 | long | 5 | -3.5% | 50 | +0.2% | +1.3% |
| 2022-03-11 | short | 6 | -3.4% | 50 | -2.8% | -10.7% |
| 2022-03-01 | long | 4 | -3.3% | 49 | +7.3% | +13.8% |
| 2025-02-28 | short | 2 | -3.3% | 38 | -13.9% | -18.5% |
| 2024-01-16 | long | 3 | -3.3% | 46 | +0.7% | +2.4% |

## The tree trained on 2019-2025 (to read; trading uses the per-year trees above)

```
|--- btc_ret_30d <= 0.186
|   |--- funding_7d <= 0.000
|   |   |--- breadth_50d <= 0.127
|   |   |   |--- class: 1
|   |   |--- breadth_50d >  0.127
|   |   |   |--- class: 1
|   |--- funding_7d >  0.000
|   |   |--- alt_lead_30d <= -0.049
|   |   |   |--- class: 1
|   |   |--- alt_lead_30d >  -0.049
|   |   |   |--- class: 0
|--- btc_ret_30d >  0.186
|   |--- breadth_50d <= 0.679
|   |   |--- class: 1
|   |--- breadth_50d >  0.679
|   |   |--- btc_ret_30d <= 0.323
|   |   |   |--- class: 1
|   |   |--- btc_ret_30d >  0.323
|   |   |   |--- class: 0

```
