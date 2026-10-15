# Rocket - report (auto, 2026-10-15T22:53:52+00:00)

Generated from `ledger.jsonl` by `rocket.py report`. Notes by hand: `JOURNAL.md`. Gain = selection-law score over 2022-25 with the validator minus without it (same champion, same book). Return/DD per year shown as `yy:ret/dd`.

## Universe: today

Baseline (release 34, no validator): law +0.270, max DD 24%, win rate 56.1%.

| | tested | win | promising | neutral | hurts | silent |
|---|---|---|---|---|---|---|
| real ideas | 1067 | 0 | 0 | 40 | 518 | 509 |
| placebo (time-shifted) | 112 | 0 | 1 | 6 | 57 | 48 |

Chance rate: 0.0% of active placebo ideas 'win' and 1.6% are win-or-promising; real ideas: 0.0% and 0.0%. A family is only interesting where it clearly beats the placebo.

| family | tested | active | win % | win-or-promising % | best gain | best idea |
|---|---|---|---|---|---|---|
| random_combo | 2 | 1 | 0.0% | 0.0% | +0.037 | self pos 15m n=19 OR self rsi 4h n=70 OR x bb_percent_b |
| engine44 | 44 | 36 | 0.0% | 0.0% | +0.036 | x bb_percent_b |
| random | 138 | 91 | 0.0% | 0.0% | +0.018 | rel vol 3d n=468 |
| coin | 1 | 1 | 0.0% | 0.0% | +0.011 | coin |
| daily | 21 | 9 | 0.0% | 0.0% | +0.005 | daily feargreed n=1 chg |
| ma_cross | 165 | 94 | 0.0% | 0.0% | +0.003 | self ma_cross 1d a=13 b=50 |
| cross_section | 117 | 21 | 0.0% | 0.0% | +0.001 | rank ema_dist 1d n=37 |
| rsi | 166 | 66 | 0.0% | 0.0% | +0.000 | self rsi 1d n=2 |
| macd | 166 | 165 | 0.0% | 0.0% | +0.000 | self macd 1d a=19 b=89 sig=13 |
| indicators | 48 | 27 | 0.0% | 0.0% | +0.000 | self ema_dist 1d n=2 |
| ma_scan | 165 | 28 | 0.0% | 0.0% | +0.000 | self sma_dist 1d n=2 |
| data | 1 | 0 | 0.0% | 0.0% | +0.000 | breadth |
| macro | 8 | 6 | 0.0% | 0.0% | +0.000 | macro ref_y10_chg20 |
| half | 6 | 0 | 0.0% | 0.0% | +0.000 | self rsi 4h n=80 |
| band | 6 | 0 | 0.0% | 0.0% | +0.000 | self rsi 4h n=80 |
| ml | 4 | 4 | 0.0% | 0.0% | -0.001 | learned validator on bank 'x44' |
| calendar | 3 | 3 | 0.0% | 0.0% | -0.006 | cal hour |
| funding | 5 | 5 | 0.0% | 0.0% | -0.007 | funding n=3 |
| model | 1 | 1 | 0.0% | 0.0% | -0.030 | model |

### Best 25 (win or promising)

| gain | verdict | sig yrs | win rate | max DD | years | idea |
|---|---|---|---|---|---|---|

### Moving averages 2-300: gain by period bucket (best n in bucket)

| source tf | 2-31 | 32-61 | 62-91 | 92-121 | 122-151 | 152-181 | 182-211 | 212-241 | 242-271 | 272-301 |
|---|---|---|---|---|---|---|---|---|---|---|
| self 1d | +0.000 (n=2) | +0.000 (n=42) | +0.000 (n=62) | +0.000 (n=92) | +0.000 (n=122) | +0.000 (n=152) |  |  |  |  |

