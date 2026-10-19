# Phase 3b: market-neutral long/short on the phase 3 signal (2026-10-19)

**Verdict: FALSIFIED** by the criterion fixed before the run. On the worse seed set the bagged nested
curve 2022-2025 has Sharpe -0.06, and two of the four nested years have no eligible configuration.

Tool: `phase3b_longshort.py`. Results: `phase3b_results.json`. Funding: `fetch_funding.py` downloads
Binance USD-M history for the 32 PIT coins. CTXC, GXS, PEPE and SHIB never had a perpetual, so they are
never shorted.

Same predictions, honest execution and risk layer as phases 3-4. The book is long the top K and short
the bottom K, dollar neutral, gross 1 or 2. Shorts are perpetuals and earn or pay funding.

| median over the 72 configs | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| seed set 1 | -1.2% | +7.1% | -16.2% | -8.6% | +11.1% |
| seed set 2 | -3.4% | +6.1% | -19.2% | -14.5% | +7.9% |

| nested, bagging top 10 | 2022 | 2023 | 2024 | 2025 | total | Sharpe [p5, p95] | max DD |
|---|---|---|---|---|---|---|---|
| seed set 1 | +25.6% | -24.9% | cash | cash | -5.7% | -0.06 [-0.86, +0.78] | 31.6% |
| seed set 2 | +41.7% | -6.3% | +5.5% | cash | +40.0% | 0.57 [-0.21, +1.36] | 22.7% |

- Seed noise is median 10.5 points, the highest of all phases.
- Funding is small: -0.7% to +5.2% a year on the short leg.
- 12 (seed set 1) and 4 (seed set 2) of the 72 configurations are positive in every year 2022-2025.
  None holds DD <= 18% across 2021-2025 (the lowest is 18.5%).

## Reading

The ranking works in falling and flat markets (2022, 2025). It fails in the bull years 2023-2024,
when the coins it ranks worst rally hardest (alt squeezes). The positive IC of phase 3 is spread over the
whole cross-section. Its tails, which a K = 2-5 long/short book trades, are not reliable in a rally.
