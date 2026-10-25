# Rocket - report (auto, 2026-10-19T12:23:53+00:00)

Generated from `ledger.jsonl` by `rocket.py report`. Notes by hand: `JOURNAL.md`. Gain = selection-law score over 2022-25 with the validator minus without it (same champion, same book). Return/DD per year shown as `yy:ret/dd`.

## Universe: today

Baseline (release 34, no validator): law +0.270, max DD 24%, win rate 56.1%.

| | tested | win | promising | neutral | hurts | silent |
|---|---|---|---|---|---|---|
| real ideas | 15737 | 6 | 550 | 1269 | 13275 | 637 |
| placebo (time-shifted) | 5055 | 9 | 264 | 556 | 4108 | 118 |

**Evidence test (primary ideas only):** 317 / 13545 = 2.34% win-or-promising vs placebo 5.53%, z = -16.2. Derived ideas (combos, half, band, neighbours of leaders: 239 / 1555) are built from leaders picked on the SAME years they are graded on, so their rate is selection bias, not evidence; they are listed for follow-up only. A z above +3 would be worth the operator's time.

Chance rate: 0.2% of active placebo ideas 'win' and 5.5% are win-or-promising; real ideas: 0.0% and 3.7%. A family is only interesting where it clearly beats the placebo.

| family | tested | active | win % | win-or-promising % | best gain | best idea |
|---|---|---|---|---|---|---|
| martingale | 126 | 126 | 1.6% | 42.9% | +0.136 | martingale win x2.0^k k<=2 cap 3.0 dd-gate 0.15 |
| random | 5588 | 5237 | 0.0% | 1.2% | +0.107 | rel efficiency 15m n=47 |
| combo2 | 239 | 239 | 0.0% | 7.9% | +0.107 | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| robust | 159 | 159 | 0.0% | 17.6% | +0.107 | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| indicators | 2184 | 2159 | 0.0% | 0.8% | +0.105 | self vr 1d n=75 |
| random_combo | 1087 | 1087 | 0.0% | 17.4% | +0.105 | mkt_disp skew 2h n=29 OR mkt_disp autocorr 2h n=423 |
| miner_random | 456 | 456 | 0.4% | 33.3% | +0.089 | miner rules K=10 on 20 random features (seed 834803) boost 2.0 cut 0.5 |
| cross_section | 1596 | 1516 | 0.0% | 0.5% | +0.065 | rank vol 4h n=25 |
| ma_scan | 2093 | 1937 | 0.0% | 0.0% | +0.064 | self sma_dist 1d n=298 |
| ma_cross | 612 | 610 | 0.0% | 0.0% | +0.063 | self ma_cross 1d a=10 b=300 |
| half | 40 | 40 | 0.0% | 2.5% | +0.062 | rank kurt 1h n=7 |
| engine44 | 44 | 43 | 0.0% | 2.3% | +0.057 | x down_streak |
| miner | 44 | 44 | 0.0% | 25.0% | +0.050 | miner rules K=10 boost 2.0 cut 0.5 |
| band | 40 | 30 | 0.0% | 6.7% | +0.047 | rank kurt 1h n=7 |
| macd | 783 | 782 | 0.0% | 0.4% | +0.041 | self macd 1h a=5 b=13 sig=9 |
| coin | 1 | 1 | 0.0% | 0.0% | +0.041 | coin |
| conviction | 104 | 104 | 0.0% | 7.7% | +0.020 | conviction operator split q 0.75 boost 1.5 cut 0.75 |
| rsi | 498 | 493 | 0.0% | 0.0% | +0.007 | self rsi 1d n=220 |
| macro | 8 | 7 | 0.0% | 0.0% | +0.000 | macro ref_y10_chg20 |
| daily | 21 | 16 | 0.0% | 0.0% | +0.000 | daily oi_BTCUSDT n=1 |
| funding | 5 | 5 | 0.0% | 0.0% | -0.013 | funding n=3 |
| ml | 4 | 4 | 0.0% | 0.0% | -0.018 | learned validator on bank 'all' |
| calendar | 3 | 3 | 0.0% | 0.0% | -0.031 | cal hour |
| data | 1 | 1 | 0.0% | 0.0% | -0.063 | breadth |
| model | 1 | 1 | 0.0% | 0.0% | -0.159 | model |

### Best 25 (win or promising)

| gain | verdict | sig yrs | win rate | max DD | years | idea |
|---|---|---|---|---|---|---|
| +0.136 | promising | 3/4 | 55.1% (base 56.1%) | 27% | 22:+65%/17% 23:+28%/7% 24:+78%/27% 25:+79%/22% | martingale win x2.0^k k<=2 cap 3.0 dd-gate 0.15 |
| +0.136 | promising | 3/4 | 55.1% (base 56.1%) | 27% | 22:+65%/17% 23:+28%/7% 24:+78%/27% 25:+79%/22% | martingale win x2.0^k k<=3 cap 3.0 dd-gate 0.15 |
| +0.132 | promising | 3/4 | 54.8% (base 56.1%) | 28% | 22:+65%/17% 23:+28%/7% 24:+89%/28% 25:+77%/22% | martingale win x2.0^k k<=2 cap 3.0 dd-gate None |
| +0.132 | promising | 3/4 | 54.8% (base 56.1%) | 28% | 22:+65%/17% 23:+28%/7% 24:+89%/28% 25:+77%/22% | martingale win x2.0^k k<=3 cap 3.0 dd-gate None |
| +0.129 | promising | 3/4 | 54.9% (base 56.1%) | 26% | 22:+62%/17% 23:+27%/7% 24:+97%/26% 25:+75%/22% | martingale win x1.5^k k<=3 cap 3.0 dd-gate 0.15 |
| +0.128 | promising | 4/4 | 54.8% (base 56.1%) | 27% | 22:+62%/17% 23:+27%/7% 24:+109%/27% 25:+75%/22% | martingale win x1.5^k k<=3 cap 3.0 dd-gate None |
| +0.107 | win | 3/4 | 56.3% (base 56.1%) | 23% | 22:+39%/18% 23:+26%/3% 24:+92%/23% 25:+116%/15% | rel efficiency 15m n=47 |
| +0.107 | promising | 1/4 | 56.3% (base 56.1%) | 18% | 22:+36%/18% 23:+24%/4% 24:+94%/18% 25:+90%/12% | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| +0.107 | promising | 1/4 | 56.3% (base 56.1%) | 18% | 22:+36%/18% 23:+24%/4% 24:+94%/18% 25:+90%/12% | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| +0.105 | promising | 1/4 | 58.0% (base 56.1%) | 22% | 22:+45%/17% 23:+19%/5% 24:+99%/19% 25:+109%/22% | mkt_disp skew 2h n=29 OR mkt_disp autocorr 2h n=423 |
| +0.104 | promising | 3/4 | 55.2% (base 56.1%) | 26% | 22:+63%/17% 23:+28%/7% 24:+72%/26% 25:+53%/24% | martingale win x2.0^k k<=2 cap 3.0 dd-gate 0.08 |
| +0.104 | promising | 3/4 | 55.2% (base 56.1%) | 26% | 22:+63%/17% 23:+28%/7% 24:+72%/26% 25:+53%/24% | martingale win x2.0^k k<=3 cap 3.0 dd-gate 0.08 |
| +0.104 | promising | 1/4 | 58.7% (base 56.1%) | 23% | 22:+51%/17% 23:+18%/3% 24:+94%/23% 25:+129%/12% | mkt_disp sma_slope 1h n=3 OR mkt_disp skew 2h n=29 OR rank skew 1d n=225 |
| +0.103 | promising | 1/4 | 57.3% (base 56.1%) | 23% | 22:+57%/17% 23:+16%/3% 24:+88%/23% 25:+87%/16% | rank skew 1d n=225 OR self skew 15m n=212 |
| +0.102 | promising | 3/4 | 55.3% (base 56.1%) | 26% | 22:+61%/17% 23:+27%/7% 24:+85%/26% 25:+55%/24% | martingale win x1.5^k k<=3 cap 3.0 dd-gate 0.08 |
| +0.102 | promising | 2/4 | 55.5% (base 56.1%) | 22% | 22:+47%/18% 23:+25%/4% 24:+94%/22% 25:+71%/19% | rank kurt 1h n=7 OR mkt_mean pos 15m n=11 |
| +0.102 | promising | 1/4 | 57.3% (base 56.1%) | 22% | 22:+45%/18% 23:+24%/4% 24:+101%/22% 25:+76%/16% | rank kurt 1h n=7 OR mkt_disp sma_dist 1h n=13 |
| +0.101 | promising | 1/4 | 55.4% (base 56.1%) | 23% | 22:+47%/18% 23:+23%/3% 24:+93%/23% 25:+79%/16% | rank kurt 1h n=7 OR rel pos 2h n=41 |
| +0.100 | promising | 1/4 | 56.9% (base 56.1%) | 23% | 22:+38%/19% 23:+23%/3% 24:+95%/23% 25:+128%/19% | self efficiency 15m n=41 OR rel efficiency 15m n=41 |
| +0.100 | promising | 3/4 | 55.4% (base 56.1%) | 26% | 22:+58%/17% 23:+25%/7% 24:+67%/26% 25:+59%/23% | martingale win x2.0^k k<=1 cap 2.0 dd-gate 0.15 |
| +0.100 | promising | 3/4 | 55.4% (base 56.1%) | 26% | 22:+58%/17% 23:+25%/7% 24:+67%/26% 25:+59%/23% | martingale win x2.0^k k<=1 cap 3.0 dd-gate 0.15 |
| +0.100 | promising | 3/4 | 55.4% (base 56.1%) | 26% | 22:+58%/17% 23:+25%/7% 24:+67%/26% 25:+59%/23% | martingale win x2.0^k k<=2 cap 2.0 dd-gate 0.15 |
| +0.100 | promising | 3/4 | 55.4% (base 56.1%) | 26% | 22:+58%/17% 23:+25%/7% 24:+67%/26% 25:+59%/23% | martingale win x2.0^k k<=3 cap 2.0 dd-gate 0.15 |
| +0.100 | promising | 2/4 | 58.2% (base 56.1%) | 24% | 22:+48%/18% 23:+26%/4% 24:+87%/24% 25:+67%/19% | rank kurt 1h n=7 OR self rsi 15m n=11 |
| +0.100 | promising | 2/4 | 58.2% (base 56.1%) | 24% | 22:+48%/18% 23:+26%/4% 24:+87%/24% 25:+67%/19% | rank kurt 1h n=7 OR self rsi 15m n=11 |

