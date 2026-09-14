# System 09 - Results

All three phases have run, and **the sealed 2026 window was read twice**. Both readings are
below, in the order they were taken, and the second one is not clean. The headline first:

> | | R1 upside-down population | R2 corrected classes | R3 classes refreshed |
> |---|---|---|---|
> | Return | **-16.07%** | **-0.52%** | **+17.85%** |
> | Operations | 144 | 144 | 144 |
> | Successful / unsuccessful | 67 / 77 | 71 / 73 | 68 / 76 |
> | Success ratio | 46.53% | 49.31% | 47.22% |
> | Max drawdown | -43.24% | -17.84% | -29.90% |
> | Model IC on the sealed rows | +0.1325 | +0.1927 | **-0.0553** |
> | Directional accuracy | 51.69% | 46.06% | 45.60% |
> | Buy & hold BTC, same window | -11.27% | -11.25% | -11.25% |
> | Buy & hold universe, same window | -7.67% | -7.78% | -7.78% |
>
> **Three readings of a window that may honestly be read once. None of them is a clean
> out-of-sample result**, and the third is the one that proves the point: it is the only
> profitable reading and it was produced by a model whose ranking on those same rows is
> **negative** (IC -0.0553, hit rate 45.6%). The P&L and the skill measure disagree in sign,
> so +17.85% is not evidence of an edge - it is what a four-name long book happened to hold.
> See *Three readings* at the foot of this page.

This page is in three parts: **phase 1**, the whole record reconstructed; **phase 2**, the
model trained on it; **phase 3**, the sealed forward test. Reproduce with
`python -m quantlab_system09.phase1`, then `.train`, then `.phase3`.

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

---
---

# Phase 2 - training the model

`python -m quantlab_system09.train` (RTX 4060, CUDA, about 30 seconds).

**What was trained, and why it is not circular.** The obvious reading of "train the model on
how the players behaved" is to fit a policy to the cohort flows the reconstruction produced.
That would be fitting the asserted rules in `cohorts.py` to themselves. So the cohort state is
the **input** and the market's forward return is the **target**, and the experiment is the
design's V4: does knowing who holds the coins and who holds the dry powder help predict what
happens next, beyond what price already says?

Two models, identical in architecture, seed, optimiser, epochs and folds. The only difference
is the input width.

| Fold (validate) | Train rows | Valid rows | MARKET IC | MARKET+LEDGER IC | Ledger better? |
|---|---|---|---|---|---|
| 2021 | 7,663 | 4,003 | +0.0141 | +0.0181 | yes |
| 2022 | 11,666 | 4,015 | +0.0877 | +0.1383 | yes |
| 2023 | 15,681 | 4,237 | +0.0878 | +0.2589 | yes |
| 2024 | 19,918 | 5,047 | +0.1181 | +0.0816 | no |
| 2025 | 24,965 | 5,110 | +0.1694 | +0.2090 | yes |
| **mean** | | | **+0.0954** | **+0.1412** | **4 of 5** |

| | mean IC | mean directional accuracy | positive folds |
|---|---|---|---|
| MARKET | +0.0954 | 0.5141 | 5 / 5 |
| MARKET + LEDGER | +0.1412 | 0.5003 | 5 / 5 |

**V4 verdict: LEDGER HELPS** - mean IC +0.0458, four folds of five, both variants positive
in every fold.

Read it honestly all the same. The ledger variant wins mean IC and four folds, and loses on
mean directional accuracy (0.5003 against 0.5141) - it ranks better and calls the sign no
better than a coin. The per-fold gain is +0.004, +0.05, +0.17, +0.04 against -0.04: one clear
loss, so the spread still touches zero, and this laboratory's own rule says an edge whose
spread straddles zero has not earned a sealed reading. The sealed rows then returned IC
**-0.0553**, which is what that rule exists to predict.

Rows 33,575 across 14 assets (30,075 in the research era). 7 market features, 22 ledger
features, 7-day horizon. Nothing was selected on 2026.

---

# Phase 3 - the sealed 2026 forward test

`python -m quantlab_system09.phase3`. **Read once, on 2026-09-14. The window is spent.**

Window 2026-01-01 to 2026-09-14. USD 100,000, long only, at most 4 concurrent positions,
7-day holding period, 0.30% round-trip cost, position capped at 0.1% of the asset's own dollar
volume on the entry day. Model: `market+ledger`, 29 inputs, fitted and selected entirely on
2017-2025.

## Reading 3 - stable class proportions (the current artefact)

