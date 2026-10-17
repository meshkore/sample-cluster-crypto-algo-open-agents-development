# Rocket - report (auto, 2026-10-17T17:46:00+00:00)

Generated from `ledger.jsonl` by `rocket.py report`. Notes by hand: `JOURNAL.md`. Gain = selection-law score over 2022-25 with the validator minus without it (same champion, same book). Return/DD per year shown as `yy:ret/dd`.

## Universe: today

Baseline (release 34, no validator): law +0.270, max DD 24%, win rate 56.1%.

| | tested | win | promising | neutral | hurts | silent |
|---|---|---|---|---|---|---|
| real ideas | 8865 | 0 | 106 | 519 | 7867 | 373 |
| placebo (time-shifted) | 1820 | 0 | 13 | 164 | 1600 | 43 |

**Evidence test (primary ideas only):** 35 / 7770 = 0.45% win-or-promising vs placebo 0.73%, z = -2.9. Derived ideas (combos, half, band, neighbours of leaders: 71 / 722) are built from leaders picked on the SAME years they are graded on, so their rate is selection bias, not evidence; they are listed for follow-up only. A z above +3 would be worth the operator's time.

Chance rate: 0.0% of active placebo ideas 'win' and 0.7% are win-or-promising; real ideas: 0.0% and 1.2%. A family is only interesting where it clearly beats the placebo.

