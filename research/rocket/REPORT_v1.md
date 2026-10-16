# Rocket - report (auto, 2026-10-16T05:26:21+00:00)

Generated from `ledger.jsonl` by `rocket.py report`. Notes by hand: `JOURNAL.md`. Gain = selection-law score over 2022-25 with the validator minus without it (same champion, same book). Return/DD per year shown as `yy:ret/dd`.

## Universe: today

Baseline (release 34, no validator): law +0.270, max DD 24%, win rate 56.1%.

| | tested | win | promising | neutral | hurts | silent |
|---|---|---|---|---|---|---|
| real ideas | 3462 | 0 | 8 | 131 | 2063 | 1260 |
| placebo (time-shifted) | 444 | 0 | 1 | 36 | 228 | 179 |

Chance rate: 0.0% of active placebo ideas 'win' and 0.4% are win-or-promising; real ideas: 0.0% and 0.4%. A family is only interesting where it clearly beats the placebo.

| family | tested | active | win % | win-or-promising % | best gain | best idea |
|---|---|---|---|---|---|---|
| combo2 | 300 | 180 | 0.0% | 0.0% | +0.040 | mkt_mean efficiency 8h n=19 OR x bb_percent_b |
| random_combo | 54 | 32 | 0.0% | 9.4% | +0.037 | self pos 15m n=19 OR self rsi 4h n=70 OR x bb_percent_b |
| engine44 | 44 | 36 | 0.0% | 0.0% | +0.036 | x bb_percent_b |
| random | 437 | 291 | 0.0% | 0.3% | +0.019 | rank efficiency 4h n=7 |
| macd | 478 | 477 | 0.0% | 0.2% | +0.018 | btc macd 4h a=3 b=21 sig=5 |
| band | 42 | 9 | 0.0% | 11.1% | +0.012 | rel roc 15m n=7 |
| coin | 1 | 1 | 0.0% | 0.0% | +0.011 | coin |
| cross_section | 340 | 132 | 0.0% | 0.8% | +0.011 | rel ema_dist 1h n=2 |
| half | 43 | 16 | 0.0% | 6.2% | +0.011 | x bb_percent_b |
| daily | 21 | 9 | 0.0% | 0.0% | +0.005 | daily feargreed n=1 chg |
| ma_cross | 478 | 306 | 0.0% | 0.0% | +0.003 | self ma_cross 1d a=13 b=50 |
| rsi | 478 | 342 | 0.0% | 0.0% | +0.002 | self rsi 1h n=9 |
| indicators | 137 | 102 | 0.0% | 0.0% | +0.001 | btc ema_dist 4h n=3 |
| ma_scan | 477 | 175 | 0.0% | 0.0% | +0.000 | self sma_dist 1d n=2 |
| data | 1 | 0 | 0.0% | 0.0% | +0.000 | breadth |
| macro | 8 | 6 | 0.0% | 0.0% | +0.000 | macro ref_y10_chg20 |
| combo3 | 110 | 75 | 0.0% | 0.0% | +0.000 | self rsi 4h n=80 OR self rsi 4h n=70 OR self rsi 4h n=110 |
| ml | 4 | 4 | 0.0% | 0.0% | -0.001 | learned validator on bank 'x44' |
| calendar | 3 | 3 | 0.0% | 0.0% | -0.006 | cal hour |
| funding | 5 | 5 | 0.0% | 0.0% | -0.007 | funding n=3 |
| model | 1 | 1 | 0.0% | 0.0% | -0.030 | model |

### Best 25 (win or promising)