### miner: do criteria learned on past trades hold the next year?

Win rate of the champion's trades inside the learned criteria vs outside, in the training years and in the year after (the same trades the baseline took).

| idea | year | criteria found | train win in / out | next-year win in / out (n in) |
|---|---|---|---|---|
| miner rules K=10 on 20 random features (seed 834803) boost 2.0 cut 0.5 | 2022 | self zscore 1d n=20 in (1.2295, inf]; macro ref_oil_ret20 in (-inf, -0.1578] | 0.5897 / 0.2667 | 0.5812 / 0.4457 (234) |
| miner rules K=10 on 20 random features (seed 834803) boost 2.0 cut 0.5 | 2023 | cal dow in (-inf, 1.0]; btc sma_dist 1d n=50 in (0.099, inf] | 0.6098 / 0.3901 | 0.7407 / 0.75 (81) |
| miner rules K=10 on 20 random features (seed 834803) boost 2.0 cut 0.5 | 2024 | macro ref_vix_pct in (0.7123, 0.9286]; macro ref_ndx_ret20 in (0.0399, inf] | 0.6126 / 0.3697 | 0.5972 / 0.65 (1656) |
| miner rules K=10 on 20 random features (seed 834803) boost 2.0 cut 0.5 | 2025 | breadth in (0.9091, inf]; btc sma_dist 1d n=50 in (0.146, inf] | 0.6104 / 0.5345 | 0.509 / 0.5211 (998) |
| miner rules K=10 on 30 random features (seed 909497) boost 2.0 cut 0.5 | 2022 | self rsi 1d n=7 in (66.0632, inf]; self zscore 1d n=20 in (1.2295, inf] | 0.6154 / 0.2338 | 0.5874 / 0.4466 (223) |
| miner rules K=10 on 30 random features (seed 909497) boost 2.0 cut 0.5 | 2023 | model in (0.0078, 0.0217]; cal dow in (-inf, 1.0] | 0.5812 / 0.4412 | 0.7439 / 0.6667 (82) |
| miner rules K=10 on 30 random features (seed 909497) boost 2.0 cut 0.5 | 2024 | macro ref_ndx_ret60 in (0.1132, inf]; model in (0.0074, 0.02] | 0.6039 / 0.3413 | 0.6066 / 0.5205 (1505) |
| miner rules K=10 on 30 random features (seed 909497) boost 2.0 cut 0.5 | 2025 | macro ref_vix_chg20 in (-inf, -0.1527]; macro ref_curve in (0.04, 0.22] | 0.6171 / 0.5188 | 0.4822 / 0.5776 (985) |
| miner rules K=10 +pairs on 30 random features (seed 671163) boost 2.0 cut 1.0 | 2022 | btc vol 1d n=30 in (-inf, 0.0328] & self rsi 1d n=14 in (54.5483, inf]; btc vol 1d n=30 in | 0.6762 / 0.4894 | 0.4321 / 0.5796 (81) |
| miner rules K=10 +pairs on 30 random features (seed 671163) boost 2.0 cut 1.0 | 2023 | macro ref_ndx_ret60 in (0.0509, inf] & btc vol 1d n=30 in (-inf, 0.0304]; btc sma_dist 1d  | 0.6368 / 0.4328 | 0.7286 / 0.8 (70) |
| miner rules K=10 +pairs on 30 random features (seed 671163) boost 2.0 cut 1.0 | 2024 | macro ref_ndx_ret60 in (0.0565, inf] & btc vol 1d n=30 in (-inf, 0.0291]; macro ref_ndx_re | 0.6615 / 0.4339 | 0.6012 / 0.5707 (1492) |
| miner rules K=10 +pairs on 30 random features (seed 671163) boost 2.0 cut 1.0 | 2025 | self roc 1d n=30 in (0.0833, inf] & self sma_dist 4h n=50 in (0.0166, inf]; self roc 1d n= | 0.6363 / 0.5528 | 0.545 / 0.4927 (556) |
| miner rules K=10 on 30 random features (seed 888979) boost 1.5 cut 0.5 | 2022 | self vol 4h n=24 in (-inf, 0.0161]; mkt_below sma_dist 1d n=50 in (-inf, 0.0] | 0.6097 / 0.3833 | 0.5341 / 0.5714 (249) |
| miner rules K=10 on 30 random features (seed 888979) boost 1.5 cut 0.5 | 2023 | macro ref_dxy_chg20 in (-0.0091, -0.0012]; btc sma_dist 1d n=200 in (-0.3084, -0.2245] | 0.6213 / 0.2865 | 0.7333 / 0.8 (75) |
| miner rules K=10 on 30 random features (seed 888979) boost 1.5 cut 0.5 | 2024 | macro ref_dxy_chg20 in (-0.0005, 0.0125]; macro ref_dxy_chg20 in (-0.0091, -0.0005] | 0.6227 / 0.3731 | 0.5955 / 0.7027 (1639) |
| miner rules K=10 on 30 random features (seed 888979) boost 1.5 cut 0.5 | 2025 | btc roc 1d n=30 in (0.1614, inf]; mkt_below sma_dist 1d n=50 in (-inf, 0.0769] | 0.6221 / 0.5286 | 0.4994 / 0.5285 (783) |
| miner rules K=3 on 8 random features (seed 498518) boost 2.0 cut 1.0 | 2022 | macro ref_dxy_chg20 in (-0.0097, -0.0018]; self roc 1d n=7 in (0.1025, inf] | 0.6442 / 0.4646 | 0.6911 / 0.4532 (123) |
| miner rules K=3 on 8 random features (seed 498518) boost 2.0 cut 1.0 | 2023 | macro ref_dxy_chg20 in (-0.0091, -0.0012]; macro ref_dxy_chg20 in (-0.0012, 0.0126] | 0.6601 / 0.4254 | 0.7857 / 0.6977 (42) |
| miner rules K=3 on 8 random features (seed 498518) boost 2.0 cut 1.0 | 2024 | macro ref_dxy_chg20 in (-0.0005, 0.0125]; macro ref_dxy_chg20 in (-0.0091, -0.0005] | 0.69 / 0.435 | 0.5849 / 0.6355 (1248) |
| miner rules K=3 on 8 random features (seed 498518) boost 2.0 cut 1.0 | 2025 | self roc 1d n=7 in (0.0695, inf]; self rsi 1d n=28 in (57.7469, inf] | 0.6641 / 0.5515 | 0.5011 / 0.518 (449) |
| miner rules K=10 on 30 random features (seed 184834) boost 2.0 cut 0.5 | 2022 | daily feargreed n=1 in (44.0, 75.0]; btc vol 1d n=30 in (-inf, 0.0297] | 0.5814 / 0.458 | 0.5081 / 0.6538 (248) |
| miner rules K=10 on 30 random features (seed 184834) boost 2.0 cut 0.5 | 2023 | cal dow in (-inf, 1.0]; btc roc 1d n=30 in (0.0977, inf] | 0.5878 / 0.4279 | 0.7381 / 1.0 (84) |
| miner rules K=10 on 30 random features (seed 184834) boost 2.0 cut 0.5 | 2024 | macro ref_ndx_ret60 in (0.1132, inf]; btc roc 1d n=30 in (0.0712, inf] | 0.6224 / 0.4123 | 0.5972 / 0.6333 (1646) |
| miner rules K=10 on 30 random features (seed 184834) boost 2.0 cut 0.5 | 2025 | btc roc 1d n=30 in (0.1614, inf]; mkt_below sma_dist 1d n=50 in (-inf, 0.0769] | 0.6058 / 0.5596 | 0.4804 / 0.5645 (891) |