| family | tested | active | win % | win-or-promising % | best gain | best idea |
|---|---|---|---|---|---|---|
| combo2 | 239 | 239 | 0.0% | 7.9% | +0.107 | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| robust | 138 | 138 | 0.0% | 18.8% | +0.107 | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| random | 1664 | 1561 | 0.0% | 1.4% | +0.087 | rank kurt 1h n=7 |
| random_combo | 275 | 275 | 0.0% | 8.4% | +0.087 | rank pos 4h n=43 OR rel ema_dist 15m n=7 |
| cross_section | 1596 | 1516 | 0.0% | 0.5% | +0.065 | rank vol 4h n=25 |
| ma_scan | 2093 | 1937 | 0.0% | 0.0% | +0.064 | self sma_dist 1d n=298 |
| ma_cross | 612 | 610 | 0.0% | 0.0% | +0.063 | self ma_cross 1d a=10 b=300 |
| half | 40 | 40 | 0.0% | 2.5% | +0.062 | rank kurt 1h n=7 |
| engine44 | 44 | 43 | 0.0% | 2.3% | +0.057 | x down_streak |
| band | 40 | 30 | 0.0% | 6.7% | +0.047 | rank kurt 1h n=7 |
| macd | 783 | 782 | 0.0% | 0.4% | +0.041 | self macd 1h a=5 b=13 sig=9 |
| coin | 1 | 1 | 0.0% | 0.0% | +0.041 | coin |
| indicators | 799 | 790 | 0.0% | 0.1% | +0.032 | btc vol 1h n=34 |
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
| +0.107 | promising | 1/4 | 56.3% (base 56.1%) | 18% | 22:+36%/18% 23:+24%/4% 24:+94%/18% 25:+90%/12% | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| +0.107 | promising | 1/4 | 56.3% (base 56.1%) | 18% | 22:+36%/18% 23:+24%/4% 24:+94%/18% 25:+90%/12% | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| +0.102 | promising | 1/4 | 57.3% (base 56.1%) | 22% | 22:+45%/18% 23:+24%/4% 24:+101%/22% 25:+76%/16% | rank kurt 1h n=7 OR mkt_disp sma_dist 1h n=13 |
| +0.100 | promising | 2/4 | 58.2% (base 56.1%) | 24% | 22:+48%/18% 23:+26%/4% 24:+87%/24% 25:+67%/19% | rank kurt 1h n=7 OR self rsi 15m n=11 |
| +0.087 | promising | 1/4 | 55.9% (base 56.1%) | 22% | 22:+45%/18% 23:+25%/4% 24:+101%/22% 25:+59%/21% | rank kurt 1h n=7 |
| +0.087 | promising | 1/4 | 55.9% (base 56.1%) | 23% | 22:+48%/15% 23:+18%/5% 24:+86%/23% 25:+81%/16% | rank pos 4h n=43 OR rel ema_dist 15m n=7 |
| +0.087 | promising | 1/4 | 55.8% (base 56.1%) | 24% | 22:+48%/17% 23:+26%/3% 24:+59%/24% 25:+56%/18% | rank kurt 1h n=7 OR x upper_wick_fraction |
| +0.087 | promising | 1/4 | 55.8% (base 56.1%) | 24% | 22:+48%/17% 23:+26%/3% 24:+59%/24% 25:+56%/18% | rank kurt 1h n=7 OR x upper_wick_fraction |
| +0.081 | promising | 2/4 | 58.8% (base 56.1%) | 23% | 22:+60%/17% 23:+22%/5% 24:+49%/23% 25:+57%/17% | self rsi 15m n=11 OR rel roc 4h n=89 OR self efficiency 2h n=19 |
| +0.080 | promising | 1/4 | 58.6% (base 56.1%) | 22% | 22:+56%/15% 23:+11%/3% 24:+82%/22% 25:+94%/16% | self rsi 15m n=11 OR rank rsi 2h n=64 |
| +0.080 | promising | 2/4 | 58.2% (base 56.1%) | 23% | 22:+51%/16% 23:+22%/4% 24:+63%/23% 25:+55%/22% | self rsi 15m n=11 OR x upper_wick_fraction |
| +0.077 | promising | 1/4 | 56.5% (base 56.1%) | 24% | 22:+45%/18% 23:+22%/4% 24:+65%/24% 25:+84%/18% | rank kurt 1h n=7 OR rank skew 1h n=21 |
| +0.077 | promising | 1/4 | 56.5% (base 56.1%) | 24% | 22:+45%/18% 23:+22%/4% 24:+65%/24% 25:+84%/18% | rank skew 1h n=21 OR rank kurt 1h n=7 |
| +0.076 | promising | 0/4 | 56.9% (base 56.1%) | 24% | 22:+47%/17% 23:+22%/4% 24:+70%/24% 25:+60%/18% | rank kurt 1h n=7 OR rank skew 1h n=23 |
| +0.076 | promising | 0/4 | 56.9% (base 56.1%) | 24% | 22:+47%/17% 23:+22%/4% 24:+70%/24% 25:+60%/18% | rank skew 1h n=23 OR rank kurt 1h n=7 |
| +0.075 | promising | 1/4 | 56.7% (base 56.1%) | 23% | 22:+40%/18% 23:+22%/4% 24:+106%/23% 25:+68%/19% | rank kurt 1h n=7 OR rank skew 1h n=25 |
| +0.075 | promising | 1/4 | 56.7% (base 56.1%) | 23% | 22:+40%/18% 23:+22%/4% 24:+106%/23% 25:+68%/19% | rank skew 1h n=25 OR rank kurt 1h n=7 |
| +0.070 | promising | 1/4 | 57.4% (base 56.1%) | 19% | 22:+31%/18% 23:+22%/3% 24:+89%/19% 25:+76%/14% | rank kurt 1h n=8 OR mkt_disp autocorr 2h n=419 |
| +0.069 | promising | 1/4 | 57.3% (base 56.1%) | 21% | 22:+46%/15% 23:+11%/3% 24:+87%/21% 25:+110%/15% | rank rsi 2h n=64 OR mkt_disp sma_dist 1h n=13 |
| +0.068 | promising | 1/4 | 57.6% (base 56.1%) | 22% | 22:+49%/15% 23:+11%/3% 24:+81%/22% 25:+99%/16% | mkt_below ema_dist 1d n=15 OR rank rsi 2h n=64 OR x stoch_k |
| +0.068 | promising | 1/4 | 56.2% (base 56.1%) | 21% | 22:+48%/18% 23:+14%/5% 24:+100%/21% 25:+70%/18% | rank rsi 1h n=61 OR rel autocorr 1h n=31 |
| +0.068 | promising | 1/4 | 56.1% (base 56.1%) | 23% | 22:+53%/16% 23:+29%/3% 24:+62%/23% 25:+40%/22% | x upper_wick_fraction OR rank sma_slope 1h n=40 |
| +0.066 | promising | 1/4 | 56.8% (base 56.1%) | 22% | 22:+34%/17% 23:+25%/3% 24:+105%/22% 25:+60%/20% | rank kurt 1h n=7 OR btc macd 1h a=5 b=13 sig=5 |
| +0.066 | promising | 1/4 | 56.8% (base 56.1%) | 22% | 22:+34%/17% 23:+25%/3% 24:+105%/22% 25:+60%/20% | btc macd 1h a=5 b=13 sig=5 OR rank kurt 1h n=7 |
| +0.066 | promising | 1/4 | 56.3% (base 56.1%) | 22% | 22:+46%/18% 23:+25%/4% 24:+101%/22% 25:+46%/21% | rank kurt 1h n=7 OR btc ma_cross 1d a=30 b=67 |

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
| +0.024 | rank ema_dist 4h | 2-10 |
| +0.015 | rel ema_dist 1h | 75-144 |
| +0.001 | rank roc 1h | 5-15 |

