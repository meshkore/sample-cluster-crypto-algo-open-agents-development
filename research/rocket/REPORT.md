# Rocket - report (auto, 2026-10-16T17:24:01+00:00)

Generated from `ledger.jsonl` by `rocket.py report`. Notes by hand: `JOURNAL.md`. Gain = selection-law score over 2022-25 with the validator minus without it (same champion, same book). Return/DD per year shown as `yy:ret/dd`.

## Universe: today

Baseline (release 34, no validator): law +0.270, max DD 24%, win rate 56.1%.

| | tested | win | promising | neutral | hurts | silent |
|---|---|---|---|---|---|---|
| real ideas | 3250 | 0 | 22 | 172 | 3000 | 56 |
| placebo (time-shifted) | 325 | 0 | 0 | 33 | 286 | 6 |

Chance rate: 0.0% of active placebo ideas 'win' and 0.0% are win-or-promising; real ideas: 0.0% and 0.7%. A family is only interesting where it clearly beats the placebo.

| family | tested | active | win % | win-or-promising % | best gain | best idea |
|---|---|---|---|---|---|---|
| combo2 | 198 | 198 | 0.0% | 3.0% | +0.107 | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| random | 320 | 308 | 0.0% | 2.3% | +0.087 | rank kurt 1h n=7 |
| random_combo | 55 | 55 | 0.0% | 5.5% | +0.087 | rank kurt 1h n=7 OR x upper_wick_fraction |
| ma_scan | 510 | 510 | 0.0% | 0.0% | +0.064 | self sma_dist 1d n=298 |
| ma_cross | 511 | 509 | 0.0% | 0.0% | +0.063 | self ma_cross 1d a=10 b=300 |
| half | 25 | 25 | 0.0% | 4.0% | +0.062 | rank kurt 1h n=7 |
| engine44 | 44 | 43 | 0.0% | 2.3% | +0.057 | x down_streak |
| cross_section | 364 | 344 | 0.0% | 0.3% | +0.051 | rank ema_dist 4h n=15 |
| band | 25 | 15 | 0.0% | 6.7% | +0.047 | rank kurt 1h n=7 |
| macd | 510 | 510 | 0.0% | 0.4% | +0.041 | self macd 1h a=5 b=13 sig=9 |
| coin | 1 | 1 | 0.0% | 0.0% | +0.041 | coin |
| rsi | 498 | 493 | 0.0% | 0.0% | +0.007 | self rsi 1d n=220 |
| macro | 8 | 7 | 0.0% | 0.0% | +0.000 | macro ref_y10_chg20 |
| daily | 21 | 16 | 0.0% | 0.0% | +0.000 | daily oi_BTCUSDT n=1 |
| indicators | 146 | 146 | 0.0% | 0.0% | -0.004 | btc ema_dist 4h n=10 |
| funding | 5 | 5 | 0.0% | 0.0% | -0.013 | funding n=3 |
| ml | 4 | 4 | 0.0% | 0.0% | -0.018 | learned validator on bank 'all' |
| calendar | 3 | 3 | 0.0% | 0.0% | -0.031 | cal hour |
| data | 1 | 1 | 0.0% | 0.0% | -0.063 | breadth |
| model | 1 | 1 | 0.0% | 0.0% | -0.159 | model |

### Best 25 (win or promising)

