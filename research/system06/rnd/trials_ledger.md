# Every combination tested — profits per year

Study `thresholds-v3-heldout` · 1668 combinations completed · 1607 of them actually traded · exported 2026-09-07.

Years **2018–2023** are what the search was allowed to optimise on. **2024–2025** were recorded on every single trial and used for nothing — they are the out-of-sample check. **2026 was never touched by the search.**

## The incumbent champion

| trial | fit | held-out | 18      19      20      21      22      23      24      25      | maxDD | trades |
|---|---|---|---|---|
|    2 | +0.2805 | +0.1643 |  +190.2%   +52.9%  +129.3% +11884.2%   +12.2%   +29.8%   +78.4%    -0.7% | 22.0% | 3694 |

## The ten best on the FITTED years (2018–2023)

This is what the search optimises, and where it did find better combinations.

| trial | fit | held-out | 18      19      20      21      22      23      24      25      | maxDD | trades |
|---|---|---|---|---|
|   68 | +0.2964 | +0.1467 |  +192.4%   +51.9%  +134.6% +11005.8%   +21.1%   +71.6%   +69.9%    -3.8% | 19.9% | 3369 |
|   47 | +0.2925 | +0.1094 |  +188.1%   +72.3%  +177.3% +11135.3%   +18.4%   +60.4%   +53.2%   -10.8% | 20.2% | 3092 |
|   42 | +0.2912 | +0.0867 |  +246.2%   +32.8%  +125.2% +15242.1%   +18.7%   +38.8%   +23.6%    -5.0% | 24.2% | 6789 |
|   64 | +0.2910 | +0.1163 |  +179.3%   +40.2%  +118.1% +8515.8%   +18.3%   +36.0%   +24.8%    -4.6% | 22.0% | 6788 |
|   85 | +0.2832 | +0.1813 |  +210.1%   +66.6%  +144.4% +10379.4%   +12.4%   +31.0%   +75.7%    +2.0% | 22.0% | 3867 |
|   35 | +0.2830 | +0.1625 |  +185.7%   +56.9%  +127.3% +10997.5%   +13.7%   +32.2%   +80.2%    -1.4% | 19.5% | 3683 |
|   49 | +0.2830 | +0.1566 |  +192.1%   +57.2%  +127.5% +10963.8%   +13.7%   +34.8%   +82.1%    -2.6% | 20.4% | 3678 |
|   25 | +0.2810 | +0.1770 |  +196.4%   +51.4%  +134.6% +13511.1%   +13.6%   +29.1%   +93.0%    +1.8% | 21.1% | 3694 |
|   21 | +0.2808 | +0.1744 |  +170.1%   +40.5%  +134.7% +11236.7%   +12.0%   +31.4%   +86.6%    +0.9% | 20.1% | 3812 |
|   51 | +0.2806 | +0.1395 |  +191.2%   +55.2%  +131.9% +9848.0%   +12.7%   +29.3%   +71.8%    -5.6% | 22.0% | 3694 |

## The ten best on the years the search NEVER saw (2024–2025)

Listed for completeness. **These were never selectable** — picking a combination by this column would turn the out-of-sample check into a selection input, which is the exact mistake this design exists to prevent.

| trial | fit | held-out | 18      19      20      21      22      23      24      25      | maxDD | trades |
|---|---|---|---|---|
|   67 | +0.0998 | +0.2205 |  +124.8%   +42.0%  +109.0% +11429.0%   +12.0%   +34.5%   +92.4%   +10.1% | 40.0% | 3694 |
|   14 | +0.2528 | +0.2103 |  +183.9%   +17.5%   +99.5% +10552.3%    +8.0%   +36.8%   +64.2%    +7.8% | 20.7% | 4086 |
|    8 | +0.1597 | +0.2091 |  +119.6%   -19.1%   +31.6% +3465.9%    +5.5%   +35.2%   +49.9%    +7.2% | 24.7% | 4259 |
|   31 | +0.2741 | +0.2090 |  +211.3%   +47.6%  +108.0% +9811.2%    +7.9%   +35.3%   +79.3%    +7.1% | 20.2% | 3907 |
|   48 | +0.2724 | +0.2088 |  +178.7%   +54.0%   +89.9% +1387.9%    +7.6%   +29.8%   +31.2%    +7.9% | 19.0% | 2550 |
|   41 | +0.2648 | +0.2072 |  +188.5%   +25.5%  +128.1% +9858.8%    +7.2%   +36.8%   +69.4%    +7.1% | 20.2% | 3982 |
|   59 | +0.1824 | +0.2072 |  +144.0%   +44.1%  +100.8% +9556.3%   +11.4%   +31.6%   +89.7%    +7.5% | 31.7% | 3694 |
|   71 | +0.1471 | +0.1996 |  +167.0%   -11.1%   +75.8% +9206.8%    -6.8%   +44.8%   +81.7%    +6.0% | 25.2% | 4434 |
|    6 | +0.2380 | +0.1980 |   +83.0%   +23.6%   +62.7% +1841.2%    +4.2%   +19.0%   +37.2%    +5.4% | 11.7% | 3973 |
|   38 | +0.1572 | +0.1857 |  +166.8%    -2.6%  +133.3% +16486.7%    -8.1%   +55.6%  +107.1%    +6.6% | 25.5% | 4474 |

## Does moving a value change anything?

Yes — every one of the 1,607 trading combinations produced a different book. The question was never whether the values matter. It is whether any setting is better on years it was **not** fitted to.

Below, trials are cut into quartiles of each lever's value and the median result per quartile is shown. A column that climbs or falls means the lever pulls in a direction; a flat one means whatever it does is drowned by the other 32 levers moving alongside it. **These numbers are confounded by construction** — a joint search cannot isolate one lever. The clean per-lever curve requires moving one at a time, which is what A115 measures separately.

