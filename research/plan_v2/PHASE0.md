# Phase 0: execution and leakage audit (2026-10-19)

**Verdict: FALSIFIED** under the plan's rule. With fill at t+1 and a 0.45% round trip, the worse seed set
loses 56% of its nested PIT return (+59.1% -> +25.8%, 2023-2025 compounded). The other seed set does not
lose (+25.2% -> +28.8%). With every friction at once, both seed sets are negative.

Tool: `phase0_exec.py`. Results: `phase0_results.json`. PIT union world (32 coins, per-year membership),
both seed sets. Signals are computed exactly as `search.evaluate` does; only the execution changes. The
forked book reproduces the engine and the ledger exactly on all 14 jobs (`base_check`).

## Nested PIT selection, 2023-2025 (the system's honest curve)

Annualised return with its 10-day block-bootstrap p5 / p95 interval, and Sharpe with its interval.

| variant | seed set 1: total, ann [p5, p95] | Sharpe [p5, p95] | seed set 2: total, ann [p5, p95] | Sharpe [p5, p95] |
|---|---|---|---|---|
| base (same close, 0.30%) | +25.2%, +7.8% [-9.4, +26.7] | 0.51 [-0.47, 1.44] | +59.1%, +16.7% [-1.8, +38.4] | 0.94 [-0.01, 1.86] |
| cost 0.20% | +34.3% | 0.63 | +75.8% | 1.11 [0.16, 2.03] |
| cost 0.45% | +12.9% | 0.32 | +36.0% | 0.66 |
| cost 0.60% | +2.1% | 0.13 | +16.5% | 0.38 |
| cost 0.80% | -10.3% | -0.14 | -0.3% | 0.07 |
| fill close t+1 | +43.0% | 0.75 | +46.3% | 0.81 |
| intrabar stops, worst case | +16.4% | 0.38 | +23.3% | 0.47 |
| ADV impact + 0.30% | +5.8% | 0.20 | +24.4% | 0.50 |
| **falsify: t+1 + 0.45%** | **+28.8%** | 0.56 | **+25.8%** | 0.53 |
| all: t+1 + intrabar + 0.45% + ADV | -9.0%, -3.1% [-15.5, +10.3] | -0.15 [-1.08, 0.78] | -14.6%, -5.1% [-15.9, +6.3] | -0.27 [-1.06, 0.49] |

Per year, falsify: seed set 1 +8.4 / -8.0 / +29.1; seed set 2 +13.6 / -3.0 / +14.2. All frictions: seed set 1
+6.8 / -12.9 / -2.2; seed set 2 +11.5 / -16.1 / -8.7.

## Release 48 (paper book) on PIT, 2022-2025

| variant | seed set 1 total (worst year, max DD) | seed set 2 total (worst year, max DD) |
|---|---|---|
| base | +85.3% (-24.2%, 40%) | +14.9% (-27.4%, 37%) |
| falsify | +57.9% (-23.3%) | +6.5% (-32.5%) |
| all | -12.1% (-29.9%, 42%) | -21.0% (-37.2%, 44%) |

2024 loses 24-37% in every variant. On PIT, release 48 breaks the 25% DD cap even before frictions.

## What the numbers say

1. **The edge is not a same-bar artefact.** Filling one bar later changes single years by up to 30 points
   in either direction (2025 seed set 1: +4.7% -> +33.9%), but on average it does not hurt. Execution
   timing is noise of the same size as the edge.
2. **Cost is what kills it.** Break-even is a 0.6-0.8% round trip. Square-root impact on a $100k book adds
   0.01% per side on BTC and up to 0.39% on the 14th pair (HBAR, 2025). That alone takes seed set 1 from
   +25% to +6%.
3. **Even the base is not distinguishable from zero.** Its annualised p5 is below 0 on both seed sets.

## Checks 4 and 5: no leakage found

- **Embargo.** In every fold the selector drops the rows of N-2 whose 768-bar (8-day) label reaches N-1
  (5,376-10,752 rows). The exit model drops the rows of N-1 whose 96-bar label reaches N (1,248-1,344
  rows). No training label reads a price of the test year. Features are standardised on years <= 2020.
- **PIT.** For every year 2020-2025 the coins that trade equal that year's list exactly. Breadth is
  rebuilt over member coins only (`pit.breadth_members`). The gate's regime reads BTC, a member every year.
- **Open vs close.** A fill at the open of t+1 is the close of t to within 0.009% (median gap; p90 0.10%,
  p99 0.43%). "Open t+1" is the base case; "close t+1" is the lag1 row.

## Caveats

- Signal-side choices (take-bar share, pareto veto) were made with the base book, as the search does.
  Only year N's execution changes.
- Impact uses the largest stake of a $100k book. A $50k book is about 0.7x that impact.

Next: phase 1 (alpha vs beta, benchmarks a-d). By the plan, the current system is retired as a candidate
for capital. The paper book stays frozen as a measurement only.
