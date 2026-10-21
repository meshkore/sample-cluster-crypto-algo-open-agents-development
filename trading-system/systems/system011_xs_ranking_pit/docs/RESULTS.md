# System 11 - results

## Per calendar year (each year from the same capital; out of sample: models and choices from earlier years only)

| era | year | System 11 | max DD | at full size | BTC | all coins, equal weight |
|---|---|---|---|---|---|---|
| research | 2020 | +59% | 17% | +91% | +302% | +211% |
| research | 2021 | +96% | 11% | +132% | +60% | +324% |
| research | 2022 | -12% | 14% | -15% | -64% | -59% |
| research | 2023 | +38% | 13% | +54% | +156% | +97% |
| research | 2024 | +19% | 25% | +30% | +121% | +60% |
| research | 2025 | +7.8% | 7% | +15% | -6% | -40% |
| forward | 2026 YTD | +1.7% | 5% | +3.0% | -5% | -3% |

- 2020-2025: +30.2%/yr, Sharpe 1.40, max DD 25%.
- Configuration: `cap14-spot_long-xs-base-mlp`, exposure x0.45-0.79 per year to fit the 18% DD budget.
- Paper book: $50k from 2026-10-19, kept running as a yardstick (task `plan-v2-forward-ic`).

## Log of actions

| date | action | result |
|---|---|---|
| 2026-10-18 | Public review-request page (round 1) | two external reviews: no edge strong enough for capital |
| 2026-10-19 | Plan v2 phases 0, 1, 3, 3b, 4 | execution audit and alpha test falsified the old systems; a real but small cross-sectional IC (~0.05) survives |
| 2026-10-19 | Forward IC tracker; review brief round 2 | running every 4 h |
| 2026-10-20 | Endless lab (6 workers), controller, shadow paper book | 18 paper candidates; paper from 2026-10-19 |
| 2026-10-20 | Named System 11; full-history walk-forward; Live view | +30%/yr 2020-25, 2026 +1.5% |
| 2026-10-20 | Grid C: the "positive every year" law | 2025 fixed for perps; 2022 still about -14% everywhere |
| 2026-10-20 | Exit below EMA 20/50 (operator idea) | rejected: lowers return |
| 2026-10-21 | Rocket 11 (4,500 ideas vs placebo) | best picks no better than the median walk-forward |
| 2026-10-21 | Bayes 11 and Bayes 11 robust | no reliable gain walk-forward |
| 2026-10-21 | Exits 11 (stops, take profit, time) | no gain |
| 2026-10-21 | Classics 11 (16 published strategies) | none beats System 11; the plain BTC-gated basket matches it |
| 2026-10-21 | Review brief round 3 | published, then superseded by the System 12 brief |
| 2026-10-21 | CLOSED by the operator | everything moved to System 12 |
