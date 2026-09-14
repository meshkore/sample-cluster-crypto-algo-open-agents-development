# System 09 - Results

**There are no trading returns on this page, and there will not be until Phase 7.** System
09 has no `decide(tick)` brain, has never taken a position and has never touched the sealed
window. What follows are the results of the Phase 3 MVP: a reconstruction and the two
validation rungs it is entitled to climb, V0 and V2.

Reproduce with `python -m quantlab_system09.mvp` (about 25 seconds, no network).

---

## The run

| | |
|---|---|
| Symbol | BTCUSDT, Binance spot, plus a minimal perpetual book |
| Era | **training / research only**: `[2020-01-01, 2026-01-01)` |
| Sealed forward (2026) | **never opened.** Nothing here has been read against it |
| Buckets | 16,976 dollar-volume buckets, never crossing a UTC midnight (~8/day) |
| Days | 2,192 |
| Population | 106 agents: 6 trading types x 13 Zipf rungs, miners x 13, perps x 13, 2 boundary operators |
| Fitted parameters | **none.** Every behavioural constant is an unfitted prior |

The window opens in 2020, not at the first Bitcoin trade, because the *cash* side of the
ledger is only observable in the stablecoin era. It closes before 2026 because the catalogue
will not serve the sealed window here.

---

## V0 - accounting

| Check | Result |
|---|---|
| Buckets settled | 16,976 |
| Coin total drift | **-2.1e-07 BTC** over six years |
| Cash total drift | **+0.0008 USD** over six years |
| Sell shortfalls (a cohort asked to sell coins it did not hold) | **0** |
| Funding left unpaid | **$0** |
| Verdict | **PASS** |

Drift at 1e-7 on a total of 2e7 is float64 rounding, not a leak. The invariant runs on every
settlement rather than at the end, so a failure names the bucket and the agent.

## V0 - fidelity to the tape, per calendar year

`fill` is the fraction of observed volume the reconstructed population was actually able to
trade. It is the diagnostic that matters more than any output: a population whose cash and
coins are distributed roughly right fills essentially all of it.

| Year | Days | Fill, mean | Fill, worst day | LTH Δcoins | Institutional Δcoins | Price, year end |
|---|---|---|---|---|---|---|
| 2020 | 366 | 0.9591 | 0.2481 | -216,595 | +247,460 | $28,924 |
| 2021 | 365 | **0.8982** | **0.1602** | **-2,086,706** | +119,824 | $46,217 |
| 2022 | 365 | 1.0000 | 1.0000 | -1,736,149 | -1,070,510 | $16,542 |
| 2023 | 365 | 1.0000 | 1.0000 | -1,547,922 | +729,526 | $42,284 |
| 2024 | 366 | 0.9999 | 0.9565 | -563,298 | +516,875 | $93,576 |
| 2025 | 365 | 1.0000 | 1.0000 | -378,070 | +206,439 | $87,648 |
| **all** | **2,192** | **0.9762** | **0.1602** | | | |

Read this table as the honest boundary of the system's usable range. **From 2022 the
reconstruction funds the entire tape; in 2020-2021 it cannot**, because the stablecoin float
was small next to BTC turnover and pre-2022 exchange cash was mostly fiat, which is not
observable anywhere. Any later phase should treat 2020-2021 as burn-in rather than as data.

The long-term-holder column is the clearest *failure* in the table: -2.09M coins in 2021 is
far more turnover than that cohort has in reality, and it says the 0.2%/day cap is too loose.

---

## V2 - anchor recovery (the test that can fail)

ETF creations and redemptions are **withheld entirely** from the reconstruction. The
institutional cohort acts on its behavioural rule alone, and what it ends up holding is
scored against the published Farside series it never saw - and, crucially, against the
**baseline**: the raw unconstrained desire that drove the rule. The question is not whether
the reconstruction correlates with ETF flow. It is whether it correlates *more than its own
driving signal does*.

Scored on 511 days, 2024-01-11 to 2025-12-31.

| Horizon | Statistic | Inferred | Baseline | Inferred wins |
|---|---|---|---|---|
| daily | pearson | **+0.2847** | +0.2430 | yes |
| daily | spearman | +0.2333 | +0.2437 | no |
| daily | sign agreement | 0.6040 | 0.6101 | no |
| weekly | pearson | **+0.4512** | +0.3833 | yes |
| weekly | spearman | +0.4411 | +0.4329 | yes |
| weekly | sign agreement | 0.6575 | 0.6849 | no |
| cumulative | pearson | +0.9849 | +0.9809 | yes |
| cumulative | spearman | +0.9818 | +0.9832 | no |
| cumulative | sign agreement | 1.0000 | 1.0000 | tie |

**Verdict: NOT RECOVERED — 4 of 9.**

The inferred cohort does track ETF flow, and at weekly horizon it tracks it well. But the
naive predictor already does, because ETF flows chase the slow trend and the cohort's rule
reads the slow trend. The ledger's capacity constraints, turnover budgets and competition
for the tape's flow bought **+0.068 of weekly pearson and a losing record overall**.

This is a negative result and it is the point of having built the test. It says the
institutional cohort's state is not identified beyond the signal that drives it. It does not
say the reconstruction is worthless - V0 and the fill table say the books are sound - and it
does not yet say the *other* cohorts are unidentified, because they have not been tested
against an anchor. It does say that no further layer should be built on this cohort until
either a calibrated version or a different anchor clears the bar.

---

## Who holds what, 2025-12-31, BTC at $87,648 (anchored reconstruction)

Read as a **model state, not a measurement**: the levels are the opening priors with six
years of tape on top. The shares are what this population implies, not what the chain says.

| Cohort | Coins | Share | Cash $bn | Avg basis | Unrealised $bn |
|---|---|---|---|---|---|
| long_term_holders | 4,342,094 | 21.7% | 10.4 | $7,219 | +349.2 |
| market_makers | 3,720,313 | 18.6% | 28.4 | $64,980 | +84.3 |
| basis_arb | 3,682,421 | 18.4% | 28.1 | $32,196 | +204.2 |
| momentum_retail | 3,059,815 | 15.3% | 34.8 | $62,173 | +77.9 |
| dip_buyers | 2,603,317 | 13.0% | 31.3 | $37,933 | +129.4 |
| institutional | 1,840,321 | 9.2% | 16.0 | $46,969 | +74.9 |
| miners | 721,534 | 3.6% | 1.3 | $926 | +62.6 |
| levered_directional | 0 | 0.0% | 16.8 | - | - |
| exchanges / issuers | 0 | 0.0% | 0.0 | - | - |
| **total** | **19,969,816** | 100% | **167.3** | | |

The one number here with an external check: the institutional cohort accumulates +516,875
BTC across 2024, against roughly +560,000 BTC of real net growth in US spot ETF holdings
over the same year. That is the anchored run, so the cash was given to it - but the
conversion of that cash into coins through the tape, at the tape's own prices, is the
model's own work.

---

## Baselines

There is no trivial return baseline to beat, because there is no return. The baselines that
apply at this stage are the two above and they are both stated against the run:

- **V0's null**: a model with no conservation law. This one drifts by 1e-7 BTC in six years.
- **V2's null**: the unconstrained behavioural desire. This one **did not beat it**.
