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

## 2026-10-16 05:30 UTC - night 1 (7,600 tests) and a flaw in my own score
- Night 1: 13 ideas reached "promising". Against the placebo: today's 14 real 0.36% vs placebo
  0.38% (chance); point-in-time 0.17% vs 0.00% of 330 placebos (too few to separate).
- The point-in-time "plateau" (price vs its 4h average 128-233, RSI 4h 70-110: 2024 +12% → +37%)
  was an ARTIFACT. RSI 4h 80 was learned with opposite sides in two runs and both "helped". v1
  scored a rule by minus the denied trades' summed return; where the champion lost money in the
  training years (point-in-time 2020-23) denying ANY half looked good. In 2024 those rules denied
  78-88% of entries: "trade less in a bad year", no information in the feature.
- Fix (rule v2): score = denied trades measured against that year's AVERAGE trade (a denied
  entry frees a slot for an average one). Denying a random half now scores ~0. Under v2 both
  plateaus are silent: no stable below-average subset exists.
- The one v2 survivor on point-in-time (cross-sectional rank of the 8h drawdown, n=41: deny the
  coins nearest their highs) does NOT replicate: on today's 14 it learns the opposite side and
  hurts at n = 34..50 (−0.10 to −0.12); on point-in-time n=45 hurts and n=50 flips side. Noise.
- Ledger v1 archived as `ledger_v1.jsonl` (+ `REPORT_v1.md`); everything re-runs under v2.
- New rule of thumb for this lab: a validator counts only if it (1) beats the placebo rate as a
  family, (2) keeps its side across neighbouring periods, (3) replicates on the other coin list.
- Caveat on combos/half/band: their members are leaders picked on the same 2022-25 years, so
  their gains carry selection bias; they need the three checks above even more.

## 2026-10-16 17:40 UTC - day 1 under rule v2 (6,496 tests, 3,288 ideas, 650 placebos)
- Promising rate vs placebo: today's 14 real 22 / 3,232 active (0.68%) vs placebo 0 / 322;
  point-in-time 29 / 2,810 (1.03%) vs placebo 4 / 318 (1.26%) = chance.
- First idea to replicate on both lists: `rank kurt 1h n=7 OR mkt_disp autocorr 2h n=419`
  (+0.107 today, +0.132 point-in-time). It does NOT survive scrutiny:
  - the autocorrelation half is a lucky period: n=300 hurts both lists, n=360 hurts PIT;
  - the kurtosis half alone is a spike at n=7: n=6 and n=9 hurt on both lists, n=7 on 30m and
    2h hurts, and its time-shifted placebo scores as well on PIT (+0.031 promising).
- So replication on two lists is necessary, not sufficient. Rocket now tests every replicated
  idea's NEIGHBOURS automatically (nearby periods, adjacent timeframes, each combo member in
  turn) and the report shows how many hold on both lists. Combos pass rebuilt hourly.
- Also fixed: the report crashed when a combo replicated (its rule is a list), which had hidden
  this result from the watch for hours.