### martingale: 126 tested, 69 improve the law; placebos 193, 85 improve (placebo best +0.116)

| gain | verdict | max DD (base) | years | idea |
|---|---|---|---|---|
| +0.136 | promising | 27% (24%) | 22:+65%/17% 23:+28%/7% 24:+78%/27% 25:+79%/22% | martingale win x2.0^k k<=2 cap 3.0 dd-gate 0.15 |
| +0.136 | promising | 27% (24%) | 22:+65%/17% 23:+28%/7% 24:+78%/27% 25:+79%/22% | martingale win x2.0^k k<=3 cap 3.0 dd-gate 0.15 |
| +0.132 | promising | 28% (24%) | 22:+65%/17% 23:+28%/7% 24:+89%/28% 25:+77%/22% | martingale win x2.0^k k<=2 cap 3.0 dd-gate None |
| +0.132 | promising | 28% (24%) | 22:+65%/17% 23:+28%/7% 24:+89%/28% 25:+77%/22% | martingale win x2.0^k k<=3 cap 3.0 dd-gate None |
| +0.129 | promising | 26% (24%) | 22:+62%/17% 23:+27%/7% 24:+97%/26% 25:+75%/22% | martingale win x1.5^k k<=3 cap 3.0 dd-gate 0.15 |
| +0.128 | promising | 27% (24%) | 22:+62%/17% 23:+27%/7% 24:+109%/27% 25:+75%/22% | martingale win x1.5^k k<=3 cap 3.0 dd-gate None |
| +0.104 | promising | 26% (24%) | 22:+63%/17% 23:+28%/7% 24:+72%/26% 25:+53%/24% | martingale win x2.0^k k<=2 cap 3.0 dd-gate 0.08 |
| +0.104 | promising | 26% (24%) | 22:+63%/17% 23:+28%/7% 24:+72%/26% 25:+53%/24% | martingale win x2.0^k k<=3 cap 3.0 dd-gate 0.08 |
| +0.102 | promising | 26% (24%) | 22:+61%/17% 23:+27%/7% 24:+85%/26% 25:+55%/24% | martingale win x1.5^k k<=3 cap 3.0 dd-gate 0.08 |
| +0.100 | promising | 26% (24%) | 22:+58%/17% 23:+25%/7% 24:+67%/26% 25:+59%/23% | martingale win x2.0^k k<=1 cap 2.0 dd-gate 0.15 |

### conviction: 104 tested, 20 improve the law; placebos 171, 96 improve (placebo best +0.074)

| gain | verdict | max DD (base) | years | idea |
|---|---|---|---|---|
| +0.020 | neutral | 24% (24%) | 22:+42%/16% 23:+17%/4% 24:+120%/23% 25:+43%/24% | conviction operator split q 0.75 boost 1.5 cut 0.75 |
| +0.018 | promising | 22% (24%) | 22:+43%/16% 23:+15%/4% 24:+109%/22% 25:+43%/22% | conviction trend split q 1.0 boost 1.5 cut 0.5 |
| +0.015 | promising | 24% (24%) | 22:+44%/16% 23:+17%/4% 24:+109%/23% 25:+41%/24% | conviction trend split q 1.0 boost 1.5 cut 0.75 |
| +0.012 | promising | 25% (24%) | 22:+46%/17% 23:+19%/5% 24:+103%/25% 25:+38%/25% | conviction trend top boost 1.5 |
| +0.012 | neutral | 22% (24%) | 22:+37%/15% 23:+16%/3% 24:+121%/22% 25:+44%/22% | conviction operator split q 0.75 boost 1.5 cut 0.5 |
| +0.011 | neutral | 23% (24%) | 22:+42%/16% 23:+17%/4% 24:+100%/23% 25:+40%/22% | conviction multi_tf linear 0.75..1.25 |
| +0.010 | neutral | 24% (24%) | 22:+39%/17% 23:+16%/3% 24:+124%/24% 25:+43%/24% | conviction operator split q 0.75 boost 2.0 cut 0.5 |
| +0.008 | neutral | 22% (24%) | 22:+41%/15% 23:+15%/4% 24:+109%/22% 25:+42%/21% | conviction multi_tf linear 0.5..1.5 |
| +0.008 | promising | 24% (24%) | 22:+46%/16% 23:+15%/4% 24:+115%/24% 25:+40%/24% | conviction trend split q 1.0 boost 2.0 cut 0.5 |
| +0.008 | neutral | 22% (24%) | 22:+41%/15% 23:+16%/4% 24:+104%/22% 25:+40%/21% | conviction multi_tf split q 1.0 boost 1.5 cut 0.5 |

### miner: 44 tested, 16 improve the law; placebos 88, 36 improve (placebo best +0.064)

| gain | verdict | max DD (base) | years | idea |
|---|---|---|---|---|
| +0.050 | promising | 32% (24%) | 22:+39%/17% 23:+27%/7% 24:+92%/32% 25:+50%/20% | miner rules K=10 boost 2.0 cut 0.5 |
| +0.042 | promising | 32% (24%) | 22:+45%/17% 23:+28%/7% 24:+92%/32% 25:+43%/24% | miner rules K=10 boost 2.0 cut 1.0 |
| +0.041 | promising | 28% (24%) | 22:+38%/17% 23:+25%/6% 24:+91%/28% 25:+48%/19% | miner rules K=10 boost 1.5 cut 0.5 |
| +0.039 | promising | 28% (24%) | 22:+45%/17% 23:+25%/6% 24:+92%/28% 25:+42%/24% | miner rules K=10 boost 1.5 cut 1.0 |
| +0.022 | promising | 24% (24%) | 22:+43%/16% 23:+20%/5% 24:+90%/24% 25:+41%/23% | miner rules K=1 boost 1.5 cut 1.0 |
| +0.020 | neutral | 30% (24%) | 22:+43%/17% 23:+32%/7% 24:+108%/27% 25:+32%/30% | miner ML top 30% boost 2.0 cut 0.5 |
| +0.018 | promising | 28% (24%) | 22:+45%/16% 23:+21%/5% 24:+90%/28% 25:+41%/25% | miner rules K=10 +pairs boost 1.5 cut 1.0 |
| +0.016 | neutral | 27% (24%) | 22:+43%/17% 23:+21%/6% 24:+78%/27% 25:+39%/24% | miner rules K=3 boost 1.5 cut 1.0 |
| +0.013 | promising | 27% (24%) | 22:+43%/17% 23:+20%/5% 24:+84%/27% 25:+41%/24% | miner rules K=3 +pairs boost 1.5 cut 1.0 |
| +0.013 | neutral | 27% (24%) | 22:+43%/17% 23:+19%/5% 24:+67%/27% 25:+41%/23% | miner rules K=1 +pairs boost 1.5 cut 1.0 |