| lever | champion | range tried | median fit by quartile (low→high) | ρ(value, fit) | ρ(value, held-out) |
|---|---|---|---|---|---|
| `breadth_gate` | 0.3 | 0 … 0.5879 | +0.140 · +0.137 · +0.144 · +0.128 | -0.050 | -0.044 |
| `consensus_k` | 1 | 1 … 2 | +0.157 · +0.147 · +0.135 · +0.114 | -0.306 | -0.298 |
| `conviction_sizing` | 0 | 0 … 0.6586 | +0.169 · +0.122 · +0.131 · +0.129 | -0.138 | -0.160 |
| `dd_sizer` | 0 | 0 … 0.981 | +0.160 · +0.135 · +0.132 · +0.120 | -0.178 | -0.135 |
| `edge_monitor` | 0 | 0 … 0.8558 | +0.155 · +0.132 · +0.134 · +0.133 | -0.105 | -0.157 |
| `enter` | 0.75 | 0.5579 … 0.8986 | +0.120 · +0.132 · +0.159 · +0.144 | +0.098 | -0.063 |
| `exit_` | 0.25 | 0.0563 … 0.4765 | +0.145 · +0.155 · +0.135 · +0.122 | -0.069 | -0.055 |
| `feargreed` | 0 | 0 … 0.989 | +0.174 · +0.129 · +0.120 · +0.131 | -0.171 | -0.188 |
| `fng_min` | 25 | 0 … 47.02 | +0.120 · +0.146 · +0.141 · +0.140 | +0.018 | -0.003 |
| `horserace` | 0 | 0 … 0.682 | +0.161 · +0.139 · +0.131 · +0.122 | -0.156 | -0.155 |
| `hurst_gate` | 0 | 0 … 0.6121 | +0.164 · +0.132 · +0.143 · +0.108 | -0.216 | -0.198 |
| `martingale` | 0 | 0 … 0.4995 | +0.159 · +0.135 · +0.126 · +0.128 | -0.164 | -0.187 |
| `max_positions` | 2 | 1 … 8 | +0.143 · +0.174 · +0.129 · +0.105 | -0.145 | -0.023 |
| `meta_margin` | 0.005 | 0 … 0.04325 | +0.147 · +0.157 · +0.126 · +0.117 | -0.130 | -0.334 |
| `micro_gate` | 0 | 0 … 0.9873 | +0.163 · +0.129 · +0.137 · +0.115 | -0.162 | -0.118 |
| `min_age_days` | 0 | 0 … 365 | +0.168 · +0.144 · +0.129 · +0.117 | -0.204 | -0.129 |
| `min_hold` | 16 | 1 … 282 | +0.176 · +0.168 · +0.146 · +0.086 | -0.350 | +0.038 |
| `mom_gate` | 0 | 0 … 0.4526 | +0.159 · +0.127 · +0.141 · +0.126 | -0.129 | -0.143 |
| `money_kelly` | 0 | 0 … 0.9884 | +0.163 · +0.137 · +0.129 · +0.120 | -0.175 | -0.132 |
| `money_model` | 0.5 | 0 … 0.9689 | +0.121 · +0.145 · +0.143 · +0.140 | +0.046 | +0.014 |
| `money_pyramid` | 0.132 | 0 … 0.992 | +0.159 · +0.126 · +0.131 · +0.137 | -0.113 | -0.126 |
| `position_fraction` | 0.15 | 0.05007 … 0.8437 | +0.121 · +0.160 · +0.133 · +0.132 | -0.029 | -0.034 |
| `regime_deploy` | 0.5 | 0 … 0.9871 | +0.093 · +0.149 · +0.155 · +0.156 | +0.212 | +0.177 |
| `regime_persist` | 0 | 0 … 438.3 | +0.164 · +0.132 · +0.122 · +0.129 | -0.130 | -0.143 |
| `scale_enter` | 0 | 0 … 0.9483 | +0.160 · +0.137 · +0.132 · +0.124 | -0.156 | -0.127 |
| `scale_in` | 0 | 0 … 4 | +0.160 · +0.135 · +0.120 · +0.130 | -0.059 | -0.069 |
| `stop_loss` | 0.08 | 0 … 0.2191 | +0.119 · +0.149 · +0.149 · +0.137 | +0.063 | +0.103 |
| `sweep` | 0 | 0 … 0.8505 | +0.149 · +0.135 · +0.135 · +0.127 | -0.116 | -0.117 |
| `trail_stop` | 0.12 | 0 … 0.3277 | +0.124 · +0.145 · +0.149 · +0.131 | +0.039 | +0.070 |
| `tree_weight` | 0 | 0 … 0.9702 | +0.155 · +0.129 · +0.129 · +0.134 | -0.141 | -0.173 |
| `trend_soft` | 0 | 0 … 0.9097 | +0.159 · +0.139 · +0.120 · +0.132 | -0.125 | -0.057 |
| `vol_floor` | 0.4 | 0.1015 … 0.9841 | +0.128 · +0.157 · +0.135 · +0.126 | -0.008 | -0.037 |
| `vol_scale` | 0 | 0 … 1.524 | +0.051 · +0.108 · +0.163 · +0.195 | +0.414 | +0.333 |

## How to read this

Every row is one full 8-year backtest of the whole 14-symbol book, with Binance-style costs: 10 bp commission, 5 bp slippage, market impact by participation, $100 minimum order. The model is identical in every row — only the decision-layer values differ, which is why thousands of combinations were affordable at all: **no retraining, only replay.**
