# System 09 - Results

**There are no trading returns on this page, and there will not be until phase 3.** System 09
has no `decide(tick)` brain, has never taken a position and has never touched the sealed
window. What follows is phase 1: the whole record reconstructed, and the two validation rungs
it is entitled to climb.

Reproduce with `python -m quantlab_system09.phase1` (about six minutes, no network).

---

## The run

| | |
|---|---|
| Window | **2017-08-17 to 2025-12-31**, the whole record, inclusive at both ends |
| Era | **training / research only.** 2026 is the sealed window and was not opened |
| Assets | 14, each joining the day it first trades: BTC & ETH 2017-08-17, BNB 2017-11, ADA 2018-04, XRP 2018-05, TRX 2018-06, LINK 2019-01, ZEC 2019-03, DOGE 2019-07, SOL 2020-08, NEAR 2020-10, SUI 2023-05, WLD 2023-07, ACE 2023-12 |
| Buckets | 177,699 dollar-volume buckets, never crossing a UTC midnight (~6/day/asset) |
| Days | 3,059 |
| Players | 105 at the open, **435 at the 2024 peak**, 344 at the close |
| Fitted parameters | **none.** Every behavioural constant is an unfitted prior |

The ledger opens **empty**. Every unit and every dollar in it arrived through a boundary
event that can be named and dated.

---

## V0 - accounting

| Check | Result |
|---|---|
| Buckets settled | 177,699 |
| Unit total drift, worst of 14 assets | **-1.03e-14** (relative) |
| Cash total drift | **+$0.058** on a $560bn pool |
| Sell shortfalls (a cohort asked to sell units it did not hold) | **0** |
| Funding left unpaid (margin the levered cohort could not meet) | $518,614 |
| Verdict | **PASS** |

Drift at 1e-14 relative over eight years and 177,699 settlements is float64 rounding. The
invariant runs at every daily close, so a failure names the day and the agent.

## V0 - fidelity to the tape, and the inferred fiat channel

`fill` is the fraction of observed dollar volume the reconstructed population was able to
trade. `fiat ramped` is the fifth boundary channel: the dollars the *observed* cash could not
account for, inferred as a residual and recorded.

| Year | Days | Fill, mean | Worst day | Players | Assets | Fiat ramped $bn |
|---|---|---|---|---|---|---|
| 2017 | 137 | 0.9456 | 0.0000 | 218 | 3 | 7.5 |
| 2018 | 365 | 0.9741 | 0.6784 | 218 | 6 | 16.0 |
| 2019 | 365 | 0.9357 | 0.6322 | 218 | 9 | 7.5 |
| 2020 | 366 | 0.9804 | 0.7313 | 351 | 11 | 39.6 |
| 2021 | 365 | 0.9245 | 0.4358 | 407 | 11 | 41.8 |
| 2022 | 365 | 0.9953 | 0.6695 | 372 | 11 | 84.8 |
| 2023 | 365 | 0.9979 | 0.8529 | 372 | 14 | **0.0** |
| 2024 | 366 | 0.9950 | 0.8426 | 435 | 14 | **0.0** |
| 2025 | 365 | 0.9855 | 0.7534 | 344 | 14 | **0.0** |
| **all** | **3,059** | **0.9723** | 0.0000 | | | **197.2** |

**The fiat column is the one result on this page that was predicted in advance and then
came true.** The design argued that pre-stablecoin exchange balances were mostly fiat, that
no public series has ever measured them, and that the honest treatment is to infer the gap
and check that it *fades as stablecoins take over*. It does: $7.5bn in 2017 rising to
$84.8bn through the 2022 deleveraging, then **exactly zero from 2023 onward** - from that
point the observed stablecoin float alone funds the entire observed tape. That is a
falsifiable prediction the model could have failed and did not.

The worst day is 2017-08-17 itself, when the ledger has no cash at all. The weakest full year
is 2021, where the population funds 92% of a tape that was turning over faster than the
observed cash could support.

---

## V2 - anchor recovery (the test that can fail)

ETF creations and redemptions are **withheld entirely** from the reconstruction. The
institutional cohort acts on its behavioural rule alone, and what it ends up holding is scored
against the published Farside series it never saw - and against the **baseline**: the raw
unconstrained desire that drove the rule. The question is not whether the reconstruction
correlates with ETF flow. It is whether it correlates *more than its own driving signal*.

Scored on 511 days, 2024-01-11 to 2025-12-31.

