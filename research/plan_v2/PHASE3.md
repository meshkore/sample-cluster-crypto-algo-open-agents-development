# Phase 3: selection redesign (2026-10-19)

**Verdict: FALSIFIED** under the plan's rule. Bagging plus the reduced space neither improves nested PIT
nor lowers the seed noise:
- Seed noise: median 8.5 points (old system 7.7).
- Nested PIT, worse seed set: -24.5% over 2022-2025 (old system with honest execution: -14.6%).
- The 18% DD constraint leaves no configuration eligible in any year, so the nested curve is cash on seed
  set 1 (0%) and one losing 2022 pick on seed set 2.

**Correction (2026-10-19, `ic_check.py`):** part of the IC below is an artefact. The target subtracts each
coin's own cost (ADV impact), which the features can read. Predictions correlate +0.2 to +0.55 with the
cost term alone. Against the GROSS forward return the IC is about half: 0.02-0.15, still t > 2 in most
years at 4h, weak at 1d. In sealed 2026 (`READINGS.md`) only the 4h / 1-day horizon survives: gross IC
0.05-0.06, t 2.5-2.8. The top-3 minus bottom-3 spread there is about 0 a day, far below cost.

**The original claim:** the single net-return model has a real out-of-sample
cross-sectional signal. Over 120 cells (timeframe x horizon x model x seed set x year 2021-2025), 98 have
an IC t-stat > 2 and only 5 have a negative IC. Median Spearman IC is 0.088 (t 5.0) at 4h and 0.060
(t 3.6) at 1d. It is there every year, including 2022 and 2025. It does not survive as a long-only book.

Tool: `phase3_select.py`. Results: `phase3_results.json`; the first run, whose book churned, is in
`phase3_results_v1_churn.json`.

## Design as run

- **Space:** 72 configurations.
  - Five levers: timeframe 4h / 1d, horizon 1 / 3 / 7 days, K 3 / 5 / 8, BTC > MA100 gate on / off,
    ridge / GBM.
  - Everything else fixed.
- **Model and target:** one model, the expected NET return of an entry (close t+1 to t+1+H, minus the
  0.45% round trip and twice the pair's impact). Four bagged fits per seed set. Walk-forward per year,
  label-end embargo.
- **Book:** honest execution as in phase 0: decide at t, fill at t+1, ADV impact, no stops.
  - It holds the top K with a positive prediction for H.
  - At expiry it extends a position while that coin is still in the top 2K.
- **Selection:** nested.
  - Score: p5 of the block-bootstrap Sharpe (the lower confidence bound) on the years 2021..N-1.
  - Constraint: DD <= 18%. No "every year positive" rule, no minimum trade count, cash allowed.
  - Picks compared: argmax vs bagging the top 10 / top 20.

## Why it fails

| median over the 72 configs (seed set 1) | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|
| net return | -34.5% | +47.3% | +21.7% | -16.4% |
| gross return | -22.6% | +78.5% | +58.0% | +0.1% |
| turnover (book traded per year) | 34x | 55x | 71x | 53x |
| max DD | 42% | 28% | 46% | 36% |

- **Beta.** A long-only book of 3-8 alts loses in 2022 and 2025 even with the gate. No configuration
  keeps DD <= 18% in 2021 (lowest 17.7%, and only one configuration). Since 2021 is in every past
  window, nothing is ever eligible.
- **Cost.** Holding for H cut turnover about 8x versus the first run (34-71x a year vs 400-700x). Costs
  still take 20-40 points a year: gross +58% becomes net +22% in 2024.
- **Seed noise is not lower.** Median 8.5 points (p90 35): the configurations are high-variance books.

Best configurations, net per year (for reading, not selection):

| configuration | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| 4h H1d K3 gbm gate, seed set 1 | -4% | -40% | +66% | +94% | +23% |
| same, seed set 2 | +47% | -25% | +132% | +90% | +5% |

Benchmarks on the same book: rule c 2022-2025 -23 / +53 / +8 / +1% (DD 60%); rule d -24 / +59 / +4 / -2%.

## What the evidence points to (operator's decision, not done)

The signal is cross-sectional: which coin beats the others. The losses come from the market direction
(beta) and from cost. Two things would harvest the IC without the beta, and neither is a new parameter:

1. **Market-neutral long/short** (perpetuals): long the top K, short the bottom K. It removes the
   2021/2022/2025 drawdowns the constraint rejects, and doubles the cost.
2. **Phase 4 risk layer** (in the plan): volatility-target sizing with a portfolio risk budget, and
   cluster limits, applied to this pipeline. It may bring DD under 18%.

Phase 4 is next by the plan, on this pipeline. Long/short changes the problem and needs the operator's go.