### The ten ideas that help 2024 most (and what they do to the other years)

| 2024 ret/DD | all years | gain over 22-25 | idea |
|---|---|---|---|
| +149.7% / 19% | 22:+25%/17% 23:+10%/3% 24:+150%/19% 25:+5%/22% | -0.163 | mkt_disp vol 1h n=75 |
| +142.1% / 20% | 22:+24%/15% 23:+9%/3% 24:+142%/20% 25:+23%/23% | -0.106 | rank rsi 2h n=61 OR btc efficiency 3d n=31 OR btc macd 1h a=5 b=13 sig=5 |
| +139.2% / 17% | 22:+18%/18% 23:+23%/3% 24:+139%/17% 25:+20%/18% | -0.067 | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=339 |
| +131.8% / 22% | 22:+43%/15% 23:+8%/4% 24:+132%/22% 25:+33%/23% | -0.042 | self skew 12h n=23 |
| +127.3% / 18% | 22:+20%/16% 23:+10%/2% 24:+127%/18% 25:+63%/13% | -0.001 | rank rsi 2h n=61 OR rank pos 1w n=23 |
| +130.6% / 25% | 22:+43%/17% 23:+17%/5% 24:+131%/25% 25:+14%/24% | -0.086 | mkt_disp ema_dist 1d n=3 |
| +125.5% / 18% | 22:+16%/18% 23:+19%/3% 24:+125%/18% 25:+16%/20% | -0.104 | rank kurt 1h n=8 OR mkt_disp autocorr 2h n=339 |
| +124.4% / 20% | 22:+29%/16% 23:+15%/5% 24:+124%/20% 25:+38%/23% | -0.027 | rank zscore 1h n=189 |
| +122.8% / 21% | 22:+30%/17% 23:+19%/5% 24:+123%/21% 25:+50%/25% | +0.021 | mkt_disp kurt 2h n=166 |
| +119.7% / 22% | 22:+6%/17% 23:+1%/5% 24:+120%/22% 25:+29%/22% | -0.145 | btc ma_cross 4h a=200 b=233 |

## Universe: pit

Baseline (release 34, no validator): law +0.072, max DD 32%, win rate 53.0%.

| | tested | win | promising | neutral | hurts | silent |
|---|---|---|---|---|---|---|
| real ideas | 8773 | 0 | 138 | 1806 | 5517 | 1312 |
| placebo (time-shifted) | 1800 | 0 | 18 | 393 | 1236 | 153 |

**Evidence test (primary ideas only):** 29 / 6798 = 0.43% win-or-promising vs placebo 1.09%, z = -5.3. Derived ideas (combos, half, band, neighbours of leaders: 109 / 663) are built from leaders picked on the SAME years they are graded on, so their rate is selection bias, not evidence; they are listed for follow-up only. A z above +3 would be worth the operator's time.