### miner_random: 456 tested, 221 improve the law; placebos 456, 174 improve (placebo best +0.088)

| gain | verdict | max DD (base) | years | idea |
|---|---|---|---|---|
| +0.089 | promising | 31% (24%) | 22:+51%/15% 23:+28%/7% 24:+91%/31% 25:+62%/22% | miner rules K=10 on 20 random features (seed 834803) boost 2.0 cut 0.5 |
| +0.082 | promising | 31% (24%) | 22:+52%/15% 23:+28%/7% 24:+95%/31% 25:+53%/22% | miner rules K=10 on 30 random features (seed 909497) boost 2.0 cut 0.5 |
| +0.076 | promising | 31% (24%) | 22:+49%/16% 23:+27%/7% 24:+97%/31% 25:+55%/24% | miner rules K=10 +pairs on 30 random features (seed 671163) boost 2.0 cut 1.0 |
| +0.075 | promising | 28% (24%) | 22:+49%/16% 23:+25%/7% 24:+83%/28% 25:+55%/20% | miner rules K=10 on 30 random features (seed 888979) boost 1.5 cut 0.5 |
| +0.074 | promising | 31% (24%) | 22:+53%/16% 23:+26%/5% 24:+65%/31% 25:+51%/24% | miner rules K=3 on 8 random features (seed 498518) boost 2.0 cut 1.0 |
| +0.071 | promising | 32% (24%) | 22:+44%/17% 23:+28%/7% 24:+92%/32% 25:+60%/24% | miner rules K=10 on 30 random features (seed 184834) boost 2.0 cut 0.5 |
| +0.066 | promising | 27% (24%) | 22:+43%/16% 23:+26%/7% 24:+76%/27% 25:+50%/24% | miner rules K=3 on 20 random features (seed 89490) boost 2.0 cut 1.0 |
| +0.065 | promising | 31% (24%) | 22:+57%/17% 23:+28%/7% 24:+97%/31% 25:+45%/24% | miner rules K=10 on 8 random features (seed 806280) boost 2.0 cut 1.0 |
| +0.064 | promising | 26% (24%) | 22:+43%/15% 23:+23%/7% 24:+76%/26% 25:+58%/18% | miner rules K=3 on 12 random features (seed 363092) boost 1.5 cut 0.5 |
| +0.063 | promising | 26% (24%) | 22:+41%/20% 23:+25%/4% 24:+88%/26% 25:+53%/21% | miner rules K=10 on 8 random features (seed 454141) boost 1.5 cut 0.5 |

### Moving averages 2-300: gain by period bucket (best n in bucket)

| source tf | 2-31 | 32-61 | 62-91 | 92-121 | 122-151 | 152-181 | 182-211 | 212-241 | 242-271 | 272-301 |
|---|---|---|---|---|---|---|---|---|---|---|
| btc 1d | +0.003 (n=4) | -0.033 (n=33) | -0.086 (n=62) | -0.097 (n=121) | -0.097 (n=124) | -0.129 (n=158) | -0.087 (n=192) | -0.087 (n=212) | -0.076 (n=260) | -0.103 (n=290) |
| btc 4h | +0.006 (n=2) | -0.032 (n=43) | -0.008 (n=67) | -0.037 (n=92) | -0.026 (n=142) | -0.051 (n=160) | -0.074 (n=205) | -0.078 (n=220) | -0.082 (n=242) | -0.097 (n=274) |
| mkt_below 1d | +0.000 (n=2) | +0.000 (n=32) | -0.022 (n=90) | -0.057 (n=92) | -0.059 (n=122) | -0.059 (n=180) | +0.000 (n=204) | +0.004 (n=241) | +0.005 (n=251) | +0.000 (n=272) |
| mkt_below 4h | -0.004 (n=2) | -0.085 (n=32) | -0.099 (n=90) | -0.087 (n=107) | +0.000 (n=148) | +0.000 (n=152) | -0.104 (n=183) | +0.000 (n=214) | +0.000 (n=242) | -0.024 (n=282) |
| self 1d | -0.060 (n=6) | -0.099 (n=36) | -0.035 (n=90) | -0.018 (n=100) | -0.147 (n=143) | -0.127 (n=178) | -0.121 (n=189) | -0.105 (n=241) | +0.051 (n=268) | +0.064 (n=298) |
| self 1h | -0.023 (n=3) | -0.069 (n=37) | -0.081 (n=72) | -0.072 (n=105) | -0.089 (n=148) | -0.096 (n=165) | -0.078 (n=210) | -0.085 (n=223) | -0.102 (n=258) | -0.107 (n=297) |
| self 4h | -0.041 (n=6) | -0.092 (n=33) | -0.093 (n=74) | -0.097 (n=92) | -0.109 (n=123) | -0.108 (n=153) | -0.093 (n=200) | -0.096 (n=241) | -0.126 (n=266) | -0.128 (n=273) |