| | |
|---|---|
| Operations | **144** |
| Successful / unsuccessful | **68 / 76** |
| Success ratio | **47.22%** |
| Average win / average loss | +11.31% / -7.69% |
| **Return** | **+17.85%** |
| Max drawdown | -29.90% |
| Final equity | $117,849 |
| Model IC on the sealed rows | **-0.0553** |
| Directional accuracy | 45.60% |

| | Return, identical window |
|---|---|
| **System 09** | **+17.85%** |
| Buy and hold BTC | -11.25% |
| Buy and hold universe, equally weighted | -7.78% |

### Why this number must not be celebrated

The book beat both baselines by 25 to 29 points **while its ranking of the same rows was
worse than random**. Those two facts cannot both describe a working model. What they describe
is a long-only policy that must always hold four names out of fourteen in a window where three
assets rose hard (ZEC +118%, NEAR +50%, TRX +19%): a rotation rule with no skill lands on them
often enough, and +11.31% average wins against -7.69% average losses is the payoff shape of
holding volatile survivors, not of forecasting them.

The research folds said mean IC +0.1412. The sealed window said -0.0553. **That gap is the
result of phase 3** - the ledger features generalise out of sample far worse than the
walk-forward folds implied - and the P&L is a by-product that happens to be green.

## Reading 2 - corrected classes, assigned at birth (superseded)

| | |
|---|---|
| Operations | **144** |
| Successful | **71** |
| Unsuccessful | **73** |
| Success ratio | **49.31%** |
| Average win / average loss | +6.44% / -5.99% |
| **Return** | **-0.52%** |
| Max drawdown | -17.84% |
| Final equity | $99,484 |
| Model IC on the sealed rows | +0.1927 |
| Directional accuracy | 46.06% |

### Measured against holding

| | Return, identical window |
|---|---|
| **System 09** | **-0.52%** |
| Buy and hold BTC | -11.25% |
| Buy and hold the universe, equally weighted | -7.78% |

The book finished roughly flat in a window where Bitcoin fell 11% and the equal-weighted
universe fell 8%. It beat both baselines by seven to eleven points and **still lost money**.
Eleven of fourteen assets fell; only ZEC (+118%), NEAR (+50%) and TRX (+19%) rose.

### What the split says

- **Ranking is informative, sign is not.** IC on the sealed rows is +0.1927 - higher than any
  research fold - while directional accuracy is **46.06%**, below a coin toss. The model sorts
  assets well and calls the direction badly. A long-only book that must always hold four names
  can use the first; it has no way to act on the second except by standing aside, and standing
  aside is not in the policy.
- **The risk layer the design specified still does not exist.** Section L5 says sizing and
  stops are inherited from system 06 - stops, a slow-trend gate, concentration limits - and
  phase 3 has none of them. The -17.84% drawdown is the shape of that absence.
- **Expectancy is thin, not broken.** 49.31% of trades win, +6.44% against -5.99%: gross
  expectancy is slightly positive and the 0.30% round trip on 144 operations takes it back.

## Reading 1 - the upside-down population (superseded, kept on the record)

Taken first, on the population that had 148 whales, 84 institutions and 20 retail agents.

| | |
|---|---|
| Operations / successful / unsuccessful | 144 / 67 / 77 |
| Success ratio | 46.53% |
| Return | **-16.07%** |
| Max drawdown | -43.24% |
| Model IC on the sealed rows | +0.1325 |
| Directional accuracy | 51.69% |

## Three readings, and why that matters more than any of the numbers

The window was opened, a defect was found, the window was opened again; then a second defect
was found and it was opened a third time. Both defects were structural and real - the
participant pyramid was upside down (the operator spotted it in the segment table), and class
was then assigned once at birth, so it drifted as the ladder grew until there were twelve
whales against twenty-eight institutions. **Neither was found by looking at the 2026 P&L**,
and each correction was specified before the next reading was taken.

None of that is visible from outside. An observer cannot distinguish "two real defects were
fixed" from "the window was re-rolled until it went green", and the readings went -16.07%,
-0.52%, +17.85%. So the conservative position is the only defensible one:

- **No reading here is a clean out-of-sample result.** The sealed-window discipline was spent
  on the first one, and that reading was taken on a model of the market nobody should defend.
- **The +17.85% is not evidence of an edge.** Its own skill statistic is negative. Quoting it
  as a forward-test result would be the exact selection optimism this laboratory has already
  paid for three times (see `system06-sealed-reading-power`).
- **The next forward test needs a window this system has never touched** - 2027, or a venue
  and period held back deliberately. v2 should seal one before a line of it is written.
- **Do not add the missing risk layer and read 2026 a fourth time.**

What phase 3 actually established, and it is worth having: the ledger features' out-of-sample
IC collapses from +0.14 to -0.06. That is a real, reportable finding about the reconstruction,
and it is independent of the P&L.