Chance rate: 0.0% of active placebo ideas 'win' and 1.1% are win-or-promising; real ideas: 0.0% and 1.8%. A family is only interesting where it clearly beats the placebo.

| family | tested | active | win % | win-or-promising % | best gain | best idea |
|---|---|---|---|---|---|---|
| random_combo | 256 | 256 | 0.0% | 11.7% | +0.193 | rank roc 1d n=379 OR mkt_disp vol 15m n=242 |
| combo2 | 214 | 214 | 0.0% | 12.1% | +0.170 | rank kurt 1h n=7 OR mkt_disp vol 15m n=242 |
| robust | 138 | 138 | 0.0% | 37.7% | +0.151 | rank kurt 1h n=8 OR mkt_disp autocorr 2h n=377 |
| random | 1664 | 1405 | 0.0% | 0.9% | +0.147 | mkt_disp vol 15m n=242 |
| cross_section | 1596 | 1315 | 0.0% | 1.2% | +0.127 | mkt_disp vol 4h n=8 |
| band | 39 | 16 | 0.0% | 0.0% | +0.120 | mkt_disp autocorr 2h n=419 |
| ma_cross | 612 | 477 | 0.0% | 0.0% | +0.116 | btc ma_cross 1d a=30 b=89 |
| indicators | 798 | 654 | 0.0% | 0.2% | +0.096 | btc vol 1h n=13 |
| ma_scan | 2093 | 1727 | 0.0% | 0.0% | +0.093 | mkt_below sma_dist 1d n=23 |
| rsi | 498 | 416 | 0.0% | 0.0% | +0.076 | self rsi 4h n=110 |
| macd | 783 | 769 | 0.0% | 0.0% | +0.064 | mkt_below macd 1d a=3 b=89 sig=13 |
| daily | 21 | 16 | 0.0% | 0.0% | +0.014 | daily stablecoin_supply n=7 chg |
| half | 39 | 39 | 0.0% | 2.6% | +0.009 | mkt_mean ema_dist 1d n=10 |
| macro | 8 | 7 | 0.0% | 0.0% | +0.007 | macro ref_dxy_chg20 |
| data | 1 | 1 | 0.0% | 0.0% | +0.007 | breadth |
| funding | 5 | 5 | 0.0% | 0.0% | +0.004 | funding n=21 |
| ml | 3 | 1 | 0.0% | 0.0% | +0.000 | learned validator on bank 'core' |
| calendar | 3 | 3 | 0.0% | 0.0% | -0.004 | cal hour |
| coin | 1 | 1 | 0.0% | 0.0% | -0.032 | coin |
| model | 1 | 1 | 0.0% | 0.0% | -0.054 | model |

### Best 25 (win or promising)

