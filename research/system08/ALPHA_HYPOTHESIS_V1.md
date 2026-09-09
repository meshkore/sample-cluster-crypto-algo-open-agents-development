# Alpha module: proposed hypothesis and design — for review

**To:** the authors of `ALPHA_SYSTEM_SPEC.md` v1.0
**From:** the operating team of the laboratory that will implement it
**Date:** 2026-09-09
**Purpose:** converge on ONE falsifiable hypothesis and ONE alpha-module design before any code is written. We have read the specification in full, audited what our data and infrastructure can actually support, and we disagree with it in four specific places. We would like those four disagreements resolved — by you agreeing, or by you showing us we are wrong — because each one changes the build.

---

## 0. What you should know about who is implementing this

We are not starting from zero and we are not starting from success. We have run six generations of trading systems. The current champion is a causal TCN on 15-minute candles, long-only spot, 14 crypto pairs. Its sealed-2026 result is **+25.71%** at 22.13% drawdown on 90 trades. That is the number your design has to beat.

More useful than the win are the failures, because they are what shaped the disagreements below:

| what happened | what it cost |
|---|---|
| Three separate candidates were approved by out-of-sample walk-forward evidence and then **lost the sealed year** — one by 37 points | three of the very few unbiased readings we will ever have |
| A 32-dimensional Bayesian search over 1,668 trials found nothing that transferred | ~3 weeks |
| A module ablation found that **4 of the 9 active levers carried nothing measurable** | they had been shipping for months |
| Our founding hypothesis (imitate a perfect-hindsight oracle) had no economic mechanism — it was a labelling trick | the whole generation |

The diagnosis of the three sealed losses is the single most important thing we can tell you, and it is the origin of disagreement #3 below.

---

## 1. What we actually have (measured, not assumed)

We probed every source rather than trusting documentation. Free and available **today**:

| dataset | content | range | volume |
|---|---|---|---|
| Binance UM `aggTrades` | every trade **with aggressor side** | **2020-01 → now** | ~415 MB/month (BTC) |
| Binance UM `bookDepth` | cumulative depth at ±0.2/1/2/3/4/5%, **1 snapshot per minute** | **2023-01 → now** | 0.5 MB/day |
| Binance UM `metrics` | open interest, long/short ratios | continuous | small |
| Binance UM `markPrice` / `indexPrice` / `premiumIndex` / `fundingRate` | basis and carry | continuous | small |
| Bybit `trading` | trades with taker side | 2022 → now | medium |
| OKX swap trades | trades | → now | medium |
| Binance UM `bookTicker` (L1: spread, microprice) | best bid/ask updates | **2023-05-16 → 2024-03-30 ONLY** — discontinued | 325 MB/day |
| Tardis free samples | **full L2 incremental, book_snapshot_25, liquidations, derivative_ticker** | **one day per month, 2020 → now (~80 days)** | L2 404 MB/day; snapshot_25 45 MB/day |

**What does not exist historically at any price we would pay:** continuous L2 deltas, continuous L1 after 2024-03, and continuous liquidations for USD-M. Those are forward-capture only.

**Consequence for your specification.** Your `FS_PRICE`, `FS_FLOW`, `FS_DERIVATIVES`, `FS_CROSS_ASSET`, `FS_REGIME` and a meaningful part of `FS_LOB` (the depth-band imbalance family, `L011`–`L015`, `L024`–`L026`, `L046`–`L049`, `R012`) are trainable over **years**. Your `OFI`/`MLOFI` family (`L051`–`L072`), replenishment (`L041`–`L045`) and the entire liquidation branch are **80 sampled days or nothing**.

That is not a blocker. It is a sequencing fact, and it happens to match your own §31.1 tiering. But it means the microstructure branch you placed at the centre cannot be the thing we validate first.

**Infrastructure already built and tested (913 tests):** a backtest engine with realistic costs, participation caps and market impact; signed positions with shorts; funding accrual with the correct sign per side; a gross-exposure ceiling; intrabar forced-exit modelling (see §4); a shared data catalogue with the 2026 forward window structurally locked; and a causal transform library (rolling z, robust z/MAD, rolling percentile, signed log, relative/log change, directional efficiency) fitted on nothing — statistics travel with the series.

---

## 2. The hypothesis we propose to adopt

We want to commit to **one mechanism**, not a feature catalogue. This is the one we think is right, and it is the one your §3 identifies as central:

> **H1 — Absorption.** When aggressive order flow in one direction is large relative to its own recent distribution **and** the price response to that flow is abnormally small, the subsequent return over the next hour is biased **against** the aggressive flow.
>
> **Mechanism.** Aggressive buying that does not lift price is being absorbed by passive size. The buyers are spending inventory and conviction; the seller is not. When the aggressive side exhausts, price reverts toward where the passive size wanted it.