| gain | verdict | sig yrs | win rate | max DD | years | idea |
|---|---|---|---|---|---|---|
| +0.011 | promising | 0/4 | 56.0% (base 56.1%) | 23% | 22:+45%/17% 23:+19%/5% 24:+84%/23% 25:+36%/23% | x bb_percent_b |
| +0.009 | promising | 1/4 | 56.6% (base 56.1%) | 24% | 22:+43%/17% 23:+22%/5% 24:+78%/24% 25:+35%/23% | rel roc 15m n=7 |
| +0.004 | promising | 1/4 | 55.8% (base 56.1%) | 25% | 22:+44%/14% 23:+19%/5% 24:+64%/25% 25:+37%/23% | btc macd 4h a=19 b=21 sig=5 |
| +0.004 | promising | 1/4 | 55.8% (base 56.1%) | 25% | 22:+44%/14% 23:+19%/5% 24:+64%/25% 25:+37%/23% | self ema_dist 1d n=21 OR btc macd 4h a=19 b=21 sig=5 |
| +0.004 | promising | 1/4 | 55.8% (base 56.1%) | 25% | 22:+44%/14% 23:+19%/5% 24:+64%/25% 25:+37%/23% | mkt_mean ema_dist 1d n=13 OR self ma_cross 4h a=5 b=233 OR btc macd 4h a=19 b=21 sig=5 |
| +0.004 | promising | 0/4 | 56.5% (base 56.1%) | 24% | 22:+45%/17% 23:+19%/5% 24:+83%/24% 25:+35%/23% | mkt_disp ema_dist 1h n=3 |
| +0.004 | promising | 0/4 | 56.5% (base 56.1%) | 24% | 22:+45%/17% 23:+19%/5% 24:+83%/24% 25:+35%/23% | mkt_disp ema_dist 1h n=3 OR mkt_mean ema_dist 1d n=8 OR self sma_dist 4h n=134 |
| +0.003 | promising | 2/4 | 56.2% (base 56.1%) | 24% | 22:+45%/14% 23:+19%/5% 24:+81%/24% 25:+35%/23% | btc macd 4h a=19 b=21 sig=5 |

### Moving averages 2-300: gain by period bucket (best n in bucket)

| source tf | 2-31 | 32-61 | 62-91 | 92-121 | 122-151 | 152-181 | 182-211 | 212-241 | 242-271 | 272-301 |
|---|---|---|---|---|---|---|---|---|---|---|
| self 1d | +0.000 (n=2) | +0.000 (n=42) | +0.000 (n=62) | +0.000 (n=92) | +0.000 (n=122) | +0.000 (n=152) | +0.000 (n=182) | +0.000 (n=225) | +0.000 (n=242) | +0.000 (n=273) |
| self 4h | -0.037 (n=6) | -0.066 (n=51) | -0.093 (n=74) | +0.000 (n=113) | +0.000 (n=122) | +0.000 (n=152) |  |  |  |  |