| gain | verdict | sig yrs | win rate | max DD | years | idea |
|---|---|---|---|---|---|---|
| +0.193 | promising | 2/4 | 54.1% (base 53.0%) | 15% | 22:+0%/0% 23:+9%/2% 24:+115%/15% 25:+104%/15% | rank roc 1d n=379 OR mkt_disp vol 15m n=242 |
| +0.170 | promising | 2/4 | 52.4% (base 53.0%) | 16% | 22:+0%/0% 23:+11%/3% 24:+110%/14% 25:+79%/16% | rank kurt 1h n=7 OR mkt_disp vol 15m n=242 |
| +0.158 | promising | 1/4 | 56.8% (base 53.0%) | 12% | 22:+0%/0% 23:+13%/2% 24:+53%/12% 25:+105%/10% | rank vr 30m n=47 OR mkt_disp autocorr 2h n=419 |
| +0.156 | promising | 1/4 | 56.2% (base 53.0%) | 16% | 22:+0%/0% 23:+9%/2% 24:+112%/15% 25:+69%/16% | rank rsi 2h n=61 OR mkt_disp vol 15m n=242 |
| +0.151 | promising | 2/4 | 52.3% (base 53.0%) | 17% | 22:+0%/0% 23:+10%/3% 24:+63%/14% 25:+78%/17% | rank kurt 1h n=8 OR mkt_disp autocorr 2h n=377 |
| +0.149 | promising | 1/4 | 57.8% (base 53.0%) | 15% | 22:+0%/0% 23:+9%/2% 24:+61%/15% 25:+82%/12% | rank rsi 2h n=64 OR mkt_disp autocorr 2h n=419 |
| +0.148 | promising | 1/4 | 57.7% (base 53.0%) | 16% | 22:+0%/0% 23:+12%/2% 24:+57%/16% 25:+78%/12% | mkt_disp autocorr 2h n=419 OR rank rsi 2h n=64 OR rank kurt 1h n=7 |
| +0.147 | promising | 1/4 | 51.0% (base 53.0%) | 16% | 22:+0%/0% 23:+11%/3% 24:+57%/16% 25:+79%/16% | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=377 |
| +0.147 | promising | 1/4 | 55.6% (base 53.0%) | 14% | 22:+0%/0% 23:+10%/3% 24:+54%/14% 25:+70%/11% | rank kurt 1h n=8 OR mkt_disp autocorr 2h n=415 |
| +0.146 | promising | 2/4 | 50.8% (base 53.0%) | 17% | 22:+0%/0% 23:+10%/3% 24:+63%/17% 25:+71%/17% | rank kurt 30m n=7 OR mkt_disp autocorr 2h n=377 |
| +0.145 | promising | 1/4 | 57.9% (base 53.0%) | 18% | 22:+0%/0% 23:+9%/2% 24:+63%/18% 25:+65%/17% | rank rsi 2h n=64 OR mkt_mean kurt 4h n=37 |
| +0.141 | promising | 2/4 | 51.1% (base 53.0%) | 15% | 22:+0%/0% 23:+9%/2% 24:+52%/15% 25:+96%/15% | rank kurt 1h n=5 OR mkt_disp autocorr 2h n=377 |
| +0.139 | promising | 0/4 | 56.7% (base 53.0%) | 22% | 22:+0%/0% 23:+13%/2% 24:+59%/22% 25:+90%/16% | rank vr 30m n=47 OR mkt_mean kurt 4h n=37 |
| +0.139 | promising | 0/4 | 55.0% (base 53.0%) | 15% | 22:+0%/0% 23:+11%/3% 24:+48%/15% 25:+80%/10% | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=411 |
| +0.136 | promising | 0/4 | 56.0% (base 53.0%) | 14% | 22:+0%/0% 23:+10%/3% 24:+47%/14% 25:+75%/11% | rank kurt 1h n=8 OR mkt_disp autocorr 2h n=419 |
| +0.136 | promising | 0/4 | 55.4% (base 53.0%) | 15% | 22:+0%/0% 23:+11%/3% 24:+47%/15% 25:+71%/10% | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=415 |
| +0.136 | promising | 1/4 | 58.0% (base 53.0%) | 20% | 22:+0%/0% 23:+11%/3% 24:+55%/20% 25:+82%/16% | rank kurt 1h n=7 OR mkt_mean kurt 4h n=37 |
| +0.135 | promising | 1/4 | 56.0% (base 53.0%) | 17% | 22:+0%/0% 23:+10%/3% 24:+51%/17% 25:+74%/10% | rank kurt 30m n=7 OR mkt_disp autocorr 2h n=419 |
| +0.133 | promising | 1/4 | 51.3% (base 53.0%) | 19% | 22:+0%/0% 23:+9%/3% 24:+53%/19% 25:+106%/12% | coin OR mkt_mean ema_dist 1d n=10 |
| +0.132 | promising | 0/4 | 55.3% (base 53.0%) | 15% | 22:+0%/0% 23:+11%/3% 24:+45%/15% 25:+76%/11% | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| +0.132 | promising | 0/4 | 55.3% (base 53.0%) | 15% | 22:+0%/0% 23:+11%/3% 24:+45%/15% 25:+76%/11% | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| +0.132 | promising | 1/4 | 52.3% (base 53.0%) | 17% | 22:+0%/0% 23:+10%/3% 24:+48%/16% 25:+78%/17% | rank kurt 1h n=8 OR mkt_disp autocorr 2h n=457 |
| +0.131 | promising | 1/4 | 51.5% (base 53.0%) | 16% | 22:+0%/0% 23:+11%/3% 24:+46%/15% 25:+79%/16% | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=457 |
| +0.129 | promising | 2/4 | 52.4% (base 53.0%) | 26% | 22:+0%/0% 23:+9%/1% 24:+68%/26% 25:+87%/14% | mkt_below sma_slope 1d n=89 OR rank skew 1h n=23 |
| +0.128 | promising | 2/4 | 52.0% (base 53.0%) | 23% | 22:+0%/0% 23:+10%/3% 24:+59%/23% 25:+71%/17% | rank kurt 30m n=7 OR btc ma_cross 1d a=30 b=89 |

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
| +0.070 | self sma_dist 4h | 274-278 |
| +0.067 | mkt_below sma_dist 4h | 171-175 |
| +0.050 | mkt_below sma_dist 1d | 21-25 |
| +0.043 | rank sma_slope 1h | 34-55 |
| +0.041 | self sma_dist 1d | 22-26 |
| +0.038 | btc vol 1h | 13-25 |
| +0.036 | self ema_dist 1d | 15-30 |
| +0.027 | mkt_below ema_dist 1d | 13-25 |
| +0.022 | self rsi 4h | 100-140 |
| +0.022 | self rsi 1d | 24-28 |
| +0.020 | rel sma_slope 1h | 175-300 |