| gain | verdict | sig yrs | win rate | max DD | years | idea |
|---|---|---|---|---|---|---|
| +0.107 | promising | 1/4 | 56.3% (base 56.1%) | 18% | 22:+36%/18% 23:+24%/4% 24:+94%/18% 25:+90%/12% | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| +0.102 | promising | 1/4 | 57.3% (base 56.1%) | 22% | 22:+45%/18% 23:+24%/4% 24:+101%/22% 25:+76%/16% | rank kurt 1h n=7 OR mkt_disp sma_dist 1h n=13 |
| +0.087 | promising | 1/4 | 55.9% (base 56.1%) | 22% | 22:+45%/18% 23:+25%/4% 24:+101%/22% 25:+59%/21% | rank kurt 1h n=7 |
| +0.087 | promising | 1/4 | 55.8% (base 56.1%) | 24% | 22:+48%/17% 23:+26%/3% 24:+59%/24% 25:+56%/18% | rank kurt 1h n=7 OR x upper_wick_fraction |
| +0.087 | promising | 1/4 | 55.8% (base 56.1%) | 24% | 22:+48%/17% 23:+26%/3% 24:+59%/24% 25:+56%/18% | rank kurt 1h n=7 OR x upper_wick_fraction |
| +0.069 | promising | 1/4 | 57.3% (base 56.1%) | 21% | 22:+46%/15% 23:+11%/3% 24:+87%/21% 25:+110%/15% | rank rsi 2h n=64 OR mkt_disp sma_dist 1h n=13 |
| +0.068 | promising | 1/4 | 57.6% (base 56.1%) | 22% | 22:+49%/15% 23:+11%/3% 24:+81%/22% 25:+99%/16% | mkt_below ema_dist 1d n=15 OR rank rsi 2h n=64 OR x stoch_k |
| +0.062 | promising | 0/4 | 56.5% (base 56.1%) | 23% | 22:+40%/17% 23:+23%/4% 24:+83%/23% 25:+52%/17% | rank kurt 1h n=7 |
| +0.055 | promising | 0/4 | 58.4% (base 56.1%) | 24% | 22:+45%/17% 23:+20%/5% 24:+57%/24% 25:+51%/22% | self rsi 15m n=11 |
| +0.053 | promising | 1/4 | 55.8% (base 56.1%) | 21% | 22:+46%/15% 23:+11%/3% 24:+105%/21% 25:+70%/18% | rank rsi 2h n=64 |
| +0.049 | promising | 0/4 | 58.7% (base 56.1%) | 24% | 22:+47%/12% 23:+20%/5% 24:+47%/24% 25:+54%/16% | mkt_disp sma_dist 1h n=13 OR self rsi 15m n=11 OR btc macd 4h a=19 b=26 sig=5 |
| +0.047 | promising | 0/4 | 57.5% (base 56.1%) | 24% | 22:+46%/18% 23:+27%/4% 24:+71%/24% 25:+40%/23% | rank kurt 1h n=7 |
| +0.045 | promising | 1/4 | 55.2% (base 56.1%) | 26% | 22:+44%/18% 23:+22%/4% 24:+58%/26% 25:+47%/23% | rank macd 1h a=22 b=95 sig=12 |
| +0.043 | promising | 0/4 | 55.0% (base 56.1%) | 23% | 22:+47%/15% 23:+11%/3% 24:+90%/23% 25:+60%/22% | rank rsi 2h n=61 |
| +0.037 | promising | 2/4 | 55.7% (base 56.1%) | 24% | 22:+53%/16% 23:+21%/4% 24:+60%/24% 25:+40%/22% | x upper_wick_fraction |
| +0.037 | promising | 1/4 | 56.6% (base 56.1%) | 24% | 22:+35%/17% 23:+20%/5% 24:+82%/23% 25:+52%/24% | btc macd 1h a=5 b=13 sig=5 |
| +0.032 | promising | 0/4 | 55.8% (base 56.1%) | 22% | 22:+25%/14% 23:+21%/4% 24:+101%/22% 25:+59%/21% | rank kurt 1h n=7 OR mkt_mean vol_ratio 8h n=41 |
| +0.029 | promising | 0/4 | 56.5% (base 56.1%) | 25% | 22:+45%/15% 23:+21%/4% 24:+60%/25% 25:+42%/22% | rel ema_dist 1h n=2 |
| +0.023 | promising | 0/4 | 56.2% (base 56.1%) | 23% | 22:+22%/17% 23:+20%/3% 24:+87%/23% 25:+61%/13% | rank pos 1w n=23 |
| +0.018 | promising | 0/4 | 55.4% (base 56.1%) | 22% | 22:+32%/18% 23:+23%/3% 24:+84%/22% 25:+41%/18% | rank kurt 1h n=7 OR self ma_cross 4h a=30 b=200 |
| +0.013 | promising | 1/4 | 55.8% (base 56.1%) | 25% | 22:+44%/14% 23:+19%/5% 24:+64%/25% 25:+39%/17% | btc macd 4h a=19 b=26 sig=5 |
| +0.005 | promising | 0/4 | 57.3% (base 56.1%) | 24% | 22:+43%/17% 23:+20%/5% 24:+85%/24% 25:+36%/24% | mkt_disp sma_dist 1h n=13 |