Period 37 (the operator's hunch): self 1d gain -0.011 (hurts); self 4h gain -0.099 (hurts)

### The ten ideas that help 2024 most (and what they do to the other years)

| 2024 ret/DD | all years | gain over 22-25 | idea |
|---|---|---|---|
| +93.1% / 21% | 22:+40%/18% 23:+18%/5% 24:+93%/21% 25:+35%/23% | -0.007 | self macd 1h a=5 b=34 sig=5 |
| +90.9% / 24% | 22:+36%/17% 23:+18%/5% 24:+91%/24% 25:+35%/23% | -0.013 | self ma_cross 4h a=89 b=200 |
| +89.8% / 23% | 22:+39%/18% 23:+16%/3% 24:+90%/23% 25:+35%/23% | -0.015 | self kurt 1h n=97 |
| +88.7% / 21% | 22:+39%/18% 23:+18%/5% 24:+89%/21% 25:+35%/23% | -0.009 | self macd 1h a=3 b=26 sig=9 |
| +89.0% / 24% | 22:+38%/11% 23:+1%/0% 24:+89%/24% 25:+25%/23% | -0.105 | self skew 1h n=167 |
| +86.1% / 23% | 22:+24%/17% 23:+19%/5% 24:+86%/23% 25:+35%/23% | -0.034 | self ma_cross 4h a=144 b=200 |
| +84.6% / 23% | 22:+16%/17% 23:+21%/4% 24:+85%/23% 25:+35%/23% | -0.047 | btc macd 1h a=8 b=21 sig=13 |
| +84.3% / 23% | 22:+45%/17% 23:+19%/5% 24:+84%/23% 25:+36%/23% | +0.011 | x bb_percent_b |
| +84.2% / 23% | 22:+10%/13% 23:+11%/5% 24:+84%/23% 25:+35%/23% | -0.089 | self ma_cross 4h a=5 b=8 |
| +84.1% / 23% | 22:+27%/15% 23:+21%/4% 24:+84%/23% 25:+35%/23% | -0.019 | btc macd 1h a=8 b=26 sig=5 |

## Universe: pit

Baseline (release 34, no validator): law +0.072, max DD 32%, win rate 53.0%.

| | tested | win | promising | neutral | hurts | silent |
|---|---|---|---|---|---|---|
| real ideas | 3285 | 0 | 5 | 925 | 2039 | 316 |
| placebo (time-shifted) | 355 | 0 | 0 | 92 | 239 | 24 |

Chance rate: 0.0% of active placebo ideas 'win' and 0.0% are win-or-promising; real ideas: 0.0% and 0.2%. A family is only interesting where it clearly beats the placebo.

| family | tested | active | win % | win-or-promising % | best gain | best idea |
|---|---|---|---|---|---|---|
| cross_section | 340 | 281 | 0.0% | 0.7% | +0.138 | mkt_disp ema_dist 4h n=20 |
| ma_cross | 478 | 402 | 0.0% | 0.0% | +0.133 | btc ma_cross 1d a=37 b=100 |
| random_combo | 52 | 52 | 0.0% | 3.8% | +0.127 | mkt_mean ema_dist 1d n=8 OR rank dd 8h n=41 OR self rsi 4h n=80 |
| combo2 | 276 | 276 | 0.0% | 0.0% | +0.126 | mkt_mean efficiency 8h n=19 OR self ma_cross 1d a=89 b=100 |
| random | 333 | 283 | 0.0% | 0.4% | +0.114 | self dd 2h n=444 |
| band | 41 | 25 | 0.0% | 0.0% | +0.111 | self ma_cross 1d a=89 b=100 |
| combo3 | 110 | 110 | 0.0% | 0.0% | +0.096 | self rsi 4h n=80 OR self rsi 4h n=70 OR self ma_cross 1d a=3 b=13 |
| ma_scan | 477 | 457 | 0.0% | 0.0% | +0.089 | self sma_dist 4h n=133 |
| rsi | 478 | 432 | 0.0% | 0.0% | +0.086 | self rsi 4h n=80 |
| indicators | 137 | 121 | 0.0% | 0.0% | +0.071 | self ema_dist 1d n=21 |
| macd | 478 | 460 | 0.0% | 0.0% | +0.047 | btc macd 1h a=3 b=21 sig=5 |
| daily | 21 | 12 | 0.0% | 0.0% | +0.014 | daily stablecoin_supply n=7 chg |
| half | 42 | 42 | 0.0% | 0.0% | +0.009 | mkt_disp ema_dist 4h n=20 |
| data | 1 | 1 | 0.0% | 0.0% | +0.006 | breadth |
| funding | 5 | 5 | 0.0% | 0.0% | +0.004 | funding n=21 |
| macro | 8 | 4 | 0.0% | 0.0% | +0.000 | macro ref_vix_chg20 |
| ml | 3 | 1 | 0.0% | 0.0% | +0.000 | learned validator on bank 'core' |
| calendar | 3 | 3 | 0.0% | 0.0% | -0.004 | cal hour |
| coin | 1 | 1 | 0.0% | 0.0% | -0.026 | coin |
| model | 1 | 1 | 0.0% | 0.0% | -0.061 | model |

### Best 25 (win or promising)

| gain | verdict | sig yrs | win rate | max DD | years | idea |
|---|---|---|---|---|---|---|
| +0.127 | promising | 1/4 | 51.8% (base 53.0%) | 17% | 22:+0%/0% 23:+12%/2% 24:+44%/17% 25:+81%/16% | mkt_mean ema_dist 1d n=8 OR rank dd 8h n=41 OR self rsi 4h n=80 |
| +0.127 | promising | 2/4 | 57.0% (base 53.0%) | 29% | 22:+0%/0% 23:+13%/3% 24:+63%/29% 25:+81%/16% | mkt_disp ema_dist 4h n=20 OR rank dd 8h n=41 |
| +0.032 | promising | 0/4 | 54.3% (base 53.0%) | 28% | 22:+0%/0% 23:+9%/3% 24:+21%/28% 25:+67%/16% | rank ema_dist 1h n=21 |
| +0.027 | promising | 0/4 | 54.2% (base 53.0%) | 28% | 22:+0%/0% 23:+9%/3% 24:+19%/28% 25:+65%/16% | rank ema_dist 1h n=25 |
| +0.025 | promising | 1/4 | 53.6% (base 53.0%) | 29% | 22:+0%/0% 23:+13%/3% 24:+15%/29% 25:+81%/16% | rank dd 8h n=41 |

### Moving averages 2-300: gain by period bucket (best n in bucket)

| source tf | 2-31 | 32-61 | 62-91 | 92-121 | 122-151 | 152-181 | 182-211 | 212-241 | 242-271 | 272-301 |
|---|---|---|---|---|---|---|---|---|---|---|
| self 1d | +0.054 (n=15) | +0.036 (n=38) | +0.026 (n=72) | -0.074 (n=99) | -0.130 (n=123) | -0.136 (n=169) | -0.104 (n=209) | -0.078 (n=238) | -0.066 (n=260) | +0.000 (n=281) |
| self 4h | -0.015 (n=3) | -0.064 (n=61) | -0.003 (n=75) | +0.062 (n=117) | +0.089 (n=133) | +0.068 (n=156) |  |  |  |  |

Period 37 (the operator's hunch): self 1d gain +0.032 (neutral); self 4h gain -0.134 (hurts)

### Plateaus: five neighbouring periods that ALL help (smallest gain of the five)

| min gain | feature | periods |
|---|---|---|
| +0.081 | self sma_dist 4h | 128-132 |
| +0.058 | self rsi 4h | 70-110 |
| +0.051 | self ema_dist 4h | 144-233 |
| +0.049 | self rsi 1h | 260-300 |
| +0.043 | self ema_dist 1d | 10-21 |
| +0.041 | self sma_dist 1d | 22-26 |
| +0.031 | self rsi 1d | 24-28 |
| +0.026 | mkt_below ema_dist 1d | 13-25 |
| +0.019 | btc rsi 1d | 55-59 |
| +0.010 | mkt_mean ema_dist 1d | 5-15 |
| +0.002 | rel ema_dist 1d | 10-21 |

### The ten ideas that help 2024 most (and what they do to the other years)

| 2024 ret/DD | all years | gain over 22-25 | idea |
|---|---|---|---|
| +80.5% / 20% | 22:+0%/0% 23:+9%/3% 24:+80%/20% 25:+64%/17% | +0.138 | mkt_disp ema_dist 4h n=20 |
| +75.1% / 24% | 22:+0%/0% 23:+3%/2% 24:+75%/24% 25:+37%/15% | +0.061 | self efficiency 8h n=119 |
| +69.8% / 20% | 22:+0%/0% 23:-0%/2% 24:+70%/20% 25:+64%/17% | +0.115 | mkt_disp ema_dist 4h n=21 |
| +70.3% / 22% | 22:+0%/0% 23:+9%/3% 24:+70%/22% 25:+64%/17% | +0.133 | btc ma_cross 1d a=37 b=100 |
| +68.1% / 22% | 22:+0%/0% 23:-0%/2% 24:+68%/22% 25:+64%/17% | +0.112 | mkt_disp ema_dist 4h n=15 |
| +60.7% / 10% | 22:+0%/0% 23:+0%/0% 24:+61%/10% 25:+64%/17% | +0.121 | self dd 2h n=444 OR self sma_dist 1d n=15 |
| +63.4% / 29% | 22:+0%/0% 23:+13%/3% 24:+63%/29% 25:+81%/16% | +0.127 | mkt_disp ema_dist 4h n=20 OR rank dd 8h n=41 |
| +59.1% / 22% | 22:+0%/0% 23:+9%/3% 24:+59%/22% 25:+56%/17% | +0.126 | btc ma_cross 1d a=37 b=89 |
| +53.0% / 10% | 22:+0%/0% 23:+0%/0% 24:+53%/10% 25:+64%/17% | +0.114 | self dd 2h n=444 |
| +52.2% / 10% | 22:+0%/0% 23:+0%/0% 24:+52%/10% 25:+64%/17% | +0.113 | rel roc 15m n=7 OR self dd 2h n=444 |

