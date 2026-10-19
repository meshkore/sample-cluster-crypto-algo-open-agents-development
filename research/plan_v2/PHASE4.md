# Phase 4: portfolio risk layer (2026-10-19)

**Verdict: NOT FALSIFIED.** On the phase 3 pipeline (72 configurations, both seed sets), volatility-
target sizing with a book risk budget and correlation-cluster caps cuts the tail drawdown and raises the
net return. The plan keeps the risk layer. It is not enough to make a system:
- No configuration holds DD <= 18% in every year (the lowest is 20%).
- The nested selection on the worse seed set loses 13.6% over 2022-2025.

Tool: `phase4_risk.py`. Results: `phase4_results.json`.

Rules (fixed, not searched):
- each held coin carries 1% daily risk (w = 1% / sigma_60d), at most 1.5 slots;
- book volatility (90-day covariance) <= 2% a day;
- coins with correlation > 0.85 form one group, capped at 40% of the book;
- no leverage;
- weights are refreshed daily or when the held set changes.

| median over the 72 configs | seed set 1 base | seed set 1 risk | seed set 2 base | seed set 2 risk |
|---|---|---|---|---|
| tail DD (max over 2021-2025) | 59.4% | **43.5%** | 59.9% | **43.2%** |
| tail DD p90 | 74.2% | 51.2% | 71.8% | 50.2% |
| net 2022-2025 | -3.9% | **+12.8%** | -5.4% | **+10.8%** |
| stress DD (BTC -20%, alts -35%, spreads x3, exits 2% worse) | 79.5% | 65.5% | 79.6% | 65.5% |
| seed noise, median points | 8.5 | **5.1** | | |

## Nested selection with the risk layer (bagging top 10)

| seed set | 2022 | 2023 | 2024 | 2025 | total | Sharpe [p5, p95] | max DD |
|---|---|---|---|---|---|---|---|
| 1 | -13.6% (20 eligible) | cash (0 eligible) | cash | cash | -13.6% | -0.63 [-1.27, +0.27] | 20.8% |
| 2 | -14.3% (22 eligible) | +49.3% (1 eligible) | +50.5% (1 eligible) | cash | +92.5% | 0.82 [-0.10, +1.73] | 30.7% |

The 18% constraint is binding. The configurations calm enough in 2021 all lose about 14% in 2022 and are
ineligible from then on. Seed set 2's +92% is one surviving configuration (1d, H 7d, K 3, GBM, gated)
picked twice. That is luck of eligibility, not a robust selection.

## Phase 5 item 1, applied now: how long would a forward test take?

To show at 2 sigma that a Sharpe S is above zero, a forward test needs about (2 x sqrt(365) / S)^2
daily observations:

| Sharpe | days | years |
|---|---|---|
| 0.5 | 5,840 | 16.0 |
| 1.0 | 1,460 | 4.0 |
| 1.5 | 649 | 1.8 |
| 2.0 | 365 | 1.0 |

Our best honest numbers:
- seed set 2 bagged with the risk layer: Sharpe 0.82, so 2,187 days (6 years);
- the old system, nested, base execution: Sharpe 0.51-0.94, so 1,663-5,613 days;
- the old system with every friction: a negative Sharpe, so never.

The plan's limit (n > 2,000 is too small to validate) is exceeded by every candidate we have.

## Where this leaves the plan

- The cross-sectional signal is real (phase 3: out-of-sample IC t > 2 in 98 of 120 cells).
- Long-only books of 3-8 coins cannot hold an 18% DD through 2021-2022 with it, even risk-sized.
- No candidate exists for phase 5. The prospective window keeps running untouched.