### Moving averages 2-300: gain by period bucket (best n in bucket)

| source tf | 2-31 | 32-61 | 62-91 | 92-121 | 122-151 | 152-181 | 182-211 | 212-241 | 242-271 | 272-301 |
|---|---|---|---|---|---|---|---|---|---|---|
| self 1d | -0.060 (n=6) | -0.099 (n=36) | -0.035 (n=90) | -0.018 (n=100) | -0.147 (n=143) | -0.127 (n=178) | -0.121 (n=189) | -0.105 (n=241) | +0.051 (n=268) | +0.064 (n=298) |
| self 4h | -0.041 (n=6) | -0.092 (n=33) | -0.093 (n=74) | -0.097 (n=92) | -0.109 (n=123) | -0.108 (n=153) | -0.093 (n=200) | -0.102 (n=212) |  |  |

Period 37 (the operator's hunch): self 1d gain -0.100 (hurts); self 4h gain -0.102 (hurts)

### Plateaus: five neighbouring periods that ALL help (smallest gain of the five)

| min gain | feature | periods |
|---|---|---|
| +0.037 | self sma_dist 1d | 266-270 |
| +0.024 | rank ema_dist 4h | 2-10 |

### The ten ideas that help 2024 most (and what they do to the other years)

| 2024 ret/DD | all years | gain over 22-25 | idea |
|---|---|---|---|
| +131.8% / 22% | 22:+43%/15% 23:+8%/4% 24:+132%/22% 25:+33%/23% | -0.042 | self skew 12h n=23 |
| +130.6% / 25% | 22:+43%/17% 23:+17%/5% 24:+131%/25% 25:+14%/24% | -0.086 | mkt_disp ema_dist 1d n=3 |
| +116.5% / 24% | 22:+43%/17% 23:+17%/5% 24:+116%/24% 25:+14%/26% | -0.088 | mkt_disp ema_dist 1d n=2 |
| +114.9% / 24% | 22:+27%/17% 23:+16%/5% 24:+115%/24% 25:+15%/25% | -0.109 | mkt_disp ema_dist 1d n=8 |
| +112.0% / 23% | 22:+38%/17% 23:+10%/3% 24:+112%/23% 25:+23%/24% | -0.083 | mkt_disp ema_dist 1d n=25 |
| +109.7% / 23% | 22:+43%/17% 23:+10%/3% 24:+110%/23% 25:+29%/24% | -0.053 | mkt_disp ema_dist 1d n=20 |
| +107.9% / 24% | 22:+29%/19% 23:+19%/5% 24:+108%/24% 25:+38%/23% | -0.014 | mkt_disp skew 8h n=97 |
| +105.3% / 23% | 22:+43%/17% 23:+10%/3% 24:+105%/23% 25:+9%/25% | -0.129 | mkt_disp ma_cross 2h a=49 b=273 |
| +104.7% / 21% | 22:+46%/15% 23:+11%/3% 24:+105%/21% 25:+70%/18% | +0.053 | rank rsi 2h n=64 |
| +104.7% / 21% | 22:+19%/11% 23:+12%/3% 24:+105%/21% 25:+70%/18% | +0.001 | rank rsi 2h n=64 OR mkt_mean vol_ratio 8h n=41 |

## Universe: pit

Baseline (release 34, no validator): law +0.072, max DD 32%, win rate 53.0%.

| | tested | win | promising | neutral | hurts | silent |
|---|---|---|---|---|---|---|
| real ideas | 3170 | 0 | 29 | 645 | 2100 | 396 |
| placebo (time-shifted) | 319 | 0 | 4 | 76 | 203 | 36 |

Chance rate: 0.0% of active placebo ideas 'win' and 1.4% are win-or-promising; real ideas: 0.0% and 1.0%. A family is only interesting where it clearly beats the placebo.

| family | tested | active | win % | win-or-promising % | best gain | best idea |
|---|---|---|---|---|---|---|
| combo2 | 174 | 174 | 0.0% | 12.1% | +0.158 | rank vr 30m n=47 OR mkt_disp autocorr 2h n=419 |
| random_combo | 46 | 46 | 0.0% | 8.7% | +0.148 | mkt_disp autocorr 2h n=419 OR rank rsi 2h n=64 OR rank kurt 1h n=7 |
| random | 320 | 276 | 0.0% | 1.1% | +0.147 | mkt_disp vol 15m n=242 |
| cross_section | 364 | 300 | 0.0% | 0.3% | +0.125 | mkt_mean ema_dist 1d n=10 |
| band | 24 | 6 | 0.0% | 0.0% | +0.120 | mkt_disp autocorr 2h n=419 |
| ma_cross | 511 | 421 | 0.0% | 0.0% | +0.116 | btc ma_cross 1d a=30 b=89 |
| rsi | 498 | 416 | 0.0% | 0.0% | +0.076 | self rsi 4h n=110 |
| indicators | 146 | 132 | 0.0% | 0.0% | +0.071 | self ema_dist 1d n=21 |
| ma_scan | 510 | 446 | 0.0% | 0.0% | +0.063 | self sma_dist 4h n=210 |
| macd | 510 | 498 | 0.0% | 0.0% | +0.047 | btc macd 1h a=3 b=21 sig=5 |
| daily | 21 | 16 | 0.0% | 0.0% | +0.014 | daily stablecoin_supply n=7 chg |
| half | 24 | 24 | 0.0% | 0.0% | +0.009 | mkt_mean ema_dist 1d n=10 |
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
| +0.158 | promising | 1/4 | 56.8% (base 53.0%) | 12% | 22:+0%/0% 23:+13%/2% 24:+53%/12% 25:+105%/10% | rank vr 30m n=47 OR mkt_disp autocorr 2h n=419 |
| +0.149 | promising | 1/4 | 57.8% (base 53.0%) | 15% | 22:+0%/0% 23:+9%/2% 24:+61%/15% 25:+82%/12% | rank rsi 2h n=64 OR mkt_disp autocorr 2h n=419 |
| +0.148 | promising | 1/4 | 57.7% (base 53.0%) | 16% | 22:+0%/0% 23:+12%/2% 24:+57%/16% 25:+78%/12% | mkt_disp autocorr 2h n=419 OR rank rsi 2h n=64 OR rank kurt 1h n=7 |
| +0.145 | promising | 1/4 | 57.9% (base 53.0%) | 18% | 22:+0%/0% 23:+9%/2% 24:+63%/18% 25:+65%/17% | rank rsi 2h n=64 OR mkt_mean kurt 4h n=37 |
| +0.139 | promising | 0/4 | 56.7% (base 53.0%) | 22% | 22:+0%/0% 23:+13%/2% 24:+59%/22% 25:+90%/16% | rank vr 30m n=47 OR mkt_mean kurt 4h n=37 |
| +0.136 | promising | 1/4 | 58.0% (base 53.0%) | 20% | 22:+0%/0% 23:+11%/3% 24:+55%/20% 25:+82%/16% | rank kurt 1h n=7 OR mkt_mean kurt 4h n=37 |
| +0.133 | promising | 1/4 | 51.3% (base 53.0%) | 19% | 22:+0%/0% 23:+9%/3% 24:+53%/19% 25:+106%/12% | coin OR mkt_mean ema_dist 1d n=10 |
| +0.132 | promising | 0/4 | 55.3% (base 53.0%) | 15% | 22:+0%/0% 23:+11%/3% 24:+45%/15% 25:+76%/11% | rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419 |
| +0.114 | promising | 1/4 | 50.6% (base 53.0%) | 19% | 22:+0%/0% 23:+11%/3% 24:+42%/19% 25:+79%/16% | rank kurt 1h n=7 OR mkt_mean ema_dist 1d n=10 |
| +0.105 | promising | 0/4 | 54.2% (base 53.0%) | 25% | 22:+0%/0% 23:+9%/2% 24:+46%/25% 25:+69%/16% | rank rsi 2h n=64 OR mkt_mean ema_dist 1d n=10 |
| +0.104 | promising | 1/4 | 51.8% (base 53.0%) | 27% | 22:+0%/0% 23:+13%/2% 24:+45%/27% 25:+102%/17% | rank vr 30m n=47 OR mkt_mean ema_dist 1d n=10 |
| +0.084 | promising | 1/4 | 49.9% (base 53.0%) | 20% | 22:+0%/0% 23:+11%/3% 24:+31%/20% 25:+79%/16% | rank kurt 1h n=7 OR mkt_mean ema_dist 1d n=8 |
| +0.077 | promising | 1/4 | 50.9% (base 53.0%) | 24% | 22:+0%/0% 23:+11%/3% 24:+33%/24% 25:+79%/16% | rank kurt 1h n=7 OR self rsi 4h n=130 |
| +0.076 | promising | 1/4 | 53.0% (base 53.0%) | 25% | 22:+0%/0% 23:+13%/2% 24:+32%/25% 25:+102%/17% | rank vr 30m n=47 OR self rsi 4h n=110 |
| +0.070 | promising | 1/4 | 51.4% (base 53.0%) | 28% | 22:+0%/0% 23:+13%/2% 24:+32%/28% 25:+102%/17% | rank vr 30m n=47 OR mkt_mean ema_dist 1d n=8 |
| +0.069 | promising | 1/4 | 51.5% (base 53.0%) | 24% | 22:+0%/0% 23:+11%/3% 24:+30%/24% 25:+79%/16% | rank kurt 1h n=7 OR self rsi 4h n=110 |
| +0.069 | promising | 0/4 | 57.3% (base 53.0%) | 17% | 22:+0%/0% 23:+13%/2% 24:+21%/17% 25:+82%/7% | rank vr 30m n=47 OR mkt_below ema_dist 1d n=20 |
| +0.066 | promising | 1/4 | 53.1% (base 53.0%) | 25% | 22:+0%/0% 23:+13%/2% 24:+28%/25% 25:+102%/17% | rank vr 30m n=47 OR self rsi 4h n=100 |
| +0.065 | promising | 0/4 | 59.9% (base 53.0%) | 16% | 22:+0%/0% 23:+9%/2% 24:+21%/16% 25:+77%/10% | rank rsi 2h n=64 OR mkt_below ema_dist 1d n=20 |
| +0.064 | promising | 0/4 | 53.8% (base 53.0%) | 23% | 22:+0%/0% 23:+9%/2% 24:+28%/23% 25:+69%/16% | rank rsi 2h n=64 OR self rsi 4h n=130 |
| +0.061 | promising | 0/4 | 54.7% (base 53.0%) | 24% | 22:+0%/0% 23:+9%/2% 24:+28%/24% 25:+69%/16% | rank rsi 2h n=64 OR self rsi 4h n=110 |
| +0.061 | promising | 0/4 | 57.1% (base 53.0%) | 16% | 22:+0%/0% 23:+11%/3% 24:+18%/16% 25:+86%/7% | rank kurt 1h n=7 OR mkt_below ema_dist 1d n=20 |
| +0.061 | promising | 0/4 | 53.8% (base 53.0%) | 26% | 22:+0%/0% 23:+9%/2% 24:+30%/26% 25:+69%/16% | rank rsi 2h n=64 OR mkt_mean ema_dist 1d n=8 |
| +0.051 | promising | 1/4 | 53.6% (base 53.0%) | 31% | 22:+0%/0% 23:+11%/3% 24:+29%/31% 25:+65%/17% | rank sma_slope 15m n=233 |
| +0.049 | promising | 1/4 | 51.9% (base 53.0%) | 28% | 22:+0%/0% 23:+13%/2% 24:+23%/28% 25:+102%/17% | rank vr 30m n=47 OR self rsi 4h n=130 |

### Moving averages 2-300: gain by period bucket (best n in bucket)

| source tf | 2-31 | 32-61 | 62-91 | 92-121 | 122-151 | 152-181 | 182-211 | 212-241 | 242-271 | 272-301 |
|---|---|---|---|---|---|---|---|---|---|---|
| self 1d | +0.054 (n=15) | +0.037 (n=38) | +0.026 (n=72) | -0.074 (n=99) | -0.130 (n=123) | -0.136 (n=169) | -0.104 (n=209) | -0.078 (n=238) | -0.066 (n=260) | +0.000 (n=281) |
| self 4h | -0.015 (n=3) | -0.064 (n=61) | -0.003 (n=75) | +0.000 (n=95) | +0.000 (n=122) | -0.023 (n=171) | +0.063 (n=210) | -0.065 (n=212) |  |  |

Period 37 (the operator's hunch): self 1d gain +0.033 (neutral); self 4h gain -0.134 (hurts)

### Plateaus: five neighbouring periods that ALL help (smallest gain of the five)

| min gain | feature | periods |
|---|---|---|
| +0.041 | self sma_dist 1d | 22-26 |
| +0.036 | self ema_dist 1d | 15-30 |
| +0.027 | mkt_below ema_dist 1d | 13-25 |
| +0.022 | self rsi 4h | 100-140 |
| +0.022 | self rsi 1d | 24-28 |
| +0.014 | btc rsi 1d | 55-59 |
| +0.007 | mkt_below ema_dist 4h | 75-144 |
| +0.005 | rank ema_dist 1h | 15-30 |
| +0.002 | self rsi 1h | 210-250 |

### The ten ideas that help 2024 most (and what they do to the other years)

| 2024 ret/DD | all years | gain over 22-25 | idea |
|---|---|---|---|
| +122.4% / 14% | 22:+0%/0% 23:+9%/3% 24:+122%/14% 25:+64%/17% | +0.147 | mkt_disp vol 15m n=242 |
| +85.0% / 10% | 22:+0%/0% 23:+0%/0% 24:+85%/10% 25:+64%/17% | +0.124 | mkt_mean vol_ratio 8h n=41 |
| +81.3% / 11% | 22:+0%/0% 23:+0%/0% 24:+81%/11% 25:+79%/16% | +0.142 | rank kurt 1h n=7 OR mkt_mean vol_ratio 8h n=41 |
| +80.3% / 23% | 22:+0%/0% 23:-0%/2% 24:+80%/23% 25:+64%/17% | +0.110 | mkt_disp vol 1h n=17 |
| +67.3% / 11% | 22:+0%/0% 23:+0%/0% 24:+67%/11% 25:+102%/17% | +0.127 | rank vr 30m n=47 OR mkt_mean vol_ratio 8h n=41 |
| +68.0% / 16% | 22:+0%/0% 23:+9%/3% 24:+68%/16% 25:+75%/8% | +0.153 | mkt_mean kurt 4h n=37 OR mkt_disp autocorr 2h n=419 |
| +70.3% / 22% | 22:+0%/0% 23:+9%/3% 24:+70%/22% 25:+26%/17% | +0.048 | btc ma_cross 1d a=37 b=100 |
| +63.7% / 11% | 22:+0%/0% 23:+0%/0% 24:+64%/11% 25:+69%/16% | +0.127 | rank rsi 2h n=64 OR mkt_mean vol_ratio 8h n=41 |
| +62.8% / 9% | 22:+0%/0% 23:+0%/0% 24:+63%/9% 25:+71%/15% | +0.128 | mkt_disp sma_dist 1h n=13 OR mkt_mean vol_ratio 8h n=41 |
| +62.8% / 18% | 22:+0%/0% 23:+9%/2% 24:+63%/18% 25:+65%/17% | +0.145 | rank rsi 2h n=64 OR mkt_mean kurt 4h n=37 |

