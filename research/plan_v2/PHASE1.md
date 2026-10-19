# Phase 1: alpha or only beta? (2026-10-19)

**Verdict: FALSIFIED.** The residual alpha against the equal-weight PIT basket (b) has t < 2 on every
series: the best is t = 1.41 (release 48, base execution, seed set 1). On the nested curve the worse seed
set gives t = 0.48. The nested strategy does not beat the naive rule (c) or its momentum variant (d) in
Sharpe with any confidence. By the plan, the MLPs add nothing measurable, and phase 3 starts with the
simple rule as the base.

Tool: `phase1_alpha.py`. Results: `phase1_results.json`. Daily series, PIT, same 0.30% round trip on the
benchmarks' turnover. Newey-West t-stats (10 lags); Sharpe differences use a paired 10-day block bootstrap.

## Benchmarks (PIT, return / Sharpe)

| year | a: BTC buy and hold | b: EW PIT basket | c: b when BTC > MA100 | d: c + x2 top-7 momentum |
|---|---|---|---|---|
| 2022 | -64.2% / -1.29 | -60.9% / -0.74 | -20.2% / -1.03 | -21.3% / -1.18 |
| 2023 | +155.6% / 2.35 | +91.3% / 1.55 | +55.1% / 1.18 | +62.6% / 1.27 |
| 2024 | +121.3% / 1.76 | +53.8% / 0.97 | +28.6% / 0.72 | +20.6% / 0.61 |
| 2025 | -6.3% / 0.05 | -41.4% / -0.38 | -20.1% / -0.19 | -22.9% / -0.27 |

## Strategy vs benchmarks

| series | alpha vs b, annual (t) | beta vs b | Sharpe | Sharpe minus c [p5, p95] | P(diff <= 0) vs c |
|---|---|---|---|---|---|
| nested, seed set 1, base | +4.6% (0.48) | 0.11 | 0.51 | -0.05 [-1.05, +0.94] | 0.53 |
| nested, seed set 2, base | +12.8% (1.30) | 0.11 | 0.94 | +0.38 [-0.68, +1.47] | 0.29 |
| nested, seed set 1, all frictions | -6.1% (-0.86) | 0.10 | -0.15 | -0.70 [-1.74, +0.31] | 0.87 |
| nested, seed set 2, all frictions | -8.6% (-1.35) | 0.12 | -0.27 | -0.82 [-1.73, +0.08] | 0.94 |
| r48 2022-25, seed set 1, base | +16.1% (1.41) | 0.10 | 0.84 | +0.48 [-0.66, +1.59] | 0.25 |
| r48 2022-25, seed set 2, base | +4.0% (0.42) | 0.09 | 0.28 | -0.12 [-1.10, +0.93] | 0.58 |

Nested series cover 2023-2025, where benchmark c has Sharpe 0.56 and d 0.53. Release 48 covers 2022-2025.

## Reading

- The strategy is mostly in cash: beta to the basket is 0.1 and correlation 0.3-0.5. Its returns are not
  a levered market. They are also not separable from zero: every alpha t-stat is under 1.5.
- With honest execution (phase 0, "all") the strategy is below every benchmark's Sharpe on both seed sets.
- The naive rule (c) is no winner either: it loses 20% in 2022 and in 2025. It is the base phase 3 must
  beat, not a candidate.

## Not done

Item 3 also asks for the 2026 comparison. That needs the sealed-2026 world (a read, never a selection).
It is left for the operator's go, because 2026 readings are rationed.
