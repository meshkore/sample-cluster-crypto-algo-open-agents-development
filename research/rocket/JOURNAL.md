# Rocket — journal (by hand)

## 2026-10-15
- Opened on the operator's request. Champion = release 34 on frozen signals; baseline law 0.270
  reproduces the release exactly.
- Smoke tests (today's 14): MA 37 on 1d hurts (−0.011), BTC MACD 4h neutral (+0.003), VIX,
  fear & greed, 4-hour block, funding and NATR all hurt, the learned validator hurts (−0.112).
  Pattern already visible: rules fitted on past losers deny whole regimes in the next year
  (VIX denied 94% of 2023, fear & greed 98% of 2022). That is why ≥ 50 trades a year is required
  for a positive verdict.
- On today's 14, 2024 and 2025 are the champion's best years, so a validator mostly moves 2022-23.
  The 2024 losses the operator asked about live on the point-in-time list: that cache is built
  next and every idea runs there too.

## 2026-10-15, first hour (842 real tests + 84 placebos, today's 14)
- Point-in-time cache built in 56 min; its baseline reproduces the earlier re-booking exactly
  (2022 0 / 2023 +8.9% / 2024 +12.1% / 2025 +63.6%). Every idea now also runs there.
- Today's 14: 0 wins, 0 promising among real ideas; the placebo produced 1 promising. Nothing
  beats chance yet. 46% of ideas are silent: no rule held in two thirds of the training years.
- Best single gains are small and lone: Bollinger %b +0.036, a 3-day relative-volatility random
  idea +0.018. MA 37 on 1d hurts (-0.011). On today's 14 the champion's 2024 is already +80%, so
  nothing here can "fix" 2024: that question is answered on the point-in-time list only.
- Reading so far: the champion's losing trades do not share a simple, stable condition that
  the previous years could have revealed. Combos start once singles reach "promising".

## 2026-10-15 23:50 local - grading fix, two new rule types
- Point-in-time 2022 has 0 trades without any validator (the take-bar admits nothing), so the
  old "≥ 50 trades every year" made a positive verdict impossible on that list. Grading now
  counts only years where something traded, and asks each year to keep ≥ 50 trades or the
  champion's own count if lower. Ledger re-graded: no verdict changed.
- Long RSI on 4h (n = 70..130) on the point-in-time list: 2024 +12% → +37%, DD 32% → 23%, at
  every neighbouring period. But it fires only in 2024 (trained on 2020-23); 2023 and 2025 are
  untouched. One year of evidence = neutral, correctly. Watch whether it holds as a plateau.
- Same rule as HALF stake instead of denial: 2024 +5%, DD 32% (worse than doing nothing). As a
  TAILS band: worse still. The denial helps by FREEING SLOTS for better entries, not by
  dodging losers. A validator here is really a slot allocator.
- Added: rule "band" (deny both extremes), action "half" (soft validator), a plateau table in
  the report, and leaders that include the best neutral ideas so variants/combos start now.