### The ten ideas that help 2024 most (and what they do to the other years)

| 2024 ret/DD | all years | gain over 22-25 | idea |
|---|---|---|---|
| +122.4% / 14% | 22:+0%/0% 23:+9%/3% 24:+122%/14% 25:+64%/17% | +0.147 | mkt_disp vol 15m n=242 |
| +115.3% / 10% | 22:+0%/0% 23:-0%/2% 24:+115%/10% 25:+64%/17% | +0.124 | mkt_disp vol 1h n=60 |
| +114.7% / 10% | 22:+0%/0% 23:-0%/2% 24:+115%/10% 25:+64%/17% | +0.124 | mkt_disp vol 1h n=100 |
| +115.2% / 15% | 22:+0%/0% 23:+9%/2% 24:+115%/15% 25:+104%/15% | +0.193 | rank roc 1d n=379 OR mkt_disp vol 15m n=242 |
| +111.5% / 15% | 22:+0%/0% 23:+9%/2% 24:+112%/15% 25:+69%/16% | +0.156 | rank rsi 2h n=61 OR mkt_disp vol 15m n=242 |
| +109.5% / 14% | 22:+0%/0% 23:+11%/3% 24:+110%/14% 25:+79%/16% | +0.170 | rank kurt 1h n=7 OR mkt_disp vol 15m n=242 |
| +107.2% / 11% | 22:+0%/0% 23:-0%/2% 24:+107%/11% 25:+64%/17% | +0.124 | mkt_disp vol 1h n=55 |
| +102.1% / 11% | 22:+0%/0% 23:-0%/2% 24:+102%/11% 25:+64%/17% | +0.124 | mkt_disp vol 1h n=50 |
| +101.2% / 11% | 22:+0%/0% 23:-0%/2% 24:+101%/11% 25:+64%/17% | +0.124 | mkt_disp vol 1h n=75 |
| +100.5% / 15% | 22:+0%/0% 23:+1%/1% 24:+101%/15% 25:+60%/13% | +0.128 | rank skew 1h n=23 OR mkt_disp vol 1h n=47 |

## Replicated on both coin lists (same side every year)

Robust = neighbours (nearby periods, adjacent timeframes) with a positive gain on BOTH lists; a real effect should hold on most of them.

| gain today | gain pit | robust | idea |
|---|---|---|---|
| +0.107 (promising) | +0.132 (promising) | 8/12 of 12 | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| +0.107 (promising) | +0.132 (promising) | 8/12 of 12 | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| +0.070 (promising) | +0.136 (promising) | 8/12 of 12 | rank kurt 1h n=8 OR mkt_disp autocorr 2h n=419 |

