# Decision surface — 2026-08-28

The operator's criteria, in force: **minimum +30% per calendar year** (mandate, this
date); **balance** — when extra gain is proportional to extra drawdown, take the
smallest/most balanced drawdown; deep drawdown only for disproportionate gain;
drawdown is REPORTED, never silently enforced.

All figures measured on the SHIPPED champion net through the promotion path
(`launch.per_year`, research years 2018–2025). 2026 is sealed: it has been read
ONCE, for the balanced configuration only (see `sealed_readouts.jsonl`); the
two-book combine has NOT consumed a sealed look — that happens at adoption.

## The three candidates

| Year | A. Baseline (ships today) | dd | B. Balanced (money 0.5 + ceiling 0.50 + cap 0.50) | dd | C. Balanced + 30% capitulation sleeve (monthly rebalance, cash-capped) | dd |
|---|---|---|---|---|---|---|
| 2018 | +20.5% | 18.2% | +32.8% | 22.5% | **+38.1%** | 19.8% |
| 2019 | +8.9% | 19.8% | +8.9% | 26.1% | **+9.7%** | 24.3% |
| 2020 | +14.3% | 12.1% | +37.8% | 16.7% | **+39.3%** | 19.3% |
| 2021 | +281.5% | 11.7% | +1022.5% | 17.4% | **+1136.2%** | 11.0% |
| 2022 | +5.9% | 2.7% | +12.3% | 5.3% | **+15.6%** | 3.3% |
| 2023 | +8.4% | 8.9% | +19.3% | 14.6% | **+22.5%** | 10.9% |
| 2024 | +14.0% | 8.6% | +28.0% | 15.9% | **+28.4%** | 15.7% |
| 2025 | +3.8% | 6.2% | +5.1% | 12.6% | **+8.1%** | 8.3% |
| 2026 sealed (to date) | +4.2% | 10.0% | +3.9% | 19.0% | *not read — reserved for adoption* | — |

Consistency score: A +0.0675 · B +0.1095 · C not scored by the ledger metric
(different accounting), but C dominates B in return in EVERY year and in drawdown
in 6 of 8.

## Why C is the recommendation

- **B over A** is the operator's balance criterion applied to the P11 efficiency
  table: money 0.5 is the 4× efficiency outlier; ceiling 0.50/cap 0.50 is the
  moderate point of a proportional curve.
- **C over B** costs nothing it doesn't pay for: the capitulation book (system 07
  rule, entry 0.55–0.50 plateau, 63% win, robust to cost ×2) rides cash the trend
  book structurally never uses, so 2021 is not diluted — it is AMPLIFIED (+113.8pp)
  while its drawdown nearly halves (17.4% → 11.0%), because the bounce-buyer earns
  inside the very crashes that draw the trend book down. Feasibility measured with
  a pessimistic worst-bar cash cap: it barely binds (r_m 88–100%).

## Honest gaps and caveats — read before adopting

1. **The 30% floor is NOT met.** C's worst years: 2019 +9.7%, 2025 +8.1%, 2022
   +15.6%. The remaining gap belongs to GENERATION (P15 market features — on the
   GPU now; A60 path-true labels; A62 1h book) and to a smarter capitulation book
   (its sizing is naive equal-fraction today). No filter or sizing setting can
   close it — P13 proved that road is shut.
2. **2026 sealed says sizing needs edge**: B read +3.9% @ 19.0% dd vs A's +4.2% @
   10.0% — this year's trades are near zero-edge, so sizing multiplies risk, not
   return. Expect C's sealed readout to show the same character on the trend side;
   its sleeve is untested on 2026 by design.
3. Backtest maximum drawdown never promises the live tail stops there; edge-sailing
   configs generalise worse (measured in this repo).
4. Thin years hang on few trades (2022: 34 in the trend book) — fragility jackknife
   applies to every number above.
5. C requires live-path engineering that does not exist yet (two-book orchestration,
   monthly rebalance, cash-capped sleeve, tests). B is adoptable today by config.

## If adopted

Full honest treatment in one pass: re-derive the bar through the same measurement
path, risk_grid update, model card, strategy.json, dashboard, rolling reliability
on the true config, and the ONE sealed readout for C recorded in
`sealed_readouts.jsonl`.
