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

## 2026-10-17 05:50 UTC - day 2: 6,092 ideas, 12,101 tests, 1,889 placebos (rule v2)
- **Single ideas carry no information.** Primary families (every MA 2-300, RSI, MACD, crosses,
  13 indicators, cross-section, macro, funding, fear & greed, OI, calendar, engine columns, ML,
  random): today's 14 0.45% promising vs placebo 0.43% (z +0.2); point-in-time 0.34% vs 1.53%
  (below chance). No primary idea has ever reached "win".
- The apparent 3x edge came entirely from DERIVED ideas (combos, half, band, neighbours of
  leaders: 10-17% promising). Their members are leaders chosen on the same 2022-25 years they
  are graded on: selection bias. The report now runs the evidence test on primary ideas only
  and labels derived ones as follow-up, never as evidence. That includes the kurtosis /
  autocorrelation combo whose neighbours hold 8/12: built from leaders, so not evidence.
- Reading: the champion's entries cannot be told apart, at entry, by anything Rocket can
  measure, as of 2022-25. A validator that denies entries is not where its edge can improve.
  Rocket keeps running (random and new families), but the honest expectation is now low.

## 2026-10-17 17:45 UTC - day 2 close
- Ledger 21,344 rows. Primary ideas vs placebo: z = -2.9 (today's 14), -5.3 (point-in-time): BELOW chance on both. No primary win ever. Rocket keeps running; nothing to report to the main line.

## 2026-10-18 05:47 UTC - day 3 close
- Ledger 28,297 rows. Primary z = +0.2 (today's 14), -4.1 (point-in-time). Still chance or below; no primary win.

## 2026-10-18 10:30 UTC - two sizing families (operator's request)
- **martingale** (117 ideas): stake x base^k after k losses in a row (classic), after k wins
  (anti-martingale) or / base^k after losses (defend); base 1.25/1.5/2, k <= 1..3, cap 2-3x,
  and the risk limit: no increase while the account is more than 8% / 15% below its high.
  Placebo = the same rule on a shuffled win/loss sequence.
- **conviction** (64 ideas): score = share of bullish conditions holding at the bar (price above
  the 50/100/200-day MAs, 50-day slope up, RSI 50-70, BTC above 200, 4h trend, most coins above
  their 50-day, breadth, the model's forecast >= 2x the entry bar); bigger stake when the score
  is high (top / linear / split mappings). Placebo = the conditions shifted in time.
- Both act through the book's per-bar stake multiplier; no System 10 code touched. Every sizing
  idea runs with its own placebo.
- Smoke test (release 34, gain in law): classic martingale hurts on both lists (-0.038 / -0.026);
  anti-martingale +0.057 on today's 14 but -0.016 point-in-time; conviction (operator's set, x1.5
  when all hold) -0.016 / +0.013. Full results in REPORT.md as they come.

## 2026-10-18 10:40 UTC - the miner (operator: "find which criteria the winning trades had, and size up when they hold")
- 76 parameters measured at every entry of the champion (trend vs 10-200 MAs on 1h/4h/1d, slopes,
  returns 1-90 d, RSI, MACD, volatility, drawdowns, range position, variance ratio, skew,
  kurtosis, autocorrelation, efficiency, BTC, relative strength, cross-sectional ranks, market
  breadth/dispersion, VIX, Nasdaq, dollar, oil, 10-year, curve, funding, fear & greed, open
  interest, hour, weekday, the model's forecast). Tables cached (today 0.8 min, PIT 3.6 min).
- Two searchers, nested (learned on trades of years < N, applied to N as x boost inside / x cut
  outside): a RULE miner (each parameter by quintile, pairs of the 15 best by tercile, regions
  ranked by a stable t-score of the excess return) and an ML regressor (gradient boosting on all
  76, leave-one-year-out threshold). Placebo = returns shuffled among the training trades.
  Endless: random subsets of 8-30 parameters, forever.
- First result, the core answer: the miner ALWAYS finds criteria that separate winners in the
  past (inside 63-75% win vs outside 37-54%) and the next year the relation is gone or REVERSED:
  2022 51% in vs 60% out, 2023 62 vs 76, 2024 58 vs 63, 2025 44 vs 53 (today's 14); the same on
  point-in-time. The ML version held once (2025: 61% vs 50%, 171 trades). Law gains: rules
  +0.007 / -0.015, ML -0.033 / silent; placebos similar.

## 2026-10-18 - sizing verdicts (martingale, conviction, miner)

All three sizing families finished on both coin lists, each idea with its placebo.

| family | today's 14: real improve / placebo improve (best) | PIT: real / placebo (best) |
|---|---|---|
| martingale | 69/126 vs 57/127 (+0.136 vs +0.116) | 17/126 vs 20/127 (+0.006 vs +0.029) |
| conviction | 20/104 vs 57/105 (+0.020 vs +0.074) | 64/104 vs 24/105 (+0.021 vs +0.020) |
| miner (rules + ML) | 16/44 vs 16/44 (+0.050 vs +0.062) | 4/44 vs 5/44 (+0.016 vs +0.008) |
| miner_random | 8/16 vs 6/16 (+0.052 vs +0.066) | 1/16 vs 3/16 (+0.015 vs +0.011) |

- Anti-martingale (size up after wins) has the best gain on today's list (+0.136), but it lifts the DD to 27%
  (cap 25%), a placebo reaches +0.116, and it is flat on the PIT list. Not real.
- Conviction "with_model" beats its placebo by rate on PIT only (64 vs 24), but its gains are +0.02 and it loses
  to the placebo on today's list. It does not replicate. Follow-up list only.
- Miner: the criteria found in the past win 60-73% inside vs 40-55% outside. The next year the inside group wins
  the same as or less than the outside group (e.g. 2025 PIT: 40% vs 47%). Past hit-rate pockets do not persist.
- Conclusion: no sizing rule built from the champion's own past trades beats chance on both lists. What is
  knowable at entry does not separate winners from losers beyond what the selector already uses.
  miner_random keeps searching.