Period 37 (the operator's hunch): self 1d gain -0.011 (hurts)

### The ten ideas that help 2024 most (and what they do to the other years)

| 2024 ret/DD | all years | gain over 22-25 | idea |
|---|---|---|---|
| +83.0% / 24% | 22:+32%/17% 23:+19%/5% 24:+83%/24% 25:+35%/23% | -0.016 | self ma_cross 1d a=20 b=37 |
| +83.0% / 24% | 22:+34%/17% 23:+19%/5% 24:+83%/24% 25:+35%/23% | -0.013 | self ma_cross 1d a=21 b=37 |
| +82.7% / 24% | 22:+43%/17% 23:+17%/5% 24:+83%/24% 25:+35%/23% | -0.007 | mkt_disp ema_dist 1d n=10 |
| +82.7% / 24% | 22:+44%/17% 23:+17%/5% 24:+83%/24% 25:+35%/23% | -0.006 | mkt_disp ema_dist 1d n=13 |
| +82.7% / 24% | 22:+42%/17% 23:+17%/5% 24:+83%/24% 25:+35%/23% | -0.009 | mkt_disp ema_dist 1d n=15 |
| +81.9% / 24% | 22:+44%/17% 23:+19%/5% 24:+82%/24% 25:+35%/23% | +0.003 | self ma_cross 1d a=13 b=50 |
| +80.8% / 23% | 22:+43%/17% 23:+19%/5% 24:+81%/23% 25:+35%/23% | +0.003 | self ma_cross 1d a=13 b=55 |
| +80.8% / 24% | 22:+50%/8% 23:+18%/5% 24:+81%/24% 25:+7%/26% | -0.108 | macro ref_dxy_chg20 |
| +80.4% / 24% | 22:+43%/17% 23:+19%/5% 24:+80%/24% 25:+35%/23% | +0.000 | self rsi 1d n=2 |
| +80.4% / 24% | 22:+33%/13% 23:+13%/3% 24:+80%/24% 25:+35%/23% | -0.039 | self macd 1d a=3 b=13 sig=5 |

## Universe: pit

Baseline (release 34, no validator): law +0.072, max DD 32%, win rate 53.0%.

| | tested | win | promising | neutral | hurts | silent |
|---|---|---|---|---|---|---|
| real ideas | 289 | 0 | 0 | 42 | 211 | 36 |
| placebo (time-shifted) | 26 | 0 | 0 | 7 | 18 | 1 |

Chance rate: 0.0% of active placebo ideas 'win' and 0.0% are win-or-promising; real ideas: 0.0% and 0.0%. A family is only interesting where it clearly beats the placebo.

| family | tested | active | win % | win-or-promising % | best gain | best idea |
|---|---|---|---|---|---|---|
| rsi | 47 | 47 | 0.0% | 0.0% | +0.086 | self rsi 4h n=80 |
| random | 33 | 28 | 0.0% | 0.0% | +0.063 | self dd 8h n=82 |
| ma_cross | 46 | 29 | 0.0% | 0.0% | +0.059 | self ma_cross 1d a=3 b=13 |
| cross_section | 31 | 23 | 0.0% | 0.0% | +0.046 | mkt_mean ema_dist 1d n=89 |
| indicators | 14 | 14 | 0.0% | 0.0% | +0.026 | btc ema_dist 1d n=2 |
| random_combo | 1 | 1 | 0.0% | 0.0% | +0.015 | self rsi 4h n=220 OR self rsi 4h n=140 |
| data | 1 | 1 | 0.0% | 0.0% | +0.006 | breadth |
| macro | 8 | 4 | 0.0% | 0.0% | +0.000 | macro ref_vix_chg20 |
| ml | 3 | 1 | 0.0% | 0.0% | +0.000 | learned validator on bank 'core' |
| ma_scan | 45 | 45 | 0.0% | 0.0% | -0.005 | self sma_dist 1d n=2 |
| band | 6 | 6 | 0.0% | 0.0% | -0.011 | self rsi 4h n=70 |
| half | 6 | 6 | 0.0% | 0.0% | -0.017 | self rsi 4h n=70 |
| macd | 47 | 47 | 0.0% | 0.0% | -0.021 | self macd 4h a=8 b=34 sig=13 |
| model | 1 | 1 | 0.0% | 0.0% | -0.061 | model |

### Best 25 (win or promising)

| gain | verdict | sig yrs | win rate | max DD | years | idea |
|---|---|---|---|---|---|---|

### Moving averages 2-300: gain by period bucket (best n in bucket)

| source tf | 2-31 | 32-61 | 62-91 | 92-121 | 122-151 | 152-181 | 182-211 | 212-241 | 242-271 | 272-301 |
|---|---|---|---|---|---|---|---|---|---|---|
| self 1d | -0.005 (n=2) |  |  |  | -0.131 (n=148) | -0.137 (n=157) |  |  |  |  |

### Plateaus: five neighbouring periods that ALL help (smallest gain of the five)

| min gain | feature | periods |
|---|---|---|
| +0.058 | self rsi 4h | 70-110 |

### The ten ideas that help 2024 most (and what they do to the other years)

| 2024 ret/DD | all years | gain over 22-25 | idea |
|---|---|---|---|
| +75.1% / 24% | 22:+0%/0% 23:+3%/2% 24:+75%/24% 25:+37%/15% | +0.061 | self efficiency 8h n=119 |
| +37.3% / 23% | 22:+0%/0% 23:+9%/3% 24:+37%/23% 25:+64%/17% | +0.086 | self rsi 4h n=80 |
| +37.3% / 25% | 22:+0%/0% 23:+0%/0% 24:+37%/25% 25:+64%/17% | +0.059 | self ma_cross 1d a=3 b=13 |
| +35.2% / 24% | 22:+0%/0% 23:+9%/3% 24:+35%/24% 25:+64%/17% | +0.079 | self rsi 4h n=70 |
| +31.0% / 8% | 22:+0%/0% 23:+0%/0% 24:+31%/8% 25:+64%/17% | +0.063 | self dd 8h n=82 |
| +33.4% / 23% | 22:+0%/0% 23:+9%/2% 24:+33%/23% 25:+64%/17% | +0.078 | self rsi 4h n=110 |
| +32.9% / 23% | 22:+0%/0% 23:+8%/2% 24:+33%/23% 25:+64%/17% | +0.073 | self rsi 4h n=130 |
| +31.1% / 23% | 22:+0%/0% 23:+9%/2% 24:+31%/23% 25:+64%/17% | +0.071 | self rsi 4h n=120 |
| +27.9% / 22% | 22:+0%/0% 23:+8%/2% 24:+28%/22% 25:+64%/17% | +0.063 | self rsi 4h n=200 |
| +27.3% / 23% | 22:+0%/0% 23:+9%/2% 24:+27%/23% 25:+64%/17% | +0.063 | self rsi 4h n=100 |