Why this one:

- **It has an economic story**, which our previous generation did not. We can say who is on the other side and why they win.
- **It is measurable on trades alone** — signed flow and price response — so it is testable over **6.7 years**, not 80 days.
- **It predicts its own boundary conditions.** The effect should be *stronger* when visible depth is thin and *weaker* when depth is deep. We have depth from 2023. That conditional is a second, independent test of the same mechanism, and a mechanism that survives its own conditional is a different class of evidence from a number that survives a backtest.
- **It generates a natural NO-TRADE**, which is most of the time. Both your §30.2 and our own regime evidence want that.

**Pre-registered kill criterion, written before any number exists:** if, in walk-forward on years the model never saw, the conditional 60-minute return given (high flow, low response) is not distinguishable from the unconditional return — and does not strengthen in the thin-depth subsample — H1 is dead and we do not rescue it with parameters.

---

## 3. Four disagreements with the specification

### 3.1 The decision clock and the holding horizon must be separated — and the horizon should be 60m, not 15m

Your §2.2 sets a 1-minute decision cadence and your §30.3 makes 15m the primary horizon.

We measured, on our own record, how the payoff to fast trading changed over time. The figure is the return multiple of a fast-rotating configuration against a slow one, by calendar year:

```
2018  2.97x    2019  1.94x    2020  1.58x    2021  4.17x
2022  1.12x    2023  1.00x    2024  0.82x    2025  1.08x    2026  0.70x  (sealed)
```

Fast rotation was enormously profitable through 2021 and has paid **nothing since 2022**. We verified this is a property of the calendar and not of our model's memory: we ran the same test across three training cutoffs so the same calendar year appeared as both seen and unseen, and the gap vanished (2024: 0.86x seen, 0.81x unseen).

**We accept your 1-minute decision clock and we want it** — 3.1M decision rows over three years on two symbols is exactly the cure for the disease described in 3.3. But we propose **60m as the primary forecast horizon**, with 15m as entry timing only, for three converging reasons: the regime evidence above; the exit-risk constraint in §4; and the fact that a 15m horizon at 1-minute cadence is a turnover profile our own data says stopped paying.

**Question for you:** is there evidence in your own testing that the 15m horizon still carries edge post-2022, or was the choice made on general grounds?

### 3.2 Short is not symmetric, and your §30.1 says it is

Your decision policy computes `EV_short` as the mirror of `EV_long`. We think this is the most dangerous line in the specification.

A long position, unleveraged, has a loss bounded at 100% and — critically — **survives a spike that reverts**. A short has unbounded loss and does not survive it, because the venue closes the position inside the spike whether our model saw it or not.

We found this was not merely a policy issue but a **measurement** one. Our stops were evaluated on the bar close and filled at the next open, so a violent move *inside* a bar that reverted before the close left no trace whatsoever. For an unleveraged long that is optimistic but survivable. For a collateralised short it is ruin the backtest would never show — and a short book measured that way looks far safer than it is.

We have fixed the engine: every open short is now checked against the bar's **high**, against both a server-side protective stop and the collateral itself, and the fill is the **worse** of the trigger and the bar's open so a gap through a resting stop fills where the market actually is. Forced exits are reported separately from the trade count, because a return that arrives with liquidations attached is not the same result as one without them.

**What we propose:** the short side carries a **higher EV threshold**, a **volatility-regime veto**, and sizing derived from a survivable gap rather than from the intended stop. Not a mirror.

**Question for you:** do you agree, and if so where in the architecture should the asymmetry live — in the decision policy, in the target definition, or in both?

### 3.3 §39 is missing the test that would have saved us three sealed readings

Your statistical validation section is strong — monotonicity by decile, block bootstrap, multiple-testing correction, deflated Sharpe, a final untouched holdout. We would add one gate, and we would put it before all of them, because it is the one whose absence cost us three of our scarcest readings.

Every one of those three candidates had genuine out-of-sample evidence. The last one, for example, beat the incumbent on **7 of 8 independent walk-forward boundaries** with a median advantage of +2%. Then it lost the sealed year.

The reason, found afterwards: the per-year advantage ran from **0.76x to 1.52x**, median 1.02x. It won about **seven years in ten**. A seven-in-ten coin cannot be settled by one toss — and nobody had computed the odds before spending the reading. It was not a broken instrument. It was an **unpowered test**, and "7 of 8 boundaries" sounded like eight verdicts when at the relevant granularity it was seven noisy year-observations.

> **The gate:** before spending an evaluation the sample size cannot repeat, compute the candidate's per-period ratio against the incumbent across every available fold, and report min/q1/median/q3/max. **If that spread straddles 1.0, the evaluation cannot settle it.** Require an edge large relative to its own dispersion, not merely a positive median.

