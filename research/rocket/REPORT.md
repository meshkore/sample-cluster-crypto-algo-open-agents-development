# Rocket - report (auto, 2026-10-15T21:22:38+00:00)

Generated from `ledger.jsonl` by `rocket.py report`. Notes by hand: `JOURNAL.md`. Gain = selection-law score over 2022-25 with the validator minus without it (same champion, same book). Return/DD per year shown as `yy:ret/dd`.

## Universe: today

Baseline (release 34, no validator): law +0.270, max DD 24%, win rate 56.1%.

| | tested | win | promising | neutral | hurts | silent |
|---|---|---|---|---|---|---|
| real ideas | 842 | 0 | 0 | 36 | 421 | 385 |
| placebo (time-shifted) | 84 | 0 | 1 | 6 | 39 | 38 |

Chance rate: 0.0% of active placebo ideas 'win' and 2.2% are win-or-promising; real ideas: 0.0% and 0.0%. A family is only interesting where it clearly beats the placebo.

| family | tested | active | win % | win-or-promising % | best gain | best idea |
|---|---|---|---|---|---|---|
| engine44 | 44 | 36 | 0.0% | 0.0% | +0.036 | x bb_percent_b |
| random | 105 | 72 | 0.0% | 0.0% | +0.018 | rel vol 3d n=468 |
| coin | 1 | 1 | 0.0% | 0.0% | +0.011 | coin |
| daily | 21 | 9 | 0.0% | 0.0% | +0.005 | daily feargreed n=1 chg |
| ma_cross | 130 | 68 | 0.0% | 0.0% | +0.003 | self ma_cross 1d a=13 b=50 |
| cross_section | 92 | 16 | 0.0% | 0.0% | +0.001 | rank ema_dist 1d n=37 |
| rsi | 130 | 58 | 0.0% | 0.0% | +0.000 | self rsi 1d n=2 |
| macd | 130 | 129 | 0.0% | 0.0% | +0.000 | self macd 1d a=19 b=89 sig=13 |
| indicators | 38 | 21 | 0.0% | 0.0% | +0.000 | self ema_dist 1d n=2 |
| ma_scan | 129 | 28 | 0.0% | 0.0% | +0.000 | self sma_dist 1d n=2 |
| data | 1 | 0 | 0.0% | 0.0% | +0.000 | breadth |
| macro | 8 | 6 | 0.0% | 0.0% | +0.000 | macro ref_y10_chg20 |
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
| self 1d | +0.000 (n=2) | +0.000 (n=42) | +0.000 (n=62) | +0.000 (n=92) | +0.000 (n=122) |  |  |  |  |  |

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
| real ideas | 3 | 0 | 0 | 0 | 3 | 0 |
| placebo (time-shifted) | 1 | 0 | 0 | 0 | 1 | 0 |

Chance rate: 0.0% of active placebo ideas 'win' and 0.0% are win-or-promising; real ideas: 0.0% and 0.0%. A family is only interesting where it clearly beats the placebo.

| family | tested | active | win % | win-or-promising % | best gain | best idea |
|---|---|---|---|---|---|---|
| macd | 1 | 1 | 0.0% | 0.0% | -0.036 | self macd 4h a=8 b=26 sig=5 |
| rsi | 1 | 1 | 0.0% | 0.0% | -0.064 | self rsi 4h n=48 |
| ma_cross | 1 | 1 | 0.0% | 0.0% | -0.077 | self ma_cross 1d a=55 b=200 |

### Best 25 (win or promising)

| gain | verdict | sig yrs | win rate | max DD | years | idea |
|---|---|---|---|---|---|---|

### The ten ideas that help 2024 most (and what they do to the other years)

| 2024 ret/DD | all years | gain over 22-25 | idea |
|---|---|---|---|
| +3.3% / 33% | 22:+0%/0% 23:+5%/1% 24:+3%/33% 25:+64%/17% | -0.036 | self macd 4h a=8 b=26 sig=5 |
| -7.6% / 32% | 22:+0%/0% 23:+9%/3% 24:-8%/32% 25:+64%/17% | -0.064 | self rsi 4h n=48 |
| -9.2% / 33% | 22:+0%/0% 23:+7%/3% 24:-9%/33% 25:+64%/17% | -0.077 | self ma_cross 1d a=55 b=200 |