| Horizon | Statistic | Inferred | Baseline | Wins |
|---|---|---|---|---|
| daily | pearson | **+0.2956** | +0.2429 | yes |
| daily | spearman | **+0.2726** | +0.2434 | yes |
| daily | sign agreement | **0.6202** | 0.6101 | yes |
| weekly | pearson | **+0.4593** | +0.3830 | yes |
| weekly | spearman | **+0.4825** | +0.4329 | yes |
| weekly | sign agreement | **0.7397** | 0.6849 | yes |
| cumulative | pearson | +0.9059 | **+0.9809** | no |
| cumulative | spearman | +0.8967 | **+0.9831** | no |
| cumulative | sign | 1.0000 | 1.0000 | tie |

**Verdict: RECOVERED — 6 of 9.** The one-asset MVP scored 4 of 9 on the same test; the full
reconstruction scores 6.

Read it precisely, because the split is informative rather than noise. The reconstruction
beats the naive trend signal on **every flow statistic** - it knows *when* institutional money
moved, and by how much, better than the trend does. It loses on **both cumulative-path
statistics**: the running total drifts from the published one, so the reconstruction's sense
of the institutional cohort's *level* is worse than a trend integral. Flow yes, stock no.
That is exactly the failure mode the opening priors would produce, and it says the next
improvement is to the level (`COIN_PRIOR`) rather than to the dynamics.

---

## Balances at the close of the record, 2025-12-31

These are the books phase 2 opens with. Read them as a **model state, not a measurement**:
the levels descend from asserted opening priors with eight years of tape on top.

| Cohort | Agents | Holdings $bn | Cash $bn | Unrealised $bn | Realised $bn |
|---|---|---|---|---|---|
| long_term_holders | 47 | 977.1 | 210.1 | +871.2 | +216.1 |
| dip_buyers | 47 | 445.7 | 29.7 | +21.7 | +300.6 |
| basis_arb | 47 | 327.1 | 29.2 | +221.9 | +11.0 |
| institutional | 47 | 291.7 | 29.4 | +151.4 | +43.0 |
| momentum_retail | 47 | 235.1 | 101.3 | +69.5 | +152.8 |
| market_makers | 47 | 188.4 | 35.9 | +49.5 | +56.2 |
| miners | 13 | 37.5 | 70.4 | +37.5 | +93.9 |
| levered_directional | 47 | 0.0 | 50.3 | - | - |
| exchanges / issuers | 2 | 0.0 | 4.3 | - | - |
| **TOTAL** | **344** | **2,502.6** | **560.6** | | |

**Dry powder is 22.4% of holdings.** That is the headline number the operator asked for:
who holds the coins, and who still has cash to spend.

Holdings by asset, with the float the ledger carries:

| Asset | Price | Float held | Value $bn |
|---|---|---|---|
| BTCUSDT | 87,664.66 | 19,969,816 | 1,750.6 |
| ETHUSDT | 2,974.14 | 122,047,243 | 363.0 |
| XRPUSDT | 1.84 | 62,879,209,849 | 115.5 |
| BNBUSDT | 864.38 | 133,160,915 | 115.1 |
| SOLUSDT | 124.68 | 586,892,735 | 73.2 |
| TRXUSDT | 0.28 | 94,950,173,797 | 27.0 |
| DOGEUSDT | 0.12 | 155,910,866,384 | 18.3 |
| ADAUSDT | 0.33 | 37,516,725,700 | 12.5 |
| LINKUSDT | 12.26 | 748,099,970 | 9.2 |
| ZECUSDT | 513.15 | 16,930,431 | 8.7 |
| SUIUSDT | 1.40 | 4,096,537,147 | 5.7 |
| NEARUSDT | 1.51 | 1,306,297,465 | 2.0 |
| WLDUSDT | 0.48 | 3,592,832,556 | 1.7 |
| ACEUSDT | 0.27 | 110,552,174 | 0.0 |

The Bitcoin float, 19,969,816, is the chain's own number on that date - it is issued day by
day from `chain_total-bitcoins` rather than assumed. Every other asset carries a **snapshot**
of today's circulating supply held constant across the record, which is the largest known
level error here and is why assets still emitting look too large in the early years.

---

## Baselines

There is no trivial return baseline to beat, because there is no return. The baselines that
apply at this stage are stated against the run:

- **V0's null**: a model with no conservation law. This one drifts 1e-14 relative in eight
  years across fourteen assets.
- **V0's second null**: a model whose cash is assumed rather than inferred. This one predicts
  its own fiat residual falls to zero by 2023, and it does.
- **V2's null**: the unconstrained behavioural desire. This one **beats it on flow and loses
  to it on level**, 6 of 9.