Period 37 (the operator's hunch): self 1d gain -0.100 (hurts); self 4h gain -0.102 (hurts); self 1h gain -0.069 (hurts); btc 1d gain -0.150 (hurts); btc 4h gain -0.133 (hurts); mkt_below 1d gain +0.000 (silent); mkt_below 4h gain -0.087 (hurts)

### Plateaus: five neighbouring periods that ALL help (smallest gain of the five)

| min gain | feature | periods |
|---|---|---|
| +0.037 | self sma_dist 1d | 266-270 |
| +0.026 | self kurt 1h | 2-10 |
| +0.024 | rank ema_dist 4h | 2-10 |
| +0.017 | self vr 1d | 37-60 |
| +0.016 | self efficiency 1h | 30-50 |
| +0.015 | rel ema_dist 1h | 75-144 |
| +0.001 | rank roc 1h | 5-15 |

### The ten ideas that help 2024 most (and what they do to the other years)

| 2024 ret/DD | all years | gain over 22-25 | idea |
|---|---|---|---|
| +149.7% / 19% | 22:+25%/17% 23:+10%/3% 24:+150%/19% 25:+5%/22% | -0.163 | mkt_disp vol 1h n=75 |
| +142.1% / 20% | 22:+24%/15% 23:+9%/3% 24:+142%/20% 25:+23%/23% | -0.106 | rank rsi 2h n=61 OR btc efficiency 3d n=31 OR btc macd 1h a=5 b=13 sig=5 |
| +139.2% / 17% | 22:+18%/18% 23:+23%/3% 24:+139%/17% 25:+20%/18% | -0.067 | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=339 |
| +140.2% / 24% | 22:+42%/17% 23:+14%/4% 24:+140%/24% 25:+29%/28% | -0.051 | conviction trend split q 0.75 boost 2.0 cut 0.5 |
| +134.2% / 24% | 22:+40%/16% 23:+12%/4% 24:+134%/24% 25:+42%/23% | -0.007 | conviction trend linear 0.25..1.75 |
| +132.3% / 21% | 22:+37%/15% 23:+14%/3% 24:+132%/21% 25:+40%/20% | -0.003 | miner rules K=3 on 12 random features (seed 584986) boost 2.0 cut 0.5 |
| +132.7% / 23% | 22:+38%/17% 23:+16%/3% 24:+133%/23% 25:+48%/25% | +0.017 | miner rules K=3 +pairs on 8 random features (seed 561464) boost 2.0 cut 0.5 |
| +131.8% / 22% | 22:+43%/15% 23:+8%/4% 24:+132%/22% 25:+33%/23% | -0.042 | self skew 12h n=23 |
| +130.5% / 23% | 22:+34%/15% 23:+14%/3% 24:+130%/23% 25:+42%/21% | -0.009 | conviction operator linear 0.25..1.75 |
| +127.3% / 18% | 22:+20%/16% 23:+10%/2% 24:+127%/18% 25:+63%/13% | -0.001 | rank rsi 2h n=61 OR rank pos 1w n=23 |

## Universe: pit

Baseline (release 34, no validator): law +0.072, max DD 32%, win rate 53.0%.

| | tested | win | promising | neutral | hurts | silent |
|---|---|---|---|---|---|---|
| real ideas | 15643 | 0 | 348 | 3253 | 9944 | 2098 |
| placebo (time-shifted) | 5020 | 0 | 54 | 1087 | 3425 | 454 |

**Evidence test (primary ideas only):** 93 / 12052 = 0.77% win-or-promising vs placebo 1.18%, z = -4.2. Derived ideas (combos, half, band, neighbours of leaders: 255 / 1493) are built from leaders picked on the SAME years they are graded on, so their rate is selection bias, not evidence; they are listed for follow-up only. A z above +3 would be worth the operator's time.

Chance rate: 0.0% of active placebo ideas 'win' and 1.2% are win-or-promising; real ideas: 0.0% and 2.6%. A family is only interesting where it clearly beats the placebo.

| family | tested | active | win % | win-or-promising % | best gain | best idea |
|---|---|---|---|---|---|---|
| random_combo | 1065 | 1065 | 0.0% | 15.6% | +0.193 | rank roc 1d n=379 OR mkt_disp vol 15m n=242 |
| combo2 | 214 | 214 | 0.0% | 12.1% | +0.170 | rank kurt 1h n=7 OR mkt_disp vol 15m n=242 |
| random | 5588 | 4667 | 0.0% | 1.1% | +0.155 | mkt_disp autocorr 2h n=423 |
| robust | 159 | 159 | 0.0% | 39.0% | +0.151 | rank kurt 1h n=8 OR mkt_disp autocorr 2h n=377 |
| indicators | 2184 | 1928 | 0.0% | 1.0% | +0.135 | btc kurt 4h n=144 |
| cross_section | 1596 | 1315 | 0.0% | 1.2% | +0.127 | mkt_disp vol 4h n=8 |
| band | 39 | 16 | 0.0% | 0.0% | +0.120 | mkt_disp autocorr 2h n=419 |
| ma_cross | 612 | 477 | 0.0% | 0.0% | +0.116 | btc ma_cross 1d a=30 b=89 |
| ma_scan | 2093 | 1727 | 0.0% | 0.0% | +0.093 | mkt_below sma_dist 1d n=23 |
| rsi | 498 | 416 | 0.0% | 0.0% | +0.076 | self rsi 4h n=110 |
| macd | 783 | 769 | 0.0% | 0.0% | +0.064 | mkt_below macd 1d a=3 b=89 sig=13 |
| miner_random | 456 | 456 | 0.0% | 0.0% | +0.043 | miner rules K=10 +pairs on 30 random features (seed 512563) boost 1.5 cut 0.5 |
| conviction | 104 | 104 | 0.0% | 5.8% | +0.021 | conviction with_model linear 0.25..1.75 |
| miner | 44 | 32 | 0.0% | 0.0% | +0.016 | miner rules K=3 +pairs boost 2.0 cut 1.0 |
| daily | 21 | 16 | 0.0% | 0.0% | +0.014 | daily stablecoin_supply n=7 chg |
| half | 39 | 39 | 0.0% | 2.6% | +0.009 | mkt_mean ema_dist 1d n=10 |
| macro | 8 | 7 | 0.0% | 0.0% | +0.007 | macro ref_dxy_chg20 |
| data | 1 | 1 | 0.0% | 0.0% | +0.007 | breadth |
| martingale | 126 | 126 | 0.0% | 0.0% | +0.006 | martingale loss x1.5^k k<=1 cap 2.0 dd-gate 0.15 |
| funding | 5 | 5 | 0.0% | 0.0% | +0.004 | funding n=21 |
| ml | 3 | 1 | 0.0% | 0.0% | +0.000 | learned validator on bank 'core' |
| calendar | 3 | 3 | 0.0% | 0.0% | -0.004 | cal hour |
| coin | 1 | 1 | 0.0% | 0.0% | -0.032 | coin |
| model | 1 | 1 | 0.0% | 0.0% | -0.054 | model |

### Best 25 (win or promising)

| gain | verdict | sig yrs | win rate | max DD | years | idea |
|---|---|---|---|---|---|---|
| +0.193 | promising | 2/4 | 54.1% (base 53.0%) | 15% | 22:+0%/0% 23:+9%/2% 24:+115%/15% 25:+104%/15% | rank roc 1d n=379 OR mkt_disp vol 15m n=242 |
| +0.185 | promising | 1/4 | 59.5% (base 53.0%) | 12% | 22:+0%/0% 23:+13%/2% 24:+79%/12% 25:+90%/8% | rank autocorr 8h n=97 OR rank vr 4h n=37 OR mkt_disp autocorr 2h n=423 |
| +0.184 | promising | 1/4 | 57.0% (base 53.0%) | 14% | 22:+0%/0% 23:+11%/3% 24:+88%/14% 25:+89%/10% | mkt_disp autocorr 2h n=423 OR rank roc 4h n=17 |
| +0.172 | promising | 1/4 | 57.1% (base 53.0%) | 13% | 22:+0%/0% 23:+10%/3% 24:+77%/13% 25:+87%/10% | rel efficiency 15m n=41 OR mkt_disp autocorr 2h n=423 |
| +0.170 | promising | 1/4 | 57.2% (base 53.0%) | 16% | 22:+0%/0% 23:+11%/3% 24:+79%/16% 25:+84%/10% | rank sma_slope 1h n=61 OR mkt_disp autocorr 2h n=423 |
| +0.170 | promising | 2/4 | 52.4% (base 53.0%) | 16% | 22:+0%/0% 23:+11%/3% 24:+110%/14% 25:+79%/16% | rank kurt 1h n=7 OR mkt_disp vol 15m n=242 |
| +0.168 | promising | 1/4 | 59.7% (base 53.0%) | 15% | 22:+0%/0% 23:+11%/3% 24:+80%/15% 25:+75%/10% | rel ema_dist 15m n=11 OR mkt_disp autocorr 2h n=423 OR rank roc 1h n=75 |
| +0.168 | promising | 1/4 | 59.4% (base 53.0%) | 15% | 22:+0%/0% 23:+9%/3% 24:+81%/15% 25:+88%/11% | mkt_disp autocorr 2h n=423 OR rank rsi 1h n=61 OR rel pos 2h n=41 |
| +0.167 | promising | 1/4 | 57.6% (base 53.0%) | 17% | 22:+0%/0% 23:+11%/3% 24:+77%/17% 25:+85%/10% | mkt_disp autocorr 2h n=423 OR rank sma_slope 15m n=233 |
| +0.166 | promising | 1/4 | 56.4% (base 53.0%) | 16% | 22:+0%/0% 23:+9%/3% 24:+79%/16% 25:+89%/10% | mkt_disp autocorr 2h n=423 OR rank sma_slope 4h n=10 |
| +0.159 | promising | 1/4 | 59.4% (base 53.0%) | 15% | 22:+0%/0% 23:+9%/2% 24:+71%/15% 25:+86%/12% | mkt_disp autocorr 2h n=423 OR rank rsi 2h n=64 |
| +0.158 | promising | 1/4 | 56.8% (base 53.0%) | 12% | 22:+0%/0% 23:+13%/2% 24:+53%/12% 25:+105%/10% | rank vr 30m n=47 OR mkt_disp autocorr 2h n=419 |
| +0.156 | promising | 1/4 | 56.2% (base 53.0%) | 16% | 22:+0%/0% 23:+9%/2% 24:+112%/15% 25:+69%/16% | rank rsi 2h n=61 OR mkt_disp vol 15m n=242 |
| +0.151 | promising | 0/4 | 57.8% (base 53.0%) | 16% | 22:+0%/0% 23:+12%/2% 24:+58%/16% 25:+87%/12% | mkt_disp autocorr 2h n=423 OR rank rsi 2h n=47 OR rank kurt 1h n=7 |
| +0.151 | promising | 2/4 | 52.3% (base 53.0%) | 17% | 22:+0%/0% 23:+10%/3% 24:+63%/14% 25:+78%/17% | rank kurt 1h n=8 OR mkt_disp autocorr 2h n=377 |
| +0.149 | promising | 1/4 | 57.8% (base 53.0%) | 15% | 22:+0%/0% 23:+9%/2% 24:+61%/15% 25:+82%/12% | rank rsi 2h n=64 OR mkt_disp autocorr 2h n=419 |
| +0.148 | promising | 1/4 | 57.7% (base 53.0%) | 16% | 22:+0%/0% 23:+12%/2% 24:+57%/16% 25:+78%/12% | mkt_disp autocorr 2h n=419 OR rank rsi 2h n=64 OR rank kurt 1h n=7 |
| +0.147 | promising | 1/4 | 51.0% (base 53.0%) | 16% | 22:+0%/0% 23:+11%/3% 24:+57%/16% 25:+79%/16% | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=377 |
| +0.147 | promising | 1/4 | 55.6% (base 53.0%) | 14% | 22:+0%/0% 23:+10%/3% 24:+54%/14% 25:+70%/11% | rank kurt 1h n=8 OR mkt_disp autocorr 2h n=415 |
| +0.147 | promising | 0/4 | 55.9% (base 53.0%) | 15% | 22:+0%/0% 23:+11%/3% 24:+53%/15% 25:+83%/11% | rank zscore 2h n=261 OR rank kurt 1h n=7 OR mkt_disp autocorr 2h n=423 |
| +0.146 | promising | 2/4 | 50.8% (base 53.0%) | 17% | 22:+0%/0% 23:+10%/3% 24:+63%/17% 25:+71%/17% | rank kurt 30m n=7 OR mkt_disp autocorr 2h n=377 |
| +0.145 | promising | 1/4 | 57.9% (base 53.0%) | 18% | 22:+0%/0% 23:+9%/2% 24:+63%/18% 25:+65%/17% | rank rsi 2h n=64 OR mkt_mean kurt 4h n=37 |
| +0.145 | promising | 0/4 | 61.9% (base 53.0%) | 16% | 22:+0%/0% 23:+11%/3% 24:+55%/16% 25:+85%/12% | rank vol 3d n=120 OR rank sma_slope 15m n=233 OR mkt_disp autocorr 2h n=423 |
| +0.144 | promising | 1/4 | 55.8% (base 53.0%) | 14% | 22:+0%/0% 23:+10%/3% 24:+50%/14% 25:+81%/10% | rank kurt 1h n=8 OR mkt_disp autocorr 2h n=411 |
| +0.142 | promising | 1/4 | 56.4% (base 53.0%) | 15% | 22:+0%/0% 23:+9%/2% 24:+53%/15% 25:+80%/10% | rank kurt 1h n=5 OR mkt_disp autocorr 2h n=411 |

### miner: do criteria learned on past trades hold the next year?

Win rate of the champion's trades inside the learned criteria vs outside, in the training years and in the year after (the same trades the baseline took).

| idea | year | criteria found | train win in / out | next-year win in / out (n in) |
|---|---|---|---|---|
| miner rules K=10 +pairs on 30 random features (seed 512563) boost 1.5 cut 0.5 | 2022 | macro ref_curve in (-inf, 0.45] & cal dow in (-inf, 2.0]; macro ref_y10_chg20 in (-inf, -0 | 0.6838 / 0.3838 | None / None (None) |
| miner rules K=10 +pairs on 30 random features (seed 512563) boost 1.5 cut 0.5 | 2023 | macro ref_curve in (-inf, 0.45] & cal dow in (-inf, 2.0]; macro ref_y10_chg20 in (-inf, -0 | 0.6838 / 0.3838 | 0.6667 / 0.8571 (3) |
| miner rules K=10 +pairs on 30 random features (seed 512563) boost 1.5 cut 0.5 | 2024 | macro ref_y10_chg20 in (-inf, -0.54] & cal dow in (-inf, 2.0]; macro ref_curve in (0.38, 1 | 0.7162 / 0.3277 | 0.6495 / 0.506 (736) |
| miner rules K=10 +pairs on 30 random features (seed 512563) boost 1.5 cut 0.5 | 2025 | macro ref_vix_chg20 in (-inf, -0.0352] & macro ref_dxy_chg20 in (0.0078, inf]; macro ref_d | 0.6667 / 0.4075 | 0.4181 / 0.5133 (653) |
| miner rules K=10 +pairs on 20 random features (seed 261765) boost 1.5 cut 0.5 | 2022 | mkt_below sma_dist 1d n=200 in (0.8571, inf] & self vol 1d n=30 in (0.0658, 0.1039]; self  | 0.6215 / 0.2277 | None / None (None) |
| miner rules K=10 +pairs on 20 random features (seed 261765) boost 1.5 cut 0.5 | 2023 | mkt_below sma_dist 1d n=200 in (0.8571, inf] & self vol 1d n=30 in (0.0658, 0.1039]; self  | 0.6215 / 0.2277 | 0.8 / None (10) |
| miner rules K=10 +pairs on 20 random features (seed 261765) boost 1.5 cut 0.5 | 2024 | macro ref_y10_chg20 in (0.01, inf] & self vol 4h n=24 in (-inf, 0.0254]; macro ref_y10_chg | 0.6404 / 0.2787 | 0.6273 / 0.5034 (880) |
| miner rules K=10 +pairs on 20 random features (seed 261765) boost 1.5 cut 0.5 | 2025 | daily feargreed n=1 in (73.0, inf] & self vol 4h n=24 in (0.0228, inf]; self dd 1d n=90 in | 0.6579 / 0.4796 | 0.4224 / 0.4851 (580) |
| miner rules K=10 +pairs on 30 random features (seed 355465) boost 1.5 cut 0.5 | 2022 | macro ref_dxy_chg20 in (-0.0024, 0.0143] & btc rsi 1d n=14 in (-inf, 32.3455]; macro ref_d | 0.625 / 0.4154 | None / None (None) |
| miner rules K=10 +pairs on 30 random features (seed 355465) boost 1.5 cut 0.5 | 2023 | macro ref_dxy_chg20 in (-0.0024, 0.0143] & btc rsi 1d n=14 in (-inf, 32.3455]; macro ref_d | 0.625 / 0.4154 | 0.6667 / 0.8571 (3) |
| miner rules K=10 +pairs on 30 random features (seed 355465) boost 1.5 cut 0.5 | 2024 | macro ref_dxy_chg20 in (-0.0029, 0.0143] & self sma_dist 1d n=200 in (-inf, -0.2434]; macr | 0.6987 / 0.3254 | 0.625 / 0.523 (816) |
| miner rules K=10 +pairs on 30 random features (seed 355465) boost 1.5 cut 0.5 | 2025 | macro ref_dxy_chg20 in (0.0055, inf] & daily oi_BTCUSDT n=7 chg in (-inf, -0.0268]; macro  | 0.6646 / 0.4797 | 0.4502 / 0.4432 (291) |
| miner rules K=3 on 20 random features (seed 742956) boost 2.0 cut 1.0 | 2022 | macro ref_y10_chg20 in (-0.77, -0.454]; self sma_dist 1d n=200 in (-inf, -0.3282] | 0.5726 / 0.4495 | None / None (None) |
| miner rules K=3 on 20 random features (seed 742956) boost 2.0 cut 1.0 | 2023 | macro ref_y10_chg20 in (-0.77, -0.454]; self sma_dist 1d n=200 in (-inf, -0.3282] | 0.5726 / 0.4495 | None / 0.8 (0) |
| miner rules K=3 on 20 random features (seed 742956) boost 2.0 cut 1.0 | 2024 | self sma_dist 1d n=200 in (-inf, -0.3282]; macro ref_y10_chg20 in (0.1, inf] | 0.6441 / 0.4251 | 0.6145 / 0.5676 (524) |
| miner rules K=3 on 20 random features (seed 742956) boost 2.0 cut 1.0 | 2025 | btc sma_dist 1d n=50 in (0.175, inf]; self dd 1d n=90 in (-0.0725, inf] | 0.6829 / 0.4985 | 0.3844 / 0.501 (437) |
| miner rules K=3 +pairs on 30 random features (seed 860922) boost 2.0 cut 1.0 | 2022 | macro ref_dxy_chg20 in (-0.0024, 0.0143] & self sma_dist 1d n=200 in (-inf, -0.2495]; macr | 0.6078 / 0.4735 | None / None (None) |
| miner rules K=3 +pairs on 30 random features (seed 860922) boost 2.0 cut 1.0 | 2023 | macro ref_dxy_chg20 in (-0.0024, 0.0143] & self sma_dist 1d n=200 in (-inf, -0.2495]; macr | 0.6078 / 0.4735 | 1.0 / 0.75 (2) |
| miner rules K=3 +pairs on 30 random features (seed 860922) boost 2.0 cut 1.0 | 2024 | macro ref_curve in (0.38, 1.0] & macro ref_dxy_chg20 in (-0.0029, 0.0143]; macro ref_dxy_c | 0.6824 / 0.4417 | 0.6044 / 0.5834 (182) |
| miner rules K=3 +pairs on 30 random features (seed 860922) boost 2.0 cut 1.0 | 2025 | macro ref_vix_chg20 in (-inf, -0.0352] & macro ref_dxy_chg20 in (0.0078, inf]; macro ref_v | 0.7161 / 0.4973 | 0.4174 / 0.4542 (218) |
| miner rules K=10 on 8 random features (seed 511821) boost 2.0 cut 1.0 | 2022 | macro ref_curve in (0.956, 1.26]; macro ref_curve in (0.32, 0.46] | 0.5463 / 0.4 | None / None (None) |
| miner rules K=10 on 8 random features (seed 511821) boost 2.0 cut 1.0 | 2023 | macro ref_curve in (0.956, 1.26]; macro ref_curve in (0.32, 0.46] | 0.5463 / 0.4 | None / 0.8 (0) |
| miner rules K=10 on 8 random features (seed 511821) boost 2.0 cut 1.0 | 2024 | macro ref_curve in (0.92, 1.26]; btc vol 1d n=30 in (0.1009, inf] | 0.5507 / 0.4237 | 0.5772 / 0.5906 (421) |
| miner rules K=10 on 8 random features (seed 511821) boost 2.0 cut 1.0 | 2025 | self dd 1d n=90 in (-0.0725, inf]; self pos 1d n=100 in (0.8438, inf] | 0.6037 / 0.4431 | 0.46 / 0.4071 (663) |

### martingale: 126 tested, 17 improve the law; placebos 193, 36 improve (placebo best +0.029)

| gain | verdict | max DD (base) | years | idea |
|---|---|---|---|---|
| +0.006 | neutral | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+14%/32% 25:+81%/17% | martingale loss x1.5^k k<=1 cap 2.0 dd-gate 0.15 |
| +0.006 | neutral | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+14%/32% 25:+81%/17% | martingale loss x1.5^k k<=1 cap 3.0 dd-gate 0.15 |
| +0.004 | neutral | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+13%/32% 25:+85%/17% | martingale loss x1.5^k k<=2 cap 2.0 dd-gate 0.15 |
| +0.004 | neutral | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+13%/32% 25:+85%/17% | martingale loss x1.5^k k<=3 cap 2.0 dd-gate 0.15 |
| +0.004 | neutral | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+13%/32% 25:+74%/21% | martingale loss x1.5^k k<=3 cap 3.0 dd-gate 0.15 |
| +0.003 | neutral | 32% (32%) | 22:+0%/0% 23:+7%/3% 24:+16%/32% 25:+70%/18% | martingale win x1.25^k k<=1 cap 2.0 dd-gate None |
| +0.003 | neutral | 32% (32%) | 22:+0%/0% 23:+7%/3% 24:+16%/32% 25:+70%/18% | martingale win x1.25^k k<=1 cap 3.0 dd-gate None |
| +0.001 | neutral | 34% (32%) | 22:+0%/0% 23:+6%/3% 24:+17%/34% 25:+62%/19% | martingale win x1.5^k k<=2 cap 3.0 dd-gate None |
| +0.001 | neutral | 33% (32%) | 22:+0%/0% 23:+9%/3% 24:+13%/33% 25:+85%/16% | martingale loss x1.25^k k<=3 cap 2.0 dd-gate 0.15 |
| +0.001 | neutral | 33% (32%) | 22:+0%/0% 23:+9%/3% 24:+13%/33% 25:+85%/16% | martingale loss x1.25^k k<=3 cap 3.0 dd-gate 0.15 |

### conviction: 104 tested, 64 improve the law; placebos 171, 42 improve (placebo best +0.020)

| gain | verdict | max DD (base) | years | idea |
|---|---|---|---|---|
| +0.021 | neutral | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+20%/32% 25:+63%/17% | conviction with_model linear 0.25..1.75 |
| +0.021 | neutral | 33% (32%) | 22:+0%/0% 23:+9%/3% 24:+21%/33% 25:+60%/18% | conviction with_model split q 0.75 boost 1.5 cut 0.5 |
| +0.021 | neutral | 31% (32%) | 22:+0%/0% 23:+9%/3% 24:+19%/31% 25:+71%/17% | conviction with_model split q 1.0 boost 2.0 cut 0.5 |
| +0.020 | neutral | 31% (32%) | 22:+0%/0% 23:+9%/3% 24:+19%/31% 25:+71%/17% | conviction with_model split q 1.0 boost 1.5 cut 0.5 |
| +0.018 | neutral | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+19%/32% 25:+68%/17% | conviction with_model top boost 2.0 |
| +0.017 | neutral | 33% (32%) | 22:+0%/0% 23:+9%/3% 24:+20%/33% 25:+55%/21% | conviction trend_rsi_btc top boost 2.0 |
| +0.016 | promising | 31% (32%) | 22:+0%/0% 23:+9%/3% 24:+18%/31% 25:+69%/17% | conviction with_model split q 1.0 boost 1.5 cut 0.75 |
| +0.016 | neutral | 34% (32%) | 22:+0%/0% 23:+9%/3% 24:+20%/34% 25:+55%/21% | conviction operator top boost 2.0 |
| +0.015 | promising | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+18%/32% 25:+67%/16% | conviction with_model linear 0.5..1.5 |
| +0.013 | neutral | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+17%/32% 25:+68%/17% | conviction with_model top boost 1.5 |

### miner: 44 tested, 4 improve the law; placebos 88, 10 improve (placebo best +0.013)

| gain | verdict | max DD (base) | years | idea |
|---|---|---|---|---|
| +0.016 | neutral | 30% (32%) | 22:+0%/0% 23:+9%/3% 24:+17%/30% 25:+64%/18% | miner rules K=3 +pairs boost 2.0 cut 1.0 |
| +0.007 | neutral | 31% (32%) | 22:+0%/0% 23:+9%/3% 24:+14%/31% 25:+68%/17% | miner rules K=3 +pairs boost 1.5 cut 1.0 |
| +0.006 | neutral | 33% (32%) | 22:+0%/0% 23:+6%/3% 24:+18%/33% 25:+66%/17% | miner rules K=30 +pairs boost 1.5 cut 0.5 |
| +0.000 | neutral | 33% (32%) | 22:+0%/0% 23:+9%/3% 24:+14%/33% 25:+69%/19% | miner rules K=10 +pairs boost 2.0 cut 1.0 |
| +0.000 | neutral | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+12%/32% 25:+67%/17% | miner rules K=1 boost 1.5 cut 1.0 |
| +0.000 | neutral | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+12%/32% 25:+68%/17% | miner rules K=1 boost 2.0 cut 1.0 |
| +0.000 | neutral | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+12%/32% 25:+65%/17% | miner rules K=1 +pairs boost 1.5 cut 1.0 |
| +0.000 | neutral | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+12%/32% 25:+60%/17% | miner rules K=1 +pairs boost 2.0 cut 1.0 |
| +0.000 | silent | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+12%/32% 25:+64%/17% | miner ML top 10% boost 1.5 cut 1.0 |
| +0.000 | silent | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+12%/32% 25:+64%/17% | miner ML top 10% boost 2.0 cut 1.0 |

### miner_random: 456 tested, 110 improve the law; placebos 456, 104 improve (placebo best +0.027)

| gain | verdict | max DD (base) | years | idea |
|---|---|---|---|---|
| +0.043 | neutral | 29% (32%) | 22:+0%/0% 23:+6%/2% 24:+30%/29% 25:+60%/17% | miner rules K=10 +pairs on 30 random features (seed 512563) boost 1.5 cut 0.5 |
| +0.033 | neutral | 30% (32%) | 22:+0%/0% 23:+6%/3% 24:+26%/30% 25:+53%/17% | miner rules K=10 +pairs on 20 random features (seed 261765) boost 1.5 cut 0.5 |
| +0.031 | neutral | 28% (32%) | 22:+0%/0% 23:+6%/2% 24:+35%/28% 25:+37%/16% | miner rules K=10 +pairs on 30 random features (seed 355465) boost 1.5 cut 0.5 |
| +0.031 | neutral | 32% (32%) | 22:+0%/0% 23:+9%/3% 24:+24%/32% 25:+70%/19% | miner rules K=3 on 20 random features (seed 742956) boost 2.0 cut 1.0 |
| +0.021 | neutral | 31% (32%) | 22:+0%/0% 23:+9%/3% 24:+19%/31% 25:+67%/17% | miner rules K=3 +pairs on 30 random features (seed 860922) boost 2.0 cut 1.0 |
| +0.019 | neutral | 31% (32%) | 22:+0%/0% 23:+9%/3% 24:+18%/31% 25:+75%/22% | miner rules K=10 on 8 random features (seed 511821) boost 2.0 cut 1.0 |
| +0.019 | neutral | 31% (32%) | 22:+0%/0% 23:+6%/3% 24:+22%/31% 25:+67%/17% | miner rules K=10 +pairs on 12 random features (seed 153838) boost 1.5 cut 1.0 |
| +0.018 | neutral | 31% (32%) | 22:+0%/0% 23:+9%/3% 24:+18%/31% 25:+80%/17% | miner rules K=10 on 8 random features (seed 639136) boost 1.5 cut 1.0 |
| +0.017 | neutral | 29% (32%) | 22:+0%/0% 23:+6%/2% 24:+19%/29% 25:+66%/21% | miner rules K=10 on 30 random features (seed 909497) boost 2.0 cut 0.5 |
| +0.016 | neutral | 33% (32%) | 22:+0%/0% 23:+9%/3% 24:+19%/33% 25:+96%/17% | miner rules K=10 +pairs on 8 random features (seed 507052) boost 2.0 cut 1.0 |

### Moving averages 2-300: gain by period bucket (best n in bucket)

| source tf | 2-31 | 32-61 | 62-91 | 92-121 | 122-151 | 152-181 | 182-211 | 212-241 | 242-271 | 272-301 |
|---|---|---|---|---|---|---|---|---|---|---|
| btc 1d | +0.056 (n=3) | +0.000 (n=32) | +0.000 (n=62) | +0.000 (n=92) | -0.013 (n=122) | -0.016 (n=161) | -0.004 (n=204) | +0.000 (n=216) | +0.000 (n=242) | +0.000 (n=272) |
| btc 4h | +0.007 (n=2) | -0.089 (n=49) | -0.113 (n=64) | +0.000 (n=113) | -0.025 (n=148) | -0.020 (n=173) | +0.000 (n=197) | +0.000 (n=212) | +0.000 (n=242) | +0.000 (n=272) |
| mkt_below 1d | +0.093 (n=23) | +0.041 (n=52) | +0.000 (n=62) | +0.000 (n=92) | +0.000 (n=122) | +0.000 (n=152) | +0.000 (n=182) | -0.005 (n=230) | +0.031 (n=259) | +0.001 (n=287) |
| mkt_below 4h | -0.033 (n=20) | +0.000 (n=34) | +0.032 (n=74) | +0.012 (n=118) | +0.046 (n=148) | +0.068 (n=177) | +0.061 (n=182) | +0.056 (n=236) | +0.022 (n=249) | +0.020 (n=272) |
| self 1d | +0.054 (n=15) | +0.037 (n=38) | +0.026 (n=72) | -0.074 (n=99) | -0.130 (n=123) | -0.136 (n=169) | -0.104 (n=209) | -0.078 (n=238) | -0.066 (n=260) | +0.000 (n=281) |
| self 1h | -0.051 (n=28) | -0.096 (n=48) | -0.138 (n=70) | -0.137 (n=111) | -0.097 (n=139) | -0.049 (n=173) | -0.075 (n=182) | -0.085 (n=241) | -0.053 (n=269) | -0.051 (n=300) |
| self 4h | -0.015 (n=3) | -0.064 (n=61) | -0.003 (n=75) | +0.000 (n=95) | +0.000 (n=122) | -0.023 (n=171) | +0.063 (n=210) | +0.057 (n=228) | +0.067 (n=271) | +0.076 (n=274) |

Period 37 (the operator's hunch): self 1d gain +0.033 (neutral); self 4h gain -0.134 (hurts); self 1h gain -0.152 (hurts); btc 1d gain +0.000 (neutral); btc 4h gain -0.179 (hurts); mkt_below 1d gain +0.011 (neutral); mkt_below 4h gain +0.000 (silent)

### Plateaus: five neighbouring periods that ALL help (smallest gain of the five)

| min gain | feature | periods |
|---|---|---|
| +0.124 | mkt_disp vol 1h | 50-89 |
| +0.070 | btc kurt 4h | 89-150 |
| +0.070 | self sma_dist 4h | 274-278 |
| +0.067 | mkt_below sma_dist 4h | 171-175 |
| +0.062 | self dd 4h | 150-250 |
| +0.050 | mkt_below sma_dist 1d | 21-25 |
| +0.043 | rank sma_slope 1h | 34-55 |
| +0.041 | self sma_dist 1d | 22-26 |
| +0.038 | btc vol 1h | 13-25 |
| +0.036 | self ema_dist 1d | 15-30 |
| +0.027 | self skew 1d | 34-55 |
| +0.027 | mkt_below ema_dist 1d | 13-25 |

### The ten ideas that help 2024 most (and what they do to the other years)

| 2024 ret/DD | all years | gain over 22-25 | idea |
|---|---|---|---|
| +122.4% / 14% | 22:+0%/0% 23:+9%/3% 24:+122%/14% 25:+64%/17% | +0.147 | mkt_disp vol 15m n=242 |
| +118.0% / 10% | 22:+0%/0% 23:-0%/2% 24:+118%/10% 25:+64%/17% | +0.124 | mkt_disp vol 1h n=97 |
| +119.9% / 16% | 22:+0%/0% 23:+9%/3% 24:+120%/16% 25:+68%/11% | +0.152 | mkt_disp dd 4h n=23 |
| +115.3% / 10% | 22:+0%/0% 23:-0%/2% 24:+115%/10% 25:+64%/17% | +0.124 | mkt_disp vol 1h n=60 |
| +114.7% / 10% | 22:+0%/0% 23:-0%/2% 24:+115%/10% 25:+64%/17% | +0.124 | mkt_disp vol 1h n=100 |
| +115.2% / 15% | 22:+0%/0% 23:+9%/2% 24:+115%/15% 25:+104%/15% | +0.193 | rank roc 1d n=379 OR mkt_disp vol 15m n=242 |
| +111.5% / 15% | 22:+0%/0% 23:+9%/2% 24:+112%/15% 25:+69%/16% | +0.156 | rank rsi 2h n=61 OR mkt_disp vol 15m n=242 |
| +109.5% / 14% | 22:+0%/0% 23:+11%/3% 24:+110%/14% 25:+79%/16% | +0.170 | rank kurt 1h n=7 OR mkt_disp vol 15m n=242 |
| +107.2% / 11% | 22:+0%/0% 23:-0%/2% 24:+107%/11% 25:+64%/17% | +0.124 | mkt_disp vol 1h n=55 |
| +103.9% / 13% | 22:+0%/0% 23:-0%/2% 24:+104%/13% 25:+64%/17% | +0.124 | mkt_disp vol 2h n=43 |

## Replicated on both coin lists (same side every year)

Robust = neighbours (nearby periods, adjacent timeframes) with a positive gain on BOTH lists; a real effect should hold on most of them.

| gain today | gain pit | robust | idea |
|---|---|---|---|
| +0.107 (promising) | +0.132 (promising) | 8/12 of 12 | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| +0.107 (promising) | +0.132 (promising) | 8/12 of 12 | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| +0.070 (promising) | +0.136 (promising) | 8/12 of 12 | rank kurt 1h n=8 OR mkt_disp autocorr 2h n=419 |
| +0.035 (promising) | +0.023 (promising) | 0/1 of 6 | self efficiency 1h n=250 |