This is related to Deflated Sharpe but is not the same thing: DSR corrects for how many trials produced the winner. This asks whether the winner's edge is large enough for the *evaluation window* to distinguish it from zero. Both are needed.

**Question for you:** do you have a preferred formal treatment of this? We have implemented it as a hard gate; we would rather use a standard one than our own.

### 3.4 Do not start at 180–260 features

Your §21 warns against implementing every optional feature and then recommends 180–260 for V1. We think the warning is right and the number contradicts it.

Our evidence: a mature system with 33 available levers had 9 switched on, and an ablation found **4 of those 9 carried nothing measurable** — one of them was actively costing us. Those four had been shipping for months, each switched on by its own one-lever experiment and then never re-examined beside the others.

Separately, we learned that a joint Bayesian search **cannot** find this: of 1,607 trials in a 32-dimensional TPE anchored on the incumbent, the closest trial to "the incumbent with one lever moved" differed in **24 of the other 31 levers**. Single-lever effects are invisible inside a joint search. They have to be ablated separately.

**What we propose for V1:** approximately **40 features**, all of them serving H1 and its boundary condition — signed flow at several windows, price response, the ratio between them, absorption scores, depth-band imbalance and depth drop, volatility and liquidity regime, OI and funding, and the BTC market factor. Every feature group must justify itself by ablation before a fifth is added.

**Question for you:** which of your feature families would you most expect to add incremental value over `FS_FLOW + FS_PRICE` alone, so we can prioritise the second wave by your judgement rather than by ours?

---

## 4. What we agree with without reservation

So this reads as a collaboration and not a critique: your §0.5 (no feature available before its live timestamp), §0.7 (no folklore as hard rules), §0.9 (the model must be able to say NO TRADE), §0.10 (economic usefulness after costs, not accuracy), §7 (never normalise on full-dataset statistics), §22 (predict a distribution, not a label — and the quantiles are what let us price the tail risk that makes shorts dangerous), §23 (purge, embargo, no random splits, fit every transform in-fold), §32.3 (ablation by feature group), §38 (an LLM proposes hypotheses and deterministic code judges them — never the reverse), and §44 (the leakage checklist).

We would add one line to §38's spirit, which has become the maxim of our loop: **Recursive Self Improvement**. When the loop loses, the first question is not "which parameter was wrong" but **"which gate was missing"**. A run that produces a better strategy has not improved the loop; a run that produces a new gate has. Each of the disagreements above is a gate that a failure taught us.

---

## 5. The alpha module we propose to build

```
MarketState(t)              1-minute decision clock, multi-resolution context
        |                   (1m entry structure, 5m/15m short, 1h regime, 4h macro)
        v
AbsorptionModel             gradient-boosted, ~40 features, all serving H1
        |                   trained on 2020-2024, walk-forward
        v
ForecastBundle              P(up|down|timeout) and q10..q90 of the 60m return,
        |                   plus the 15m head for entry timing only
        v
AsymmetricPolicy            LONG  if net EV > min_edge
        |                   SHORT if net EV > min_edge_short (higher) AND
        |                         volatility regime is not extreme AND
        |                         a survivable gap is affordable at this size
        |                   FLAT otherwise, which is the default and most of the time
        v
existing execution layer    costs, participation caps, forced-exit modelling,
                            funding accrual, gross exposure <= ceiling
```

**Validation sequence, in order, no step skipped:**

1. **Sanity** — your §32.1, plus our truncation tests: recompute every feature from data truncated at its own timestamp and require the value to be unchanged.
2. **Baselines first** — your §25.1. The model must beat "always flat", last-return sign, momentum, mean reversion, and flow-only logistic, out of sample after costs.
3. **H1 in isolation**, on trades alone, 2020–2024, walk-forward. If dead, stop here and report it.
4. **The boundary condition** — does the effect strengthen in thin depth? This is the mechanism test, and it is what separates a mechanism from a fitted number.
5. **Ablation** by feature group before anything is added.
6. **The power gate of §3.3** before any sealed evaluation is spent.
7. One sealed reading, recorded whatever it says.

---

## 6. What we are asking you for

1. Do you accept **H1 as the single V1 hypothesis**, or do you believe a different mechanism in your specification is a better first bet — and on what evidence?
2. The four disagreements in §3: agree, or correct us.
3. The three questions embedded there: the 15m horizon post-2022; where the long/short asymmetry belongs architecturally; and a standard formal treatment for the power gate.
4. One thing we have not asked about that you think we have wrong.

We would rather spend a week converging on the right question than three months answering the wrong one well. We have done the second version already.
